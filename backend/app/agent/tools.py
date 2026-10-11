"""Agent 工具定义与执行。

6 个工具：
1. list_dir         - 列出目录内容
2. read_file        - 读取文件
3. search_content   - 在目录下按关键词搜索文件内容
4. write_file       - 写入文件
5. bash             - 执行 shell 命令（白名单限制）
6. fetch_rss        - 拉取 RSS 新闻

安全设计：
- 所有文件操作限制在 data/ 目录内（沙箱）
- bash 命令只允许白名单内的命令
- fetch_rss 只允许白名单内的 RSS 源
"""

import contextvars
import subprocess
import sys
from pathlib import Path

from app.config import DATA_DIR
from app.rss import RSS_WHITELIST, fetch_feed

# 沙箱根目录（默认 data/）
SANDBOX_DIR = Path(DATA_DIR)

# 当前会话的用户目录（生成简报时会被设置为 data/users/<username>/）
# 使用 contextvars 保证并发请求下每个请求的沙箱互相隔离
_current_sandbox: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "current_sandbox", default=None
)


def set_sandbox(sandbox_dir: Path | None):
    """设置当前会话的沙箱根目录。None 表示回到默认 data/。"""
    _current_sandbox.set(sandbox_dir)


def _get_sandbox() -> Path:
    """获取当前沙箱根目录。"""
    sb = _current_sandbox.get()
    return sb if sb else SANDBOX_DIR


def _safe_path(path: str) -> Path:
    """把相对路径转成沙箱内的绝对路径，防止目录穿越。"""
    sandbox = _get_sandbox().resolve()
    p = (sandbox / path).resolve()
    try:
        p.relative_to(sandbox)
    except ValueError:
        raise ValueError(f"路径越界：{path}")
    return p


# ============================================================
# 工具 1：list_dir
# ============================================================

def tool_list_dir(path: str = ".") -> dict:
    """列出目录内容。"""
    try:
        target = _safe_path(path)
        if not target.exists():
            return {"error": f"路径不存在：{path}"}
        if not target.is_dir():
            return {"error": f"不是目录：{path}"}

        items = []
        for item in sorted(target.iterdir()):
            items.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            })
        return {"path": path, "items": items}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 工具 2：read_file
# ============================================================

def tool_read_file(path: str) -> dict:
    """读取文件内容。"""
    try:
        target = _safe_path(path)
        if not target.exists():
            return {"error": f"文件不存在：{path}"}
        if not target.is_file():
            return {"error": f"不是文件：{path}"}

        content = target.read_text(encoding="utf-8")
        # 超过 5000 字截断，防止撑爆上下文
        if len(content) > 5000:
            content = content[:5000] + f"\n\n...（已截断，原文共 {len(content)} 字）"
        return {"path": path, "content": content}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 工具 3：search_content
# ============================================================

def tool_search_content(keyword: str, dir: str = ".") -> dict:
    """在目录下按关键词搜索文件内容。"""
    try:
        target = _safe_path(dir)
        if not target.exists():
            return {"error": f"目录不存在：{dir}"}

        results = []
        for file_path in target.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
                if keyword in text:
                    matched_lines = [
                        line.strip() for line in text.splitlines()
                        if keyword in line
                    ][:5]
                    results.append({
                        "file": str(file_path.relative_to(_get_sandbox())),
                        "matches": matched_lines,
                    })
                    if len(results) >= 10:
                        break
            except (UnicodeDecodeError, PermissionError):
                continue

        return {"keyword": keyword, "count": len(results), "results": results}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 工具 4：write_file
# ============================================================

def tool_write_file(path: str, content: str) -> dict:
    """写入文件（覆盖）。"""
    try:
        target = _safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": path, "size": len(content), "message": "写入成功"}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 工具 5：bash
# ============================================================

# 命令白名单（同时支持 Windows 和 Linux）
_BASH_WHITELIST = [
    # Linux 命令
    "ls", "cat", "echo", "pwd", "date", "wc", "head", "tail", "grep", "find",
    # Windows 命令
    "dir", "type", "cd", "where", "findstr",
]

# Windows 上把常见 Linux 命令映射到等价命令
_WINDOWS_CMD_MAP = {
    "ls": "dir",
    "cat": "type",
    "pwd": "cd",
    "grep": "findstr",
}

# GNU 短选项 → cmd.exe 等价选项。
# 光换命令名是不够的：cmd 的 findstr 只认 /i 不认 -i，dir 根本没有 -l。
_WINDOWS_FLAG_MAP = {
    "-i": "/i",
    "-l": "",      # dir 无此选项，直接丢掉
    "-a": "/a",
    "-la": "/a",
    "-al": "/a",
}


def _to_windows_command(command: str) -> str:
    """把 Linux 风格的命令翻译成 cmd.exe 能跑的写法。

    只翻译白名单内、且需要改写的命令；其余原样返回。
    """
    parts = command.strip().split()
    if not parts:
        return command

    mapped = _WINDOWS_CMD_MAP.get(parts[0])
    if not mapped:
        return command

    # cmd 里不带参数的 `cd` 就是打印当前目录，正好等价于 pwd
    if mapped == "cd":
        return "cd"

    args = [_WINDOWS_FLAG_MAP.get(a, a) for a in parts[1:]]
    args = [a for a in args if a]          # 丢掉被翻译没的选项（如 -l）
    return " ".join([mapped, *args])


# 管道 / 重定向 / 命令连接符 / 变量展开。
# 这个工具只用来「看一眼目录」，用不到这些；放开的代价是白名单形同虚设——
# `echo hi; rm -rf /` 的命令名是合法的 echo，但分号后面想跑什么就跑什么。
_SHELL_METACHARS = (";", "|", "&", ">", "<", "`", "$", "%", "\n", "\r")


def _arguments_stay_in_sandbox(command: str) -> bool:
    """检查命令参数里的路径有没有爬出沙箱。

    白名单只管得住命令名，管不住参数：`cat ../../.env` 的命令名是合法的 cat，
    但参数能读到沙箱外面（比如 backend/.env 里的 API Key）。
    所以每个非选项的 token 都过一遍 _safe_path —— 不是路径的词（搜索关键字之类）
    会被当成沙箱内的相对路径，无害地通过。
    """
    for token in command.split()[1:]:
        if token.startswith("-"):
            continue
        # Windows 风格的选项长这样：/i /a，很短且不含路径分隔符
        if token.startswith("/") and len(token) <= 3:
            continue
        try:
            _safe_path(token)
        except ValueError:
            return False
    return True


def tool_bash(command: str) -> dict:
    """执行 shell 命令（白名单 + 参数沙箱 + 禁止管道）。"""
    parts = command.strip().split()
    cmd_name = parts[0] if parts else ""

    if cmd_name not in _BASH_WHITELIST:
        return {"error": f"命令 {cmd_name} 不在白名单，仅允许：{_BASH_WHITELIST}"}

    for char in _SHELL_METACHARS:
        if char in command:
            return {
                "error": f"命令里不允许出现 {char!r}（管道 / 重定向 / 命令连接符）"
            }

    if not _arguments_stay_in_sandbox(command):
        return {"error": "命令参数越界：不允许访问沙箱目录以外的路径"}

    if sys.platform == "win32":
        command = _to_windows_command(command)

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(_get_sandbox()),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "命令超时（10 秒）"}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 工具 6：fetch_rss（拉取 RSS 新闻）
# ============================================================

# 模型在写简报时真正用得上的字段。
# image 是给前端卡片用的长 URL，source 和 source_name 内容重复——都裁掉。
# 这些字段会留在消息历史里，之后每一轮都要重新 prefill，裁掉能省不少时间。
_NEWS_FIELDS_FOR_LLM = ("title", "link", "summary", "source_name")


def tool_fetch_rss(url: str, limit: int = 5) -> dict:
    """拉取 RSS 源，返回新闻列表（只保留模型用得上的字段）。

    抓取与解析逻辑统一放在 app/rss.py，这里只做转发 + 瘦身，
    保证 Agent 工具和 /api/news 接口用的是同一套实现。

    参数：
    - url：RSS 地址，必须在白名单内
    - limit：最多返回几条
    """
    result = fetch_feed(url, limit=limit)
    if "error" in result:
        return result

    news = [
        {key: item[key] for key in _NEWS_FIELDS_FOR_LLM}
        for item in result["news"]
    ]
    return {"url": result["url"], "count": len(news), "news": news}


# ============================================================
# 工具 schema（给 LLM 看，OpenAI 兼容格式）
# ============================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出指定目录下的所有文件和子目录。用于了解当前有哪些数据文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于当前用户目录的路径，默认 '.' 表示根目录",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定文件的全部内容。用于查看用户的订阅偏好、历史简报等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于当前用户目录的文件路径",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_content",
            "description": "在目录下搜索包含指定关键词的文件。用于查找历史简报中是否出现过某个主题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "要搜索的关键词",
                    },
                    "dir": {
                        "type": "string",
                        "description": "搜索的目录，默认 '.' 表示根目录",
                    },
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "把内容写入指定文件（覆盖原内容）。用于保存生成的新闻简报、更新用户偏好等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对于当前用户目录的文件路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整内容",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "执行 shell 命令，用于辅助查看目录内容。"
                "仅允许白名单内的命令："
                "ls、cat、echo、pwd、date、wc、head、tail、grep、find、"
                "dir、type、cd、where、findstr。"
                "不支持管道、重定向和命令连接符（| > ; &），"
                "参数里的路径也不能超出当前用户目录。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的命令，如 'ls -la'",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_rss",
            "description": "拉取 RSS 新闻源，获取最新新闻列表。用于搜集 AI 相关新闻。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "RSS 源地址",
                        "enum": RSS_WHITELIST,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回几条新闻，默认 5",
                    },
                },
                "required": ["url"],
            },
        },
    },
]


# ============================================================
# 执行入口
# ============================================================

TOOLS_REGISTRY = {
    "list_dir": tool_list_dir,
    "read_file": tool_read_file,
    "search_content": tool_search_content,
    "write_file": tool_write_file,
    "bash": tool_bash,
    "fetch_rss": tool_fetch_rss,
}


def execute_tool(name: str, args: dict) -> dict:
    """执行一个工具，异常统一返回 error。"""
    fn = TOOLS_REGISTRY.get(name)
    if not fn:
        return {"error": f"未知工具：{name}"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"参数错误：{e}"}
    except Exception as e:
        return {"error": f"执行失败：{e}"}