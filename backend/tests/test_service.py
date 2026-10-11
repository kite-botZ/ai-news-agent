"""Agent 业务层测试：简报落盘的「找文件 + 兜底」逻辑。

这两条逻辑都在兜同一个真实故障：**模型偶尔不调 write_file**。实测跑 6 次会出现 1 次：
模型读完新闻，直接把简报当成对话回复吐出来，文件一个没写。

- _find_saved_path(since=...)  防止把上一次的旧简报当成本次生成的结果
- _persist_fallback            实在没写，后端替它落盘

这两个错误都是「静默」的：用户看到一份内容正常的简报，但它是旧的、或者根本没入库。
所以要用测试钉死。
"""

import json
import os
import re
import time

import pytest

from app.agent import service
from app.users import _BRIEF_STEM_PATTERN

TODAY = "2026-10-12"


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    """把数据根目录指到临时目录，别碰真实的 data/。"""
    monkeypatch.setattr(service, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(service, "USERS_DIR", tmp_path / "users")
    d = tmp_path / "users" / "alice"
    (d / "briefs").mkdir(parents=True)
    return d


def _write_brief(user_dir, stem: str, content: str = "正文"):
    f = user_dir / "briefs" / f"{stem}.md"
    f.write_text(content, encoding="utf-8")
    return f


def _age(path, seconds: float):
    """把文件的 mtime 往前推。"""
    past = time.time() - seconds
    os.utime(path, (past, past))


# ============================================================
# _find_saved_path
# ============================================================

def test_ignores_brief_generated_before_this_run(user_dir):
    """上一次生成的旧简报不能被当成本次的结果。"""
    _age(_write_brief(user_dir, f"{TODAY}_09-00-00", "上午生成的旧简报"), 3600)

    since = time.time()
    assert service._find_saved_path(user_dir, TODAY, since=since) is None


def test_finds_brief_written_during_this_run(user_dir):
    _age(_write_brief(user_dir, f"{TODAY}_09-00-00", "旧简报"), 3600)

    since = time.time()
    _write_brief(user_dir, f"{TODAY}_10-00-00", "刚生成的简报")

    found = service._find_saved_path(user_dir, TODAY, since=since)
    assert found is not None
    assert found.endswith(f"{TODAY}_10-00-00.md")


def test_returns_the_newest_when_several_are_new(user_dir):
    since = time.time()
    old = _write_brief(user_dir, f"{TODAY}_10-00-00", "先写的")
    new = _write_brief(user_dir, f"{TODAY}_10-00-01", "后写的")
    _age(old, 5)

    found = service._find_saved_path(user_dir, TODAY, since=since)
    assert found is not None
    assert "10-00-01" in found
    assert os.path.basename(found) == new.name


def test_ignores_other_days(user_dir):
    since = time.time()
    _write_brief(user_dir, "2026-10-11_23-59-59", "昨天的")

    assert service._find_saved_path(user_dir, TODAY, since=since) is None


def test_missing_briefs_dir_is_not_an_error(user_dir):
    (user_dir / "briefs").rmdir()
    assert service._find_saved_path(user_dir, TODAY, since=time.time()) is None


# ============================================================
# _persist_fallback
# ============================================================

def test_fallback_saves_content_the_model_forgot_to_write(user_dir):
    content = "# 每日新闻简报\n\n## 今日要点\n" + "内容" * 100

    saved = service._persist_fallback(user_dir, content)

    assert saved is not None
    written = user_dir / "briefs" / os.path.basename(saved)
    assert written.exists()
    assert written.read_text(encoding="utf-8") == content


def test_fallback_filename_is_a_valid_brief_id(user_dir):
    """前端拿这个 id 去调 GET /briefs/{id}，格式必须能被 users 模块的校验放行。"""
    saved = service._persist_fallback(user_dir, "内容" * 100)

    assert saved is not None
    stem = os.path.splitext(os.path.basename(saved))[0]
    assert re.match(_BRIEF_STEM_PATTERN, stem), f"不合法的简报 id：{stem}"


def test_fallback_skips_chit_chat(user_dir):
    """太短的内容是「已生成」之类的客套话，不是简报，不该落盘。"""
    assert service._persist_fallback(user_dir, "今天的简报已生成并保存。") is None
    assert service._persist_fallback(user_dir, "") is None
    assert service._persist_fallback(user_dir, None) is None
    assert list((user_dir / "briefs").glob("*.md")) == []


def test_fallback_creates_briefs_dir_if_missing(user_dir):
    (user_dir / "briefs").rmdir()

    saved = service._persist_fallback(user_dir, "内容" * 100)

    assert saved is not None
    assert (user_dir / "briefs" / os.path.basename(saved)).exists()


# ============================================================
# SSE 事件流：成功要走 done、失败要走 error
# ============================================================

def _consume(username="alice"):
    """跑一遍流式生成，把 SSE 解析成事件列表。"""
    events = []
    for chunk in service.generate_brief_stream(username):
        if chunk.startswith("data:"):
            events.append(json.loads(chunk[5:].strip()))
    return events


@pytest.fixture
def fake_react(monkeypatch):
    """把真正的 Agent 循环换掉，只关心 service 怎么组装 SSE 事件。

    这里不跑模型，也就顺手绕开了真实的写文件 / 拉 RSS —— 测的是「事件流对不对」。
    """

    def install(*events, side_effect=None):
        def gen(**_kwargs):
            if side_effect is not None:
                side_effect()
            yield from events

        monkeypatch.setattr(service, "run_react_stream_realtime", gen)

    return install


def test_stream_emits_done_with_brief_id_when_file_was_written(user_dir, fake_react):
    def write_brief():
        (user_dir / "briefs" / f"{TODAY}_10-00-00.md").write_text(
            "正文" * 100, encoding="utf-8"
        )

    fake_react(
        {"type": "done", "content": "今天的简报已生成并保存。"},
        side_effect=write_brief,
    )

    events = _consume()
    done = [e for e in events if e["type"] == "done"]

    assert len(done) == 1
    assert done[0]["brief_id"] == "2026-10-12_10-00-00"
    assert "error" not in [e["type"] for e in events]


def test_stream_reports_error_when_model_produced_nothing(user_dir, fake_react):
    """模型既没写文件、回复里也只有空白时，必须报错。

    以前这种情况照样发 done，前端弹出一个**空白**弹窗，用户完全不知道发生了什么。
    模型撞到 MAX_ITERATIONS 时就是这个样子（final_answer 是空串或纯空白）。
    """
    fake_react({"type": "done", "content": "\n\n"})

    events = _consume()
    types = [e["type"] for e in events]

    assert "error" in types, "什么都没产出却报了成功"
    assert "done" not in types
    assert "没有产出内容" in next(e["content"] for e in events if e["type"] == "error")


def test_stream_flags_a_write_that_overwrote_an_existing_brief(user_dir, fake_react):
    """覆盖同名简报必须在进度里报出来。

    文件名带秒级时间戳，正常永远不会撞。一旦撞上，就说明模型没照抄任务消息
    给的文件名（八成是拿提示词里的示例时间戳顶替了），而这一撞会**盖掉上一份简报**。
    """
    fake_react(
        {"type": "tool_call", "name": "write_file", "args": {}},
        {"type": "tool_result", "name": "write_file", "result": {
            "path": "briefs/2026-10-12_09-30-15.md",
            "size": 700,
            "message": "写入成功（覆盖了已存在的同名文件，原 2100 字节）",
            "overwrote_bytes": 2100,
        }},
        {"type": "done", "content": "今天的简报已生成并保存。"},
    )

    progress = [
        e["content"] for e in _consume() if e["type"] == "progress"
    ]

    assert any("覆盖" in line for line in progress), progress


def test_stream_does_not_cry_wolf_on_a_normal_write(user_dir, fake_react):
    fake_react(
        {"type": "tool_result", "name": "write_file", "result": {
            "path": "briefs/2026-10-12_09-30-15.md",
            "size": 700,
            "message": "写入成功",
        }},
        {"type": "done", "content": "今天的简报已生成并保存。"},
    )

    progress = [e["content"] for e in _consume() if e["type"] == "progress"]

    assert any("已保存到" in line for line in progress), progress
    assert not any("覆盖" in line for line in progress), progress


def test_failed_generation_does_not_mark_last_generated(user_dir, fake_react):
    """没生成成功就不能把 last_generated 标成今天。

    标了的话，用户下次打开首页会看到「今天已生成」，以为简报存好了——
    但历史里根本没有。又是一个静默错误。
    """
    prefs = user_dir / "preferences.json"
    prefs.write_text(
        json.dumps({"keywords": [], "last_generated": None}), encoding="utf-8"
    )

    fake_react({"type": "done", "content": "\n\n"})
    _consume()

    assert (
        json.loads(prefs.read_text(encoding="utf-8"))["last_generated"] is None
    ), "生成失败了却标记成已生成"
