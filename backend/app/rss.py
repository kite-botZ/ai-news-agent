"""RSS 抓取与解析。

被两处复用，避免逻辑重复：
- app/agent/tools.py  的 fetch_rss 工具（给 Agent 用）
- app/routes/news.py  的 /api/news 接口（给前端新闻列表用）

安全：只允许抓取 RSS_SOURCES 白名单内的地址，防止 SSRF。
"""

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import httpx

# 命名空间
ATOM = "http://www.w3.org/2005/Atom"
RSS1 = "http://purl.org/rss/1.0/"
CONTENT = "http://purl.org/rss/1.0/modules/content/"
MEDIA = "http://search.yahoo.com/mrss/"

# 允许的 RSS 源（白名单）。name 用于前端展示。
#
# 选源标准：稳定 + 快。三个国外源（The Verge / TechCrunch / Hacker News）实测
# 中位数 2.3~4.1 秒，其中 The Verge 和 Hacker News 三轮里各有一轮直接超时——
# 超时会静默返回空，表现为这两个源在页面上时有时无，所以移出白名单。
# 需要重新挑源时跑 check_rss_sources.py（候选列表里保留着它们）。
RSS_SOURCES = [
    # 科技综合
    {"name": "IT 之家", "url": "https://www.ithome.com/rss/"},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed"},
    {"name": "少数派", "url": "https://sspai.com/feed"},
    # AI / 技术垂直
    {"name": "量子位", "url": "https://www.qbitai.com/feed"},
    {"name": "雷锋网", "url": "https://www.leiphone.com/feed"},
    {"name": "InfoQ", "url": "https://www.infoq.cn/feed"},
]

RSS_WHITELIST = [s["url"] for s in RSS_SOURCES]
SOURCE_NAMES = {s["url"]: s["name"] for s in RSS_SOURCES}

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AINewsAgent/1.0)"}

_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


# ============================================================
# 底层解析
# ============================================================

def _get_text(element, tag: str) -> str:
    """从 XML 元素里取文本，兼容多种命名空间。"""
    el = element.find(tag)
    if el is not None and el.text:
        return el.text
    for prefix in (ATOM, RSS1):
        el = element.find(f"{{{prefix}}}{tag}")
        if el is not None and el.text:
            return el.text
    return ""


def _clean_html(text: str) -> str:
    """去掉 HTML 标签和实体，保留纯文本。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_image(url: str) -> bool:
    return bool(url) and url.split("?")[0].lower().endswith(_IMG_EXT)


def _extract_image(item) -> str:
    """尽力从条目里找一张配图。找不到返回空串。"""
    # 1. media:thumbnail / media:content
    for tag in (f"{{{MEDIA}}}thumbnail", f"{{{MEDIA}}}content"):
        for el in item.findall(tag):
            url = el.get("url", "")
            if url:
                return url

    # 2. enclosure（podcast/图片附件）
    for el in item.findall("enclosure"):
        url = el.get("url", "")
        if el.get("type", "").startswith("image") or _looks_like_image(url):
            return url

    # 3. 正文 HTML 里的第一个 <img src>
    for tag in (f"{{{CONTENT}}}encoded", "description",
                f"{{{ATOM}}}content", f"{{{ATOM}}}summary"):
        el = item.find(tag)
        if el is None or not el.text:
            continue
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', el.text, re.I)
        if m and m.group(1).startswith("http"):
            return m.group(1)

    return ""


def _get_link(item) -> str:
    """取条目链接，兼容 RSS 的 <link> 文本和 Atom 的 <link href>。"""
    link = _get_text(item, "link")
    if link:
        return link.strip()
    for el in item.findall(f"{{{ATOM}}}link"):
        href = el.get("href", "")
        if href:
            return href.strip()
    for el in item.findall("link"):
        href = el.get("href", "")
        if href:
            return href.strip()
    return ""


def _parse_items(root) -> list:
    """兼容 RSS 2.0 的 <item> 和 Atom 的 <entry>。"""
    items = root.findall(".//item")
    if not items:
        items = root.findall(f".//{{{ATOM}}}entry")
    return items


# ============================================================
# 对外接口
# ============================================================

def fetch_feed(url: str, limit: int = 10) -> dict:
    """抓取单个 RSS 源，返回新闻列表。

    参数：
    - url：RSS 地址，必须在白名单内
    - limit：最多返回几条
    """
    if url not in RSS_WHITELIST:
        return {"error": f"RSS 源不在白名单，可用：{RSS_WHITELIST}"}

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True, headers=_HEADERS)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        name = SOURCE_NAMES.get(url, "")
        news = []
        for item in _parse_items(root)[:limit]:
            title = _get_text(item, "title")
            description = (
                _get_text(item, "description")
                or _get_text(item, "summary")
                or _get_text(item, f"{{{CONTENT}}}encoded")
            )
            news.append({
                "title": _clean_html(title),
                "link": _get_link(item),
                "summary": _clean_html(description)[:200],
                "image": _extract_image(item),
                "source": url,
                "source_name": name,
            })
        return {"url": url, "count": len(news), "news": news}

    except httpx.TimeoutException:
        return {"error": "请求超时"}
    except ET.ParseError as e:
        return {"error": f"XML 解析失败：{e}"}
    except Exception as e:
        return {"error": str(e)}


def fetch_all(limit_per_source: int = 8, max_total: int = 30) -> list[dict]:
    """并发抓取全部源，按源轮流交错合并去重后返回。

    单个源失败不影响整体（失败的直接跳过）。

    合并必须交错，不能按源顺序拼接：以前是一口气把第一个源的 8 条放进来、
    再放下一个源的 8 条，然后被 max_total 一刀截断——排在后面的源整段被切掉，
    页面上永远只看得到前几个源。轮流取一条就没这个问题。
    """
    def _one(src: dict) -> list[dict]:
        result = fetch_feed(src["url"], limit=limit_per_source)
        if "error" in result:
            return []
        return result["news"]

    with ThreadPoolExecutor(max_workers=min(8, len(RSS_SOURCES))) as pool:
        batches = list(pool.map(_one, RSS_SOURCES))

    merged: list[dict] = []
    seen: set[str] = set()

    # 第 1 轮每个源各取 1 条，第 2 轮再各取 1 条……直到取满 max_total 或全部取空
    for index in range(limit_per_source):
        for batch in batches:
            if index >= len(batch):
                continue
            item = batch[index]
            key = item.get("link") or item.get("title")
            if not key or not item.get("title") or key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= max_total:
                return merged
    return merged
