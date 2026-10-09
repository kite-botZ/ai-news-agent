"""用户管理：每个用户一个独立文件夹。

目录结构：
    data/users/<username>/
        ├── preferences.json   用户偏好
        └── briefs/            历史简报
"""

import json
import os
import re
from pathlib import Path

from app.config import DATA_DIR

# 用户数据的根目录
USERS_DIR = Path(DATA_DIR) / "users"
USERS_DIR.mkdir(parents=True, exist_ok=True)

# 用户名规则：字母、数字、下划线，3~20 位
_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


def validate_username(username: str) -> bool:
    """校验用户名合法性。"""
    return bool(_USERNAME_PATTERN.match(username))


def get_user_dir(username: str) -> Path:
    """获取用户目录的路径（不存在时返回，不创建）。"""
    if not validate_username(username):
        raise ValueError(f"用户名不合法：{username}")
    return USERS_DIR / username


def user_exists(username: str) -> bool:
    """判断用户是否存在。"""
    return get_user_dir(username).exists()


def create_user(username: str) -> dict:
    """创建用户（含偏好文件和历史简报目录）。"""
    if not validate_username(username):
        raise ValueError("用户名只能包含字母、数字、下划线，长度 3~20 位")

    user_dir = get_user_dir(username)
    if user_dir.exists():
        raise ValueError(f"用户 {username} 已存在")

    # 创建目录
    user_dir.mkdir(parents=True)
    (user_dir / "briefs").mkdir()

    # 默认偏好
    default_prefs = {
        "username": username,
        "keywords": ["AI", "大模型", "LLM", "Agent"],
        "topics": ["人工智能"],
        "push_channel": "file",
        "created_at": _today(),
        "last_generated": None,
    }
    _write_json(user_dir / "preferences.json", default_prefs)

    return default_prefs


def get_preferences(username: str) -> dict:
    """读取用户偏好。"""
    user_dir = get_user_dir(username)
    prefs_file = user_dir / "preferences.json"
    if not prefs_file.exists():
        raise ValueError(f"用户 {username} 不存在或偏好文件缺失")
    return _read_json(prefs_file)


def update_preferences(username: str, updates: dict) -> dict:
    """更新用户偏好（只更新传入的字段）。"""
    user_dir = get_user_dir(username)
    if not user_dir.exists():
        raise ValueError(f"用户 {username} 不存在")

    prefs = get_preferences(username)

    # 只允许更新这几个字段
    allowed_fields = {"keywords", "topics", "push_channel"}
    for key, value in updates.items():
        if key in allowed_fields:
            prefs[key] = value

    _write_json(user_dir / "preferences.json", prefs)
    return prefs


def list_briefs(username: str) -> list[dict]:
    """列出用户的历史简报（按日期倒序）。"""
    user_dir = get_user_dir(username)
    briefs_dir = user_dir / "briefs"
    if not briefs_dir.exists():
        return []

    briefs = []
    for file in sorted(briefs_dir.glob("*.md"), reverse=True):
        stat = file.stat()
        briefs.append({
            "date": file.stem,
            "filename": file.name,
            "size": stat.st_size,
        })
    return briefs


def get_brief(username: str, date: str) -> str:
    """读取某一天的简报内容。"""
    user_dir = get_user_dir(username)
    brief_file = user_dir / "briefs" / f"{date}.md"
    if not brief_file.exists():
        raise ValueError(f"简报不存在：{date}")
    return brief_file.read_text(encoding="utf-8")


# ============================================================
# 内部工具
# ============================================================

def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _today() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")