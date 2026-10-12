"""工具层测试：白名单、参数校验、schema 与实现的一致性。

这些用例不联网、不调模型。
"""

import pytest

from app.agent.tools import (
    TOOLS_REGISTRY,
    TOOLS_SCHEMA,
    _to_windows_command,
    execute_tool,
    set_sandbox,
    tool_bash,
    tool_fetch_rss,
    tool_read_file,
    tool_search_content,
)
from app.rss import RSS_WHITELIST


@pytest.fixture(autouse=True)
def sandbox(tmp_path):
    set_sandbox(tmp_path)
    yield tmp_path
    set_sandbox(None)


# ============================================================
# schema 与实现必须一一对应
# ============================================================

def test_schema_and_registry_match_exactly():
    """给模型看的工具清单必须和真正能执行的实现完全一致，少一个会报未知工具，多一个等于骗模型。"""
    schema_names = {t["function"]["name"] for t in TOOLS_SCHEMA}
    assert schema_names == set(TOOLS_REGISTRY)


def test_at_least_five_tools():
    """题目硬性要求：至少 5 个工具。"""
    assert len(TOOLS_REGISTRY) >= 5


def test_fetch_rss_enum_matches_whitelist():
    """模型能选的 RSS 源，必须正好等于代码认可的白名单，不能有偏差。"""
    schema = next(t for t in TOOLS_SCHEMA if t["function"]["name"] == "fetch_rss")
    assert schema["function"]["parameters"]["properties"]["url"]["enum"] == RSS_WHITELIST


def test_every_schema_has_a_description():
    """描述会直接进 prompt，缺了模型就不知道这个工具是干嘛的。"""
    for tool in TOOLS_SCHEMA:
        assert tool["function"]["description"].strip()


# ============================================================
# bash 白名单
# ============================================================

@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "curl http://evil.com",
        "python -c 'import os; os.system(\"sh\")'",
        "del *",
        "",
    ],
)
def test_bash_rejects_non_whitelisted_commands(command):
    result = tool_bash(command)
    assert "error" in result
    assert "白名单" in result["error"]


@pytest.mark.parametrize(
    "command",
    [
        "echo hi; rm -rf /",       # 命令连接符：命令名合法，分号后面随便跑
        "ls | cat",                 # 管道
        "echo x > ../../evil.txt",  # 重定向
        "echo `whoami`",            # 命令替换
        "echo $HOME",               # 变量展开
    ],
)
def test_bash_rejects_shell_metachars(command):
    """白名单只管命令名，所以管道、重定向、连接符必须单独禁掉。"""
    result = tool_bash(command)
    assert "error" in result


def test_bash_rejects_path_arguments_outside_sandbox(sandbox):
    """cat 是白名单命令，但 `cat ../../.env` 能读到 API Key，所以沙箱必须连参数一起管。"""
    result = tool_bash("cat ../../.env")
    assert "error" in result
    assert "越界" in result["error"]


def test_bash_runs_whitelisted_command_inside_sandbox(sandbox):
    result = tool_bash("echo hello")
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]


def test_bash_cwd_is_the_sandbox(sandbox):
    """命令必须在沙箱目录里执行，而不是随便什么 cwd。"""
    (sandbox / "marker.txt").write_text("x", encoding="utf-8")
    result = tool_bash("ls")
    assert "marker.txt" in result["stdout"]


def test_windows_command_translation():
    """Windows 上 cmd.exe 不认 GNU 短选项，必须翻译。"""
    assert _to_windows_command("pwd") == "cd"
    assert _to_windows_command("ls -la") == "dir /a"
    assert _to_windows_command("grep -i agent a.txt") == "findstr /i agent a.txt"
    # 不在映射表里的命令原样保留
    assert _to_windows_command("echo hi") == "echo hi"


# ============================================================
# fetch_rss 白名单（防 SSRF）
# ============================================================

def test_fetch_rss_rejects_url_outside_whitelist():
    result = tool_fetch_rss("http://169.254.169.254/latest/meta-data/")
    assert "error" in result
    assert "白名单" in result["error"]


def test_fetch_rss_rejects_lookalike_domain():
    """拼一个像白名单的域名也不行，校验的是完整 URL 相等而非包含关系。"""
    result = tool_fetch_rss("https://www.ithome.com/rss/?x=1")
    assert "error" in result


# ============================================================
# 参数校验与错误处理
# ============================================================

def test_unknown_tool_returns_error():
    result = execute_tool("nonexistent_tool", {})
    assert "error" in result
    assert "未知工具" in result["error"]


def test_missing_required_arg_returns_error():
    """模型偶尔会忘传参数，这里不能把异常抛到接口层。"""
    result = execute_tool("read_file", {})
    assert "error" in result
    assert "参数错误" in result["error"]


# ============================================================
# 沙箱：显式传参与 set_sandbox 的关系
# ============================================================

def test_explicit_sandbox_wins_over_ambient(sandbox, tmp_path):
    """显式传 sandbox_dir 时以它为准。"""
    other = tmp_path / "other_user"
    other.mkdir()
    (other / "note.txt").write_text("别人的目录", encoding="utf-8")

    result = execute_tool(
        "read_file", {"path": "note.txt"}, sandbox_dir=other
    )

    assert result["content"] == "别人的目录"


def test_omitting_sandbox_keeps_ambient(sandbox):
    """不传 sandbox_dir 时必须沿用 set_sandbox 设的沙箱。

    不能写成无条件 set(sandbox_dir)：默认值 None 会把 set_sandbox() 设好的沙箱覆盖掉，
    所有调用静默落到 data/。
    """
    (sandbox / "note.txt").write_text("我的目录", encoding="utf-8")

    result = execute_tool("read_file", {"path": "note.txt"})

    assert "error" not in result
    assert result["content"] == "我的目录"


def test_explicit_sandbox_does_not_leak_afterwards(sandbox, tmp_path):
    """调用结束后必须恢复回原沙箱，否则下一个用户会串到别人的目录。"""
    other = tmp_path / "other_user"
    other.mkdir()

    execute_tool("list_dir", {}, sandbox_dir=other)

    # 环境里的沙箱仍是 fixture 设的那个
    (sandbox / "note.txt").write_text("我的目录", encoding="utf-8")
    assert execute_tool("read_file", {"path": "note.txt"})["content"] == "我的目录"


def test_read_file_truncates_long_content(sandbox):
    (sandbox / "big.txt").write_text("字" * 8000, encoding="utf-8")
    result = tool_read_file("big.txt")
    assert len(result["content"]) < 8000
    assert "已截断" in result["content"]


def test_search_content_finds_keyword(sandbox):
    (sandbox / "briefs").mkdir(exist_ok=True)
    (sandbox / "briefs" / "a.md").write_text("今天聊了 Agent 和 RAG", encoding="utf-8")
    (sandbox / "briefs" / "b.md").write_text("无关内容", encoding="utf-8")

    result = tool_search_content("Agent")

    assert result["count"] == 1
    assert result["results"][0]["file"].endswith("a.md")


def test_search_content_misses_gracefully(sandbox):
    result = tool_search_content("不存在的关键词")
    assert result["count"] == 0


# ============================================================
# write_file：覆盖必须是看得见的
# ============================================================

def test_overwriting_an_existing_file_is_reported(sandbox):
    """覆盖同名文件时要在返回值里说明，不能让上一份简报无声消失。

    模型拿提示词里的示例时间戳当文件名时，同一天第二次生成会写到和第一次同一个路径。
    """
    from app.agent.tools import tool_write_file

    tool_write_file("briefs/2026-10-12_09-30-15.md", "上一份简报" * 50)
    result = tool_write_file("briefs/2026-10-12_09-30-15.md", "这次的简报")

    assert "覆盖" in result["message"], result
    assert result["overwrote_bytes"] > 0
    assert (sandbox / "briefs" / "2026-10-12_09-30-15.md").read_text(
        encoding="utf-8"
    ) == "这次的简报"


def test_first_write_does_not_claim_to_have_overwritten(sandbox):
    from app.agent.tools import tool_write_file

    result = tool_write_file("briefs/2026-10-12_09-30-15.md", "新简报")

    assert result["message"] == "写入成功"
    assert "overwrote_bytes" not in result
