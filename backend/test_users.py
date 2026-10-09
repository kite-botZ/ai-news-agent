"""测试用户管理模块。"""
from app import users

# 1. 创建用户
print("=== 创建用户 bob ===")
try:
    prefs = users.create_user("bob")
    print("✅ 创建成功：", prefs)
except ValueError as e:
    print("⚠️ 已存在或非法：", e)

# 2. 读偏好
print("\n=== 读 bob 的偏好 ===")
print(users.get_preferences("bob"))

# 3. 更新偏好
print("\n=== 更新 bob 的偏好 ===")
updated = users.update_preferences("bob", {
    "keywords": ["AI", "Python", "FastAPI"],
})
print(updated)

# 4. 列简报（应该为空）
print("\n=== bob 的简报列表 ===")
print(users.list_briefs("bob"))

# 5. 非法用户名
print("\n=== 创建非法用户 ===")
try:
    users.create_user("bad user!")
except ValueError as e:
    print("✅ 拒绝：", e)