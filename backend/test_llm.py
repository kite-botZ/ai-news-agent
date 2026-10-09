"""测试硅基流动 API 能不能调通。"""
from app.agent.llm import simple_chat

print("正在调用模型...")
answer = simple_chat("用一句话介绍你自己")
print("模型回复：", answer)