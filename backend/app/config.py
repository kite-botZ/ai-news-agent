"""项目配置：从 .env 读取环境变量。"""

import os

from dotenv import load_dotenv

# 加载 backend/.env
load_dotenv()

# 硅基流动 API 配置
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-8B")

# 是否让模型输出思考过程（思维链）。
#
# Qwen3 这类混合推理模型默认会先写一大段思考再回答。实测在工具调用场景下，
# 思考占了输出 token 的 95% 左右：一轮只要调 read_file，却生成了 716 个 token，
# 其中 690 个是看不见的思考，单轮因此要 37 秒。
#
# ⚠️ 但直接关掉会出事：实测 10 轮全在 fetch_rss、一次 write_file 都不调，任务失败。
# 那 690 个 token 里有一部分确实在做规划（一次并发拉几个源、什么时候该收手）。
# 所以默认保留思考，只给一个预算上限（见 THINKING_BUDGET）。
#
# 只有换成不支持这两个参数的模型时，才把它设成 false。
ENABLE_THINKING = os.getenv("ENABLE_THINKING", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# 思考预算（token）。留一点思考用来做规划，但不让它无节制地写下去。
# 实测同一句问题：预算 100 → 150 个输出 token / 6.7 秒，不限制 → 456 个 / 17.9 秒。
# 设成 0 表示不限制。
_raw_budget = os.getenv("THINKING_BUDGET", "100").strip()
THINKING_BUDGET = int(_raw_budget) if _raw_budget.isdigit() and int(_raw_budget) > 0 else None

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

# 数据目录（工具操作的沙箱根目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)