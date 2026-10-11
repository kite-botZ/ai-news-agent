"""新闻接口。

- GET /api/news?limit=30&refresh=false   拉取所有源的最新新闻（合并去重）

给前端 NewsFeed 页面的「今日新闻」列表用。
结果做 10 分钟内存缓存，避免每次刷新都去请求 9 个 RSS 源。
"""

import time

from fastapi import APIRouter, Query

from app.rss import fetch_all

router = APIRouter(prefix="/api/news", tags=["news"])

# 简单的内存缓存（演示够用；多进程部署时可换成 Redis）
_CACHE: dict = {"ts": 0.0, "data": []}
_CACHE_TTL = 600  # 秒


@router.get("")
def get_news(
    limit: int = Query(30, ge=1, le=100, description="返回条数上限"),
    refresh: bool = Query(False, description="为 true 时强制刷新缓存"),
):
    """返回合并后的新闻列表。

    每个条目包含：title / link / summary / image / source / source_name
    """
    now = time.time()
    if refresh or not _CACHE["data"] or now - _CACHE["ts"] > _CACHE_TTL:
        _CACHE["data"] = fetch_all(limit_per_source=8, max_total=60)
        _CACHE["ts"] = now
    return _CACHE["data"][:limit]
