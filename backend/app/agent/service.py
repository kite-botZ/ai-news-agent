"""Agent 业务封装：为指定用户生成简报。

这一层的作用：
- 把"用户名 → 目录 → Prompt"这套上下文拼装起来
- 对外暴露一个简单的函数，供 API 层调用
- 用户调用时只需传 username，不需要关心 Agent 内部细节
"""

import json
from datetime import datetime
from pathlib import Path

from app.agent.prompts import NEWS_AGENT_PROMPT
from app.agent.react import run_react
from app.config import DATA_DIR

# data/users 目录
USERS_DIR = Path(DATA_DIR) / "users"


def generate_brief_for_user(username: str, verbose: bool = False) -> dict:
    """为指定用户生成今日 AI 新闻简报。

    参数：
    - username：用户名（必须已存在）
    - verbose：是否打印中间过程

    返回：
    {
        "username": ...,
        "date": ...,
        "content": 简报内容,
        "tool_calls": [...],
        "iterations": ...,
        "saved_path": 保存的文件路径
    }
    """

    user_dir = USERS_DIR / username
    if not user_dir.exists():
        raise ValueError(f"用户不存在：{username}")

    # 构造 user message，把 username 传给 Agent
    today = datetime.now().strftime("%Y-%m-%d")
    now_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    user_message = (
        f"请为用户名 {username} 生成今天（{today}）的 AI 新闻简报。\n\n"
        f"注意：所有文件路径都基于该用户的目录，不要加任何前缀。\n"
        f"比如读偏好用 'preferences.json'，存简报用 'briefs/{today}.md'。"
    )

    # 调用 Agent（内部工具是以 data/users/<username>/ 为沙箱根目录的）
    # 但我们现在的工具沙箱是 data/，不是 data/users/<username>/
    # 所以需要在 Prompt 里让模型拼出相对路径
    full_message = (
        f"[当前用户：{username}]\n"
        f"[用户目录：data/users/{username}/]\n\n"
        f"{user_message}\n\n"
        f"重要：所有工具路径都相对于该用户的目录，不要加任何前缀。"
        f"比如读偏好用 'preferences.json'，"
        f"存简报到 'briefs/{now_ts}.md'。\n\n"
        f"生成简报时，请用这个精确的文件名，避免同一天生成多次时互相覆盖。"
    )

    result = run_react(
        system_prompt=NEWS_AGENT_PROMPT,
        user_message=full_message,
        verbose=verbose,
        sandbox_dir=user_dir,   # 传入该用户的目录作为沙箱
    )

    # 找保存的文件路径：扫描 briefs 目录，找今天最新的文件
    briefs_dir = user_dir / "briefs"
    saved_path = None
    if briefs_dir.exists():
        today_files = sorted(
            [f for f in briefs_dir.glob(f"{today}*.md")],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if today_files:
            saved_path = str(today_files[0].relative_to(Path(DATA_DIR)))
    # 更新偏好里的 last_generated
    prefs_file = user_dir / "preferences.json"
    if prefs_file.exists():
        prefs = json.loads(prefs_file.read_text(encoding="utf-8"))
        prefs["last_generated"] = today
        prefs_file.write_text(
            json.dumps(prefs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {
        "username": username,
        "date": today,
        "content": result["answer"],
        "tool_calls": result["tool_calls"],
        "iterations": result["iterations"],
        "saved_path": saved_path,
    }