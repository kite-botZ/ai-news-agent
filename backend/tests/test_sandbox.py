"""沙箱隔离测试。

README 里写了「所有文件操作限制在 data/users/<username>/ 内，用 resolve() + relative_to()
双重校验防目录穿越」。这个文件就是把那句话变成可执行的证据。

思路：开一个临时目录当沙箱，然后从里面往外爬，看爬不爬得出去。
"""

import pytest

from app.agent.tools import (
    _safe_path,
    set_sandbox,
    tool_list_dir,
    tool_read_file,
    tool_write_file,
)


@pytest.fixture(autouse=True)
def sandbox(tmp_path):
    """每个用例一个独立的临时沙箱，跑完恢复默认，避免用例之间互相影响。"""
    (tmp_path / "preferences.json").write_text(
        '{"keywords": ["AI", "大模型"]}', encoding="utf-8"
    )
    (tmp_path / "briefs").mkdir()

    set_sandbox(tmp_path)
    yield tmp_path
    set_sandbox(None)


# ============================================================
# 正常路径：沙箱内该能读能写
# ============================================================

def test_read_inside_sandbox_works(sandbox):
    result = tool_read_file("preferences.json")
    assert "大模型" in result["content"]


def test_write_inside_sandbox_works(sandbox):
    result = tool_write_file("briefs/2026-10-12.md", "# 简报")
    assert result["message"] == "写入成功"
    assert (sandbox / "briefs" / "2026-10-12.md").read_text(encoding="utf-8") == "# 简报"


def test_write_creates_missing_parent_dirs(sandbox):
    tool_write_file("briefs/2026/10/x.md", "hi")
    assert (sandbox / "briefs" / "2026" / "10" / "x.md").exists()


def test_list_dir_only_lists_sandbox_contents(sandbox):
    result = tool_list_dir(".")
    assert {item["name"] for item in result["items"]} == {"preferences.json", "briefs"}


# ============================================================
# 攻击路径：往外爬必须被挡
# ============================================================

def test_relative_traversal_is_blocked(sandbox):
    result = tool_read_file("../../../../etc/passwd")
    assert "error" in result
    assert "越界" in result["error"]


def test_traversal_cannot_write_outside_sandbox(sandbox):
    """最关键的一条：不只是报错，文件必须真的没被创建在外面。"""
    escaped = sandbox.parent / "escaped.txt"

    result = tool_write_file("../escaped.txt", "pwned")

    assert "error" in result
    assert not escaped.exists()


def test_absolute_path_is_blocked(sandbox, tmp_path):
    """绝对路径会覆盖掉沙箱前缀（pathlib 的行为），必须单独挡。"""
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    result = tool_read_file(str(outside))

    assert "error" in result
    assert "secret" not in str(result)


def test_nested_traversal_that_lands_back_inside_is_ok(sandbox):
    """绕一圈回到沙箱内的路径不算越界——校验的是终点，不是路径写法。"""
    result = tool_read_file("briefs/../preferences.json")
    assert "keywords" in result["content"]


def test_safe_path_raises_directly(sandbox):
    """_safe_path 本身抛 ValueError，上层工具把它转成 error 字段。"""
    with pytest.raises(ValueError, match="越界"):
        _safe_path("../outside.txt")
