"""测试 ReAct 循环。

测试场景：让 Agent 读取用户的订阅偏好。
用户问："我想看我的订阅偏好"
Agent 应该：
1. 调用 list_dir 看有哪些文件
2. 调用 read_file 读取 preferences.json
3. 基于内容回答
"""

from app.agent.react import run_react

SYSTEM_PROMPT = """你是一个 AI 新闻助手，负责根据用户的订阅偏好，帮用户整理每日 AI 新闻简报。

你可以使用以下工具：
- list_dir：列出目录内容
- read_file：读取文件
- search_content：搜索文件内容
- write_file：写入文件
- bash：执行 shell 命令

请根据用户的问题，自主决定是否需要调用工具。
"""

# 测试 1：让 Agent 读偏好
print("=" * 50)
print("测试 1：用户问 '我的订阅偏好是什么'")
print("=" * 50)
result = run_react(
    system_prompt=SYSTEM_PROMPT,
    user_message="我的订阅偏好是什么？",
    verbose=True,
)
print("\n【最终回答】", result["answer"])
print(f"【调用工具】{len(result['tool_calls'])} 次")
print(f"【迭代轮数】{result['iterations']}")