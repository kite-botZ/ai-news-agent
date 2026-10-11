"""Agent 业务层测试：简报落盘的「找文件 + 兜底」逻辑。

这两条逻辑都在兜同一个真实故障：**模型偶尔不调 write_file**。实测跑 6 次会出现 1 次：
模型读完新闻，直接把简报当成对话回复吐出来，文件一个没写。

- _find_saved_path(since=...)  防止把上一次的旧简报当成本次生成的结果
- _persist_fallback            实在没写，后端替它落盘

这两个错误都是「静默」的：用户看到一份内容正常的简报，但它是旧的、或者根本没入库。
所以要用测试钉死。
"""

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
