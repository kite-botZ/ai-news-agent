"""FastAPI 应用入口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import users

app = FastAPI(title="AI 新闻助手 API")

# 允许跨域（前端端口是 5173）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(users.router)


@app.get("/")
def root():
    return {"message": "AI 新闻助手 API 已启动"}