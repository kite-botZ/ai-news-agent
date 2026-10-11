"""项目配置：从 .env 读取环境变量。"""

import os

from dotenv import load_dotenv

# 加载 backend/.env
load_dotenv()

# 硅基流动 API 配置
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-8B")

# Agent 最大迭代轮数（防止工具调用死循环）
MAX_ITERATIONS = 10

# 允许跨域的前端地址（逗号分隔）
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

# ==================== 定时任务 ====================
# 是否开启「每天自动生成简报」
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "true").lower() in (
    "1", "true", "yes", "on",
)
# 每天几点执行（24 小时制）
BRIEF_SCHEDULE_HOUR = int(os.getenv("BRIEF_SCHEDULE_HOUR", "8"))
BRIEF_SCHEDULE_MINUTE = int(os.getenv("BRIEF_SCHEDULE_MINUTE", "0"))

# 数据目录（工具操作的沙箱根目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)