"""手写的 ReAct 循环：把 system prompt + 用户消息 + 工具 schema 发给模型，
模型要么直接回答（结束），要么返回 tool_calls；后端执行后把结果作为 tool 消息
追加进历史再问一遍，直到它不再调工具或达到 MAX_ITERATIONS。

顺序和次数都不由这里决定，循环本身不认识任何具体工具。

sandbox_dir 逐次显式传给 execute_tool，不靠全局状态，原因见 tools.execute_tool。
"""

import json
from pathlib import Path

from app.agent.llm import chat, chat_stream
from app.agent.tools import TOOLS_SCHEMA, execute_tool
from app.config import MAX_ITERATIONS


def run_react(
    system_prompt: str,
    user_message: str,
    verbose: bool = False,
    sandbox_dir: Path | None = None,
) -> dict:
    """跑一次 ReAct 循环。

    返回 {"answer": 最终回答, "tool_calls": [{"name","args","result"}], "iterations": 轮数}。
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    tool_call_records = []
    iterations = 0

    for i in range(MAX_ITERATIONS):
        iterations = i + 1

        if verbose:
            print(f"\n--- 第 {iterations} 轮 ---")

        response = chat(messages=messages, tools=TOOLS_SCHEMA)
        message = response.choices[0].message

        tool_calls = message.tool_calls or []

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

        for tc in tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            if verbose:
                print(f"调用工具：{tool_name}({tool_args})")

            result = execute_tool(tool_name, tool_args, sandbox_dir=sandbox_dir)

            if verbose:
                print(f"工具返回：{result}")

            tool_call_records.append({
                "name": tool_name,
                "args": tool_args,
                "result": result,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return {
        "answer": "（已达到最大工具调用轮数，未能生成最终回答）",
        "tool_calls": tool_call_records,
        "iterations": iterations,
    }


# ============================================================
# 流式 ReAct：每一段文字都推给前端
# ============================================================

def run_react_stream_realtime(
    system_prompt: str,
    user_message: str,
    sandbox_dir: Path | None = None,
):
    """流式 ReAct，边跑边 yield 事件：

    status / reasoning / text / tool_call / tool_result / iterations / done / error
    """

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
                    # 纯空白不外发：模型调工具那几轮会推 "\n\n"，前端在 JS 里把
                    # 它当真值攒起来，会挡掉真正的兜底文案
                    if event["text"].strip():
                        yield {"type": "text", "content": event["text"]}
                elif event["type"] == "reasoning":
                    # 只推给前端，不进 content_buffer：混进去 done 的 content 会变成
                    # 一堆内心戏，而那个 content 是要落盘成简报的
                    yield {"type": "reasoning", "content": event["text"]}
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

                # 逐次显式传沙箱：上面那个 yield 之后可能已经换过线程了
                result = execute_tool(name, args, sandbox_dir=sandbox_dir)

                yield {"type": "tool_result", "name": name, "result": result}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

        yield {"type": "iterations", "count": iterations}
        # 先 strip 再判空：final_answer 可能是 "\n\n"，truthy 但看不见，
        # 会顶掉这句提示，前端于是一片空白
        yield {"type": "done", "content": final_answer.strip() or "（未生成最终回答）"}

    except Exception as e:
        yield {"type": "error", "content": str(e)}
