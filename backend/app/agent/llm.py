"""封装硅基流动的 LLM 调用。

硅基流动兼容 OpenAI 接口，直接用 openai 库。
"""

from openai import OpenAI

from app.config import (
    ENABLE_THINKING,
    MODEL_NAME,
    SILICONFLOW_API_KEY,
    SILICONFLOW_BASE_URL,
    THINKING_BUDGET,
)

# 全局 client，复用连接
_client = OpenAI(
    api_key=SILICONFLOW_API_KEY,
    base_url=SILICONFLOW_BASE_URL,
)


def _build_kwargs(messages: list[dict], tools: list[dict] | None, stream: bool) -> dict:
    """拼出一次请求的参数。普通调用和流式调用共用。"""
    kwargs = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": stream,
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    # enable_thinking / thinking_budget 不是 OpenAI 标准参数，只能走 extra_body。
    # 给思考留预算而不是关掉它：全关之后模型会失去规划能力，一路调 fetch_rss
    # 却始终不写文件，任务直接失败。要提速请调 THINKING_BUDGET。
    extra: dict = {}
    if not ENABLE_THINKING:
        extra["enable_thinking"] = False
    elif THINKING_BUDGET:
        extra["thinking_budget"] = THINKING_BUDGET
    if extra:
        kwargs["extra_body"] = extra

    return kwargs


def chat(messages: list[dict], tools: list[dict] | None = None, stream: bool = False):
    """非流式调用，返回 OpenAI 的 response 对象。"""
    return _client.chat.completions.create(**_build_kwargs(messages, tools, stream))


def simple_chat(prompt: str) -> str:
    """发一句话返回字符串，用来测 API 通不通。"""
    response = chat(messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content


def chat_stream(messages: list[dict], tools: list[dict] | None = None):
    """流式调用 LLM，逐个 chunk yield：

    - {"type": "reasoning", "text": "..."}       思考过程（开了思考才有）
    - {"type": "content", "text": "..."}         正文片段
    - {"type": "tool_calls", "tool_calls": [...]} 完整工具调用

    思考与正文分开报：前者给用户看"Agent 在想什么"，后者是最终回答，渲染方式不同。
    """

    stream = _client.chat.completions.create(
        **_build_kwargs(messages, tools, stream=True)
    )

    # 流式下 tool_calls 是分片传的，先按 index 攒齐
    tool_calls_buffer: list[dict] = []

    for chunk in stream:
        delta = chunk.choices[0].delta

        # Qwen3 开思考时逐 token 推 reasoning_content。不是 OpenAI 标准字段，
        # 关掉思考时 delta 上根本没有它，所以用 getattr 取
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield {"type": "reasoning", "text": reasoning}

        if delta.content:
            yield {"type": "content", "text": delta.content}

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

    if tool_calls_buffer:
        yield {"type": "tool_calls", "tool_calls": tool_calls_buffer}