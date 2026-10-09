"""测试：让 Agent 完整跑一次新闻简报生成流程。

期望流程：
1. Agent 读 preferences.json
2. Agent 拉取 RSS 新闻
3. Agent 筛选 + 生成简报
4. Agent 用 write_file 保存到 data/briefs/
"""

from app.agent.prompts import NEWS_AGENT_PROMPT
from app.agent.react import run_react

print("=" * 60)
print("任务：帮我生成今天的 AI 新闻简报")
print("=" * 60)

result = run_react(
    system_prompt=NEWS_AGENT_PROMPT,
    user_message="帮我生成今天的 AI 新闻简报",
    verbose=True,
)

print("\n" + "=" * 60)
print("【最终回答】")
print("=" * 60)
print(result["answer"])

print("\n" + "=" * 60)
print(f"【共调用工具 {len(result['tool_calls'])} 次】")
for i, tc in enumerate(result["tool_calls"], 1):
    print(f"  {i}. {tc['name']}({tc['args']})")

print(f"\n【迭代轮数】{result['iterations']}")