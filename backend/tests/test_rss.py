"""RSS 合并逻辑测试，重点是「按源轮流交错」这个行为。

不联网：fetch_feed 被换成假的，每个源返回预设的条目。

这条规则容易被后来的改动无意破坏——一旦退回"按源顺序拼接"，
max_total 一刀切下去，排在后面的源就整段消失，页面上再也看不到，
而且不会有任何报错。所以这里把顺序钉死。
"""

import pytest

from app import rss


def _item(source_name: str, n: int, link: str | None = None) -> dict:
    return {
        "title": f"{source_name}-{n}",
        "link": link if link is not None else f"https://example.com/{source_name}/{n}",
        "summary": "",
        "image": "",
        "source": f"https://feed/{source_name}",
        "source_name": source_name,
    }


def _install(monkeypatch, feeds: dict):
    """把 RSS_SOURCES 和 fetch_feed 换成假的。

    feeds 的值传 "ERROR" 字符串表示这个源抓取失败。
    """
    monkeypatch.setattr(
        rss, "RSS_SOURCES",
        [{"name": name, "url": f"https://feed/{name}"} for name in feeds],
    )

    def fake_fetch(url, limit=10):
        name = url.rsplit("/", 1)[-1]
        batch = feeds[name]
        if batch == "ERROR":
            return {"error": "模拟抓取失败"}
        return {"url": url, "count": len(batch), "news": batch[:limit]}

    monkeypatch.setattr(rss, "fetch_feed", fake_fetch)


@pytest.fixture
def three_feeds(monkeypatch):
    """三个源，每个 4 条。"""
    _install(monkeypatch, {
        "A": [_item("A", i) for i in range(4)],
        "B": [_item("B", i) for i in range(4)],
        "C": [_item("C", i) for i in range(4)],
    })


# ============================================================
# 核心：交错
# ============================================================

def test_items_are_interleaved_across_sources(three_feeds):
    items = rss.fetch_all(limit_per_source=4, max_total=6)
    assert [i["source_name"] for i in items] == ["A", "B", "C", "A", "B", "C"]


def test_every_source_survives_a_small_max_total(three_feeds):
    """回归测试：按源顺序拼接时，max_total=3 会让 B、C 一条都不剩。"""
    items = rss.fetch_all(limit_per_source=4, max_total=3)
    assert {i["source_name"] for i in items} == {"A", "B", "C"}


def test_respects_max_total(three_feeds):
    assert len(rss.fetch_all(limit_per_source=4, max_total=5)) == 5


def test_respects_limit_per_source(three_feeds):
    """max_total 够大时，每个源最多取 limit_per_source 条。"""
    items = rss.fetch_all(limit_per_source=2, max_total=100)
    assert len(items) == 6
    assert [i["source_name"] for i in items] == ["A", "B", "C", "A", "B", "C"]


# ============================================================
# 容错
# ============================================================

def test_failed_source_is_skipped_without_killing_the_rest(monkeypatch):
    _install(monkeypatch, {
        "A": [_item("A", 0)],
        "B": "ERROR",
        "C": [_item("C", 0)],
    })

    items = rss.fetch_all(limit_per_source=4, max_total=10)

    assert [i["source_name"] for i in items] == ["A", "C"]


def test_all_sources_failing_returns_empty(monkeypatch):
    _install(monkeypatch, {"A": "ERROR", "B": "ERROR"})
    assert rss.fetch_all(limit_per_source=4, max_total=10) == []


def test_empty_title_is_skipped(monkeypatch):
    blank = _item("A", 0)
    blank["title"] = ""
    _install(monkeypatch, {"A": [blank, _item("A", 1)]})

    items = rss.fetch_all(limit_per_source=4, max_total=10)

    assert [i["title"] for i in items] == ["A-1"]


def test_duplicate_links_are_removed(monkeypatch):
    """不同源转同一篇文章时，靠 link 去重。"""
    dup = "https://example.com/same-article"
    _install(monkeypatch, {
        "A": [_item("A", 0, link=dup)],
        "B": [_item("B", 0, link=dup)],
    })

    items = rss.fetch_all(limit_per_source=4, max_total=10)

    assert len(items) == 1
    assert items[0]["source_name"] == "A"


# ============================================================
# 白名单
# ============================================================

def test_whitelist_has_no_duplicates():
    assert len(rss.RSS_WHITELIST) == len(set(rss.RSS_WHITELIST))


def test_source_names_covers_every_source():
    assert set(rss.SOURCE_NAMES) == set(rss.RSS_WHITELIST)
