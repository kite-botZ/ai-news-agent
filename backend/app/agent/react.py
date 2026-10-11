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

支持：
- sandbox_dir：指定工具操作的沙箱根目录（比如某个用户的目录）
"""

import json
from pathlib import Path

from app.agent.llm import chat, chat_stream
from app.agent.tools import TOOLS_SCHEMA, execute_tool, set_sandbox
from app.config import MAX_ITERATIONS


def run_react(
    system_prompt: str,
    user_message: str,
    verbose: bool = False,
    sandbox_dir: Path | None = None,
) -> dict:
    """跑一次 ReAct 循环。

    参数：
    - system_prompt：系统提示词，定义 Agent 的角色
    - user_message：用户的输入
    - verbose：是否打印中间过程（调试用）
    - sandbox_dir：工具操作的沙箱根目录。None 表示默认的 data/ 目录

    返回：
    {
        "answer": 最终回答,
        "tool_calls": [{"name": ..., "args": ..., "result": ...}, ...],
        "iterations": 迭代了几轮
    }
    """

    # 设置沙箱根目录
    set_sandbox(sandbox_dir)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    tool_call_records = []
    iterations = 0

    try:
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
    finally:
        # 恢复默认沙箱，避免影响后续调用
        set_sandbox(None)


# ============================================================
# 流式 ReAct：每一段文字都推给前端
# ============================================================

def run_react_stream_realtime(
    system_prompt: str,
    user_message: str,
    sandbox_dir: Path | None = None,
):
    """真·流式 ReAct。

    yield 事件：
    - {"type": "status", "content": "..."}            状态
    - {"type": "text", "content": "..."}              **模型输出的文字片段**
    - {"type": "tool_call", "name": "...", "args": ...}
    - {"type": "tool_result", "name": "...", "result": ...}
    - {"type": "iterations", "count": N}
    - {"type": "done", "content": "..."}              最终完整回答
    - {"type": "error", "content": "..."}
    """

    set_sandbox(sandbox_dir)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    final_answer = ""
    iterations = 0

    try:
        for i in range(MAX_ITERATIONS):
            iterations = i + 1
            yield {"type": "status", "content": f"🤔 第 {iterations} 轮思考…"}

            # ---- 流式调用模型 ----
            content_buffer = ""
            tool_calls_result = None

            for event in chat_stream(messages=messages, tools=TOOLS_SCHEMA):
                if event["type"] == "content":
                    content_buffer += event["text"]
                    # ★ 关键：立即把这段文字推给前端
                    yield {"type": "text", "content": event["text"]}
                elif event["type"] == "tool_calls":
                    tool_calls_result = event["tool_calls"]

            # 把助手回复加入历史
            assistant_msg = {"role": "assistant", "content": content_buffer}
            if tool_calls_result:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    }
                    for tc in tool_calls_result
                ]
            messages.append(assistant_msg)

            # 没有工具调用 → 结束
            if not tool_calls_result:
                final_answer = content_buffer
                break

            # ---- 执行工具 ----
            for tc in tool_calls_result:
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"])
                except json.JSONDecodeError:
                    args = {}

                yield {"type": "tool_call", "name": name, "args": args}

                result = execute_tool(name, args)

                yield {"type": "tool_result", "name": name, "result": result}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

        yield {"type": "iterations", "count": iterations}
        yield {"type": "done", "content": final_answer or "（未生成最终回答）"}

    except Exception as e:
        yield {"type": "error", "content": str(e)}
    finally:
        set_sandbox(None)
