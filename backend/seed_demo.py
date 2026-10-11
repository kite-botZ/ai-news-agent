"""一键创建演示用户。

用法（先 cd 到 backend/ 目录）：
    python seed_demo.py

data/ 目录本身被 .gitignore 忽略，所以 clone 下来是空的。
跑一下这个脚本，就有了可以直接登录演示的账号。
"""

from app import users

# 演示账号：用户名 -> 偏好
DEMO_USERS = [
    ("alice", {
        "keywords": ["AI", "大模型", "LLM", "Agent", "OpenAI"],
        "topics": ["人工智能", "科技"],
    }),
    ("bob", {
        "keywords": ["Python", "FastAPI", "后端"],
        "topics": ["后端开发"],
    }),
    ("charlie", {
        "keywords": ["芯片", "半导体", "算力"],
        "topics": ["硬件"],
    }),
]


def main() -> None:
    for username, prefs in DEMO_USERS:
        try:
            users.create_user(username)
        except ValueError:
            # 已存在的用户不动，避免覆盖你自己调过的偏好
            print(f"⏭  用户 {username} 已存在，跳过")
            continue

        users.update_preferences(username, prefs)
        print(f"✅ 已创建用户 {username}")

    print("\n完成。可用账号：", ", ".join(u for u, _ in DEMO_USERS))


if __name__ == "__main__":
    main()
