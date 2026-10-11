"""排查脚本：硅基流动 API 能不能调通。

配好 .env 之后先跑这个，确认 key、base_url、model 名三项都对：

    python check_llm.py

（命名用 check_ 而不是 test_，是为了让 `test_*` 只表示 pytest 用例。）
"""
from app.agent.llm import simple_chat


def main() -> None:
    print("正在调用模型...")
    answer = simple_chat("用一句话介绍你自己")
    print("模型回复：", answer)


if __name__ == "__main__":
    main()
