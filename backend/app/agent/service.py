"""Agent 业务封装：为指定用户生成简报。

generate_brief_stream 是前端用的 SSE 流式版，generate_brief_for_user 是同步版。
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Generator

from app.agent.prompts import NEWS_AGENT_PROMPT
from app.agent.react import run_react, run_react_stream_realtime
from app.config import DATA_DIR

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


def _find_saved_path(user_dir: Path, today: str, since: float | None = None) -> str | None:
    """找今天最新生成的简报文件。since 是本次生成的开始时间戳。

    since 必须传：模型偶尔不调 write_file，这时只按"今天最新"来找会捞到上一次的
    简报，当成这次的结果返回。
    """
    briefs_dir = user_dir / "briefs"
    if not briefs_dir.exists():
        return None
    files = [f for f in briefs_dir.glob(f"{today}*.md")]
    if since is not None:
        # 容 1 秒误差（文件系统 mtime 精度）
        files = [f for f in files if f.stat().st_mtime >= since - 1]
    if not files:
        return None
    newest = max(files, key=lambda f: f.stat().st_mtime)
    return str(newest.relative_to(Path(DATA_DIR)))


def _persist_fallback(user_dir: Path, content: str) -> str | None:
    """兜底：模型没调 write_file，但正文已经生成出来了，由后端替它落盘。

    模型偶尔会把简报当成对话回复吐出来而不写文件。不兜底的话这些内容会凭空
    消失，而 last_generated 已经标成今天，用户以为已经存好了。

    返回相对路径；内容太短则返回 None（多半是"已生成"之类的客套话）。
    """
    text = (content or "").strip()
    if len(text) < 100:
        return None

    briefs_dir = user_dir / "briefs"
    briefs_dir.mkdir(exist_ok=True)
    now_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = briefs_dir / f"{now_ts}.md"
    target.write_text(text, encoding="utf-8")
    return str(target.relative_to(Path(DATA_DIR)))


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
    - reasoning ：模型的思考过程（逐段推，前端单独一栏显示）
    - text      ：模型输出的文字片段（打字机效果）
    - progress  ：工具调用进度（人话）
    - done      ：生成完成，带 brief_id / saved_path / date / iterations
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
    started_at = time.time()

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
                yield sse("text", content=event["content"])

            elif etype == "reasoning":
                # 思考过程走单独一栏，不混进 text：它逐 token 推过来，本身就是打字机
                # 效果，而且这部分内容模型已经生成好了，转发不额外花时间。
                yield sse("reasoning", content=event["content"])

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
                        # 覆盖同名文件只在模型没照抄任务消息给的文件名时发生，意味着
                        # 上一份简报已被盖掉，得在面板上留一行。
                        if result.get("overwrote_bytes"):
                            yield sse(
                                "progress",
                                content=(
                                    f"   ⚠️ 覆盖了已存在的 {result.get('path', '')}"
                                    f"（原 {result['overwrote_bytes']} 字节）"
                                ),
                                tool=name,
                            )
                        else:
                            yield sse(
                                "progress",
                                content=f"   已保存到 {result.get('path', '')}",
                                tool=name,
                            )

            elif etype == "iterations":
                iterations = event.get("count", 0)

            elif etype == "done":
                content = event.get("content", "")
                saved_path = _find_saved_path(user_dir, today, since=started_at)
                if saved_path is None:
                    saved_path = _persist_fallback(user_dir, content)

                if saved_path is None:
                    # 既没写出文件、回复里也没有正文，这次生成就是失败的（模型撞到
                    # 最大轮数时如此）。报错，别发 done，前端会弹出一个空白弹窗。
                    yield sse(
                        "error",
                        content=(
                            "本次生成没有产出内容（模型没有写出简报文件），"
                            "请重新生成一次。"
                        ),
                    )
                    return

                # 只在真的存下来时才标记，否则下次进来会以为"今天已经生成过了"
                _update_last_generated(user_dir, today)

                # brief_id 是简报文件的 stem，前端拿它调 GET /briefs/{brief_id} 就能
                # 读回正文，不必让模型在最后一条回复里把简报复述一遍。
                yield sse(
                    "done",
                    content=content,
                    date=today,
                    brief_id=Path(saved_path).stem,
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

    started_at = time.time()
    result = run_react(
        system_prompt=NEWS_AGENT_PROMPT,
        user_message=full_message,
        sandbox_dir=user_dir,
    )

    saved_path = _find_saved_path(user_dir, today, since=started_at)
    if saved_path is None:
        saved_path = _persist_fallback(user_dir, result["answer"])
    _update_last_generated(user_dir, today)

    return {
        "username": username,
        "date": today,
        "content": result["answer"],
        "tool_calls": result["tool_calls"],
        "iterations": result["iterations"],
        "brief_id": Path(saved_path).stem if saved_path else None,
        "saved_path": saved_path,
    }