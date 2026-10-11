"""手工测试：硅基流动 API 能不能调通。

直接运行：python test_llm.py
（加了 __main__ 守卫，避免被 pytest 收集时真的发请求）
"""
from app.agent.llm import simple_chat


def main() -> None:
    print("正在调用模型...")
    answer = simple_chat("用一句话介绍你自己")
    print("模型回复：", answer)


if __name__ == "__main__":
    main()
