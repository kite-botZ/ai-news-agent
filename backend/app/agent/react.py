"""ReAct 循环。

核心思想：让模型在推理（Reasoning）和行动（Acting）之间循环。

流程：
1. 把 system prompt + 用户消息 + 工具 schema 发给模型
2. 模型判断：
   - 直接回答 → 结束
   - 需要调用工具 → 返回 tool_calls
3. 后端执行工具，把结果作为 tool 消息追加到历史
4. 把更新后的消息历史再发给模型
5. 重复直到模型不再调用工具，或达到最大轮数

支持两种模式：
- run_react(messages)：一次性返回最终结果（非流式）
- run_react_stream(messages)：流式返回（SSE 用）
"""

import json

from app.agent.llm import chat
from app.agent.tools import TOOLS_SCHEMA, execute_tool
from app.config import MAX_ITERATIONS


def run_react(system_prompt: str, user_message: str, verbose: bool = False) -> dict:
    """跑一次 ReAct 循环。

    参数：
    - system_prompt：系统提示词，定义 Agent 的角色
    - user_message：用户的输入
    - verbose：是否打印中间过程（调试用）

    返回：
    {
        "answer": 最终回答,
        "tool_calls": [{"name": ..., "args": ..., "result": ...}, ...],
        "iterations": 迭代了几轮
    }
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    tool_call_records = []  # 记录每次工具调用
    iterations = 0

    for i in range(MAX_ITERATIONS):
        iterations = i + 1

        if verbose:
            print(f"\n--- 第 {iterations} 轮 ---")

        # 1. 调用模型
        response = chat(messages=messages, tools=TOOLS_SCHEMA)
        message = response.choices[0].message

        # 2. 检查是否有工具调用
        tool_calls = message.tool_calls or []

        # 把助手的回复加入历史
        assistant_msg = {"role": "assistant", "content": message.content or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        # 3. 没有工具调用 → 结束
        if not tool_calls:
            if verbose:
                print("模型没有调用工具，返回最终回答")
            return {
                "answer": message.content,
                "tool_calls": tool_call_records,
                "iterations": iterations,
            }

        # 4. 有工具调用 → 逐个执行
        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            if verbose:
                print(f"调用工具：{tool_name}({tool_args})")

            # 执行工具
            result = execute_tool(tool_name, tool_args)

            if verbose:
                print(f"工具返回：{result}")

            tool_call_records.append({
                "name": tool_name,
                "args": tool_args,
                "result": result,
            })

            # 把工具结果加入历史
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    # 达到最大轮数还没结束
    return {
        "answer": "（已达到最大工具调用轮数，未能生成最终回答）",
        "tool_calls": tool_call_records,
        "iterations": iterations,
    }