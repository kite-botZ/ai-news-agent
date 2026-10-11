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
    """给模型看的工具清单，必须和真正能执行的实现完全一致。

    少一个 → 模型调了会报「未知工具」；多一个 → 等于在骗模型。
    """
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
    """最有意思的一条：cat 是合法命令，但 `cat ../../.env` 能读到 API Key。

    沙箱必须连参数一起管，否则白名单就是个摆设。
    """
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
    """Windows 上 cmd.exe 不认 GNU 短选项，必须翻译（这是个真实踩过的坑）。"""
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
    """拼一个像白名单的域名也不行——校验的是完整 URL 相等，不是包含关系。"""
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
