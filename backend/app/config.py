"""项目配置：从 .env 读取环境变量。"""

import os

from dotenv import load_dotenv

load_dotenv()

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-8B")

# 别设成 false。实测全关思考后模型会失去规划能力：连续 10 轮都在 fetch_rss、
# 一次 write_file 都不调，任务直接失败。思考占了输出 token 的九成以上，
# 但里面确实在做规划（一次并发拉几个源、什么时候收手）。
# 要提速请调 THINKING_BUDGET，不是关这个。
ENABLE_THINKING = os.getenv("ENABLE_THINKING", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# 思考预算（token），0 表示不限制。
# 同一句问题实测：预算 100 → 150 输出 token / 6.7 秒；不限制 → 456 / 17.9 秒。
_raw_budget = os.getenv("THINKING_BUDGET", "100").strip()
THINKING_BUDGET = int(_raw_budget) if _raw_budget.isdigit() and int(_raw_budget) > 0 else None

# 工具调用轮数上限，防止死循环
MAX_ITERATIONS = 10

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

# DATA_DIR 同时是文件工具的沙箱根目录，见 agent/tools.py 的 _safe_path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)