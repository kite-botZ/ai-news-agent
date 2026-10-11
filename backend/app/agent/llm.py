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


def chat_stream(messages: list[dict], tools: list[dict] | None = None):
    """流式调用 LLM。

    yield 每个 chunk：
    - {"type": "content", "text": "..."}         模型输出的一段文字
    - {"type": "tool_calls", "tool_calls": [...]} 模型要调用的工具（完整）
    """
    kwargs = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    stream = _client.chat.completions.create(**kwargs)

    # 累积 tool_calls（流式下 tool_calls 会分片）
    tool_calls_buffer: list[dict] = []

    for chunk in stream:
        delta = chunk.choices[0].delta

        # 1. 普通文本
        if delta.content:
            yield {"type": "content", "text": delta.content}

        # 2. 工具调用（流式下的 tool_calls 是分片传递的）
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                # 保证 buffer 长度
                while len(tool_calls_buffer) <= idx:
                    tool_calls_buffer.append({
                        "id": "",
                        "name": "",
                        "arguments": "",
                    })
                if tc.id:
                    tool_calls_buffer[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        tool_calls_buffer[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        tool_calls_buffer[idx]["arguments"] += tc.function.arguments

    # 3. 最后统一返回 tool_calls
    if tool_calls_buffer:
        yield {"type": "tool_calls", "tool_calls": tool_calls_buffer}