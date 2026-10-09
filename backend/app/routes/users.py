"""用户管理接口。

提供：
- POST   /api/users                          创建用户
- GET    /api/users/{username}/preferences   读偏好
- PUT    /api/users/{username}/preferences   更新偏好
- GET    /api/users/{username}/briefs        列简报
- GET    /api/users/{username}/briefs/{date} 读简报
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import users as user_service

router = APIRouter(prefix="/api/users", tags=["users"])


# ============================================================
# 请求体
# ============================================================

class CreateUserBody(BaseModel):
    username: str = Field(min_length=3, max_length=20)


class UpdatePreferencesBody(BaseModel):
    keywords: list[str] | None = None
    topics: list[str] | None = None
    push_channel: str | None = None


# ============================================================
# 接口
# ============================================================

@router.post("", status_code=201)
def create_user(body: CreateUserBody):
    """创建用户。"""
    try:
        prefs = user_service.create_user(body.username)
        return {"message": "创建成功", "preferences": prefs}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{username}/preferences")
def get_preferences(username: str):
    """读用户偏好。"""
    try:
        return user_service.get_preferences(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{username}/preferences")
def update_preferences(username: str, body: UpdatePreferencesBody):
    """更新用户偏好。"""
    try:
        updates = body.model_dump(exclude_none=True)
        return user_service.update_preferences(username, updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{username}/briefs")
def list_briefs(username: str):
    """列出用户的历史简报。"""
    try:
        return user_service.list_briefs(username)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{username}/briefs/{date}")
def get_brief(username: str, date: str):
    """读取某一天的简报。"""
    try:
        content = user_service.get_brief(username, date)
        return {"date": date, "content": content}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{username}/generate")
def generate_brief(username: str, verbose: bool = False):
    """触发 Agent 为指定用户生成今日简报。"""
    try:
        from app.agent.service import generate_brief_for_user
        result = generate_brief_for_user(username, verbose=verbose)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 执行失败：{e}")