"""项目配置：从 .env 读取环境变量。"""

import os

from dotenv import load_dotenv

# 加载 backend/.env
load_dotenv()

# 硅基流动 API 配置
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B")

# Agent 最大迭代轮数（防止工具调用死循环）
MAX_ITERATIONS = 5

# 数据目录（工具操作的沙箱根目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)