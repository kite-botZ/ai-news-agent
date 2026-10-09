"""封装硅基流动的 LLM 调用。

硅基流动兼容 OpenAI 接口，所以直接用 openai 库调用。
"""

from openai import OpenAI

from app.config import MODEL_NAME, SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL

# 全局 client（复用连接）
_client = OpenAI(
    api_key=SILICONFLOW_API_KEY,
    base_url=SILICONFLOW_BASE_URL,
)


def chat(messages: list[dict], tools: list[dict] | None = None, stream: bool = False):
    """调用 LLM。

    参数：
    - messages：OpenAI 格式的消息列表，如 [{"role": "user", "content": "你好"}]
    - tools：工具 schema 列表（Function Calling 用），None 表示不启用工具
    - stream：是否流式返回

    返回：OpenAI 的 response 对象
    """
    kwargs = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"  # 让模型自己决定是否调用工具

    return _client.chat.completions.create(**kwargs)


def simple_chat(prompt: str) -> str:
    """最简单的对话：发一句话，返回字符串。用于测试 API 通不通。"""
    response = chat(messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content