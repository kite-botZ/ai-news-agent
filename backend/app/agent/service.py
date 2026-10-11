"""Agent 业务封装：为指定用户生成简报。

支持两种模式：
- generate_brief_for_user：一次性返回（同步，接口用）
- generate_brief_stream：流式返回（SSE，前端用）
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Generator

from app.agent.prompts import NEWS_AGENT_PROMPT
from app.agent.react import run_react, run_react_stream_realtime
from app.config import DATA_DIR
from app.users import list_users

USERS_DIR = Path(DATA_DIR) / "users"


def _build_context(username: str) -> tuple[Path, str, str, str]:
    """构造上下文。返回 (user_dir, today, now_ts, full_message)。"""
    user_dir = USERS_DIR / username
    if not user_dir.exists():
        raise ValueError(f"用户不存在：{username}")

    today = datetime.now().strftime("%Y-%m-%d")
    now_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    full_message = (
        f"[当前用户：{username}]\n"
        f"[用户目录：data/users/{username}/]\n\n"
        f"请为用户名 {username} 生成今天（{today}）的新闻简报。\n\n"
        f"重要：所有工具路径都相对于该用户的目录，不要加任何前缀。"
        f"比如读偏好用 'preferences.json'，"
        f"存简报到 'briefs/{now_ts}.md'。\n\n"
        f"生成简报时，请用这个精确的文件名，避免同一天生成多次时互相覆盖。"
    )

    return user_dir, today, now_ts, full_message


def _find_saved_path(user_dir: Path, today: str) -> str | None:
    """找今天最新生成的简报文件。"""
    briefs_dir = user_dir / "briefs"
    if not briefs_dir.exists():
        return None
    today_files = sorted(
        [f for f in briefs_dir.glob(f"{today}*.md")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not today_files:
        return None
    return str(today_files[0].relative_to(Path(DATA_DIR)))


def _update_last_generated(user_dir: Path, today: str) -> None:
    """更新用户偏好里的 last_generated 字段。"""
    prefs_file = user_dir / "preferences.json"
    if not prefs_file.exists():
        return
    try:
        prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
        prefs["last_generated"] = today
        prefs_file.write_text(
            json.dumps(prefs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        # 偏好更新失败不影响主流程
        pass


# ============================================================
# 流式：SSE 生成简报
# ============================================================

def generate_brief_stream(username: str) -> Generator[str, None, None]:
    """流式生成简报，每步 yield SSE 事件。

    事件格式：data: {"type": "...", "content": "..."}\n\n

    事件类型：
    - status    ：状态提示
    - text      ：模型输出的文字片段（打字机效果）
    - progress  ：工具调用进度（人话）
    - done      ：生成完成，带 saved_path / date / iterations
    - error     ：错误
    """

    def sse(event_type: str, **kwargs) -> str:
        data = {"type": event_type, **kwargs}
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        user_dir, today, now_ts, full_message = _build_context(username)
    except ValueError as e:
        yield sse("error", content=str(e))
        return

    yield sse("status", content=f"✅ 开始为 {username} 生成简报…")

    tool_count = 0
    iterations = 0

    try:
        for event in run_react_stream_realtime(
                system_prompt=NEWS_AGENT_PROMPT,
                user_message=full_message,
                sandbox_dir=user_dir,
        ):
            etype = event.get("type")

            if etype == "status":
                yield sse("status", content=event["content"])

            elif etype == "text":
                # 模型输出的文字片段 → 立即转发给前端（打字机效果）
                yield sse("text", content=event["content"])

            elif etype == "tool_call":
                tool_count += 1
                name = event["name"]
                friendly = {
                    "read_file": "📖 正在读取偏好…",
                    "fetch_rss": "📰 正在拉取新闻源…",
                    "write_file": "💾 正在保存简报…",
                    "list_dir": "📂 正在查看目录…",
                    "search_content": "🔍 正在搜索内容…",
                    "bash": "⚙️ 正在执行命令…",
                }.get(name, f"🔧 正在调用 {name}…")
                yield sse("progress", content=friendly, tool=name)

            elif etype == "tool_result":
                name = event["name"]
                result = event["result"]
                if isinstance(result, dict) and "error" in result:
                    yield sse(
                        "progress",
                        content=f"⚠️ {name} 失败：{str(result['error'])[:60]}",
                        tool=name,
                    )
                else:
                    if name == "fetch_rss":
                        yield sse(
                            "progress",
                            content=f"   拿到 {result.get('count', 0)} 条新闻",
                            tool=name,
                        )
                    elif name == "write_file":
                        yield sse(
                            "progress",
                            content=f"   已保存到 {result.get('path', '')}",
                            tool=name,
                        )

            elif etype == "iterations":
                iterations = event.get("count", 0)

            elif etype == "done":
                content = event.get("content", "")
                saved_path = _find_saved_path(user_dir, today)

                # 更新偏好里的 last_generated
                _update_last_generated(user_dir, today)

                yield sse(
                    "done",
                    content=content,
                    date=today,
                    saved_path=saved_path,
                    tool_count=tool_count,
                    iterations=iterations,
                )

            elif etype == "error":
                yield sse("error", content=event.get("content", "未知错误"))

    except Exception as e:
        yield sse("error", content=f"Agent 执行失败：{e}")


# ============================================================
# 同步：给 /docs 用的简单版
# ============================================================

def generate_brief_for_user(username: str) -> dict:
    """同步生成（保留，用于测试）。"""
    user_dir, today, now_ts, full_message = _build_context(username)

    result = run_react(
        system_prompt=NEWS_AGENT_PROMPT,
        user_message=full_message,
        sandbox_dir=user_dir,
    )

    saved_path = _find_saved_path(user_dir, today)
    _update_last_generated(user_dir, today)

    return {
        "username": username,
        "date": today,
        "content": result["answer"],
        "tool_calls": result["tool_calls"],
        "iterations": result["iterations"],
        "saved_path": saved_path,
    }


# ============================================================
# 批量：定时任务调用
# ============================================================

def generate_all_briefs() -> list[dict]:
    """为所有用户各生成一份今天的简报。

    单个用户失败不影响其他用户，失败信息记在返回值里。
    """
    results = []
    for username in list_users():
        try:
            r = generate_brief_for_user(username)
            results.append({
                "username": username,
                "ok": True,
                "saved_path": r.get("saved_path"),
            })
        except Exception as e:
            results.append({"username": username, "ok": False, "error": str(e)})
    return results