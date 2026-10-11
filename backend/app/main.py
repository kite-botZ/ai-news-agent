"""FastAPI 应用入口。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.routes import news, users
from app.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时挂定时任务，退出时停掉。"""
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="AI 新闻助手 API", lifespan=lifespan)

# 允许跨域（前端地址通过 CORS_ORIGINS 环境变量配置）
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(users.router)
app.include_router(news.router)


@app.get("/")
def root():
    return {"message": "AI 新闻助手 API 已启动"}
