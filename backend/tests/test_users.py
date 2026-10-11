"""用户管理模块测试。

这里最要紧的是两条正则——它们都挡在"用户可控字符串直接拼进文件路径"前面：

    _USERNAME_PATTERN      挡 data/users/<这里>/
    _BRIEF_STEM_PATTERN    挡 briefs/<这里>.md

所以除了正常的增删读写，重点是把越界的名字和日期喂进去，看能不能穿出去。
"""

import pytest

from app import users as user_service


@pytest.fixture(autouse=True)
def isolated_users_dir(tmp_path, monkeypatch):
    """把用户根目录指到临时目录，别碰真实的 data/users/。"""
    monkeypatch.setattr(user_service, "USERS_DIR", tmp_path)
    return tmp_path


# ============================================================
# 用户名校验
# ============================================================

@pytest.mark.parametrize(
    "name",
    [
        "ab",           # 太短
        "a" * 21,       # 太长
        "bad user",     # 空格
        "a/b",          # 路径分隔符
        "..",           # 直接就是上级目录
        "../etc",       # 穿越
        "中文名",        # 非 ASCII
        "alice!",       # 特殊字符
        "",             # 空
    ],
)
def test_invalid_username_is_rejected(name):
    assert user_service.validate_username(name) is False
    with pytest.raises(ValueError):
        user_service.get_user_dir(name)


@pytest.mark.parametrize("name", ["abc", "alice", "user_01", "A" * 20])
def test_valid_username_is_accepted(name):
    assert user_service.validate_username(name) is True


def test_traversal_username_cannot_escape_users_dir(isolated_users_dir):
    """最关键的一条：越界的用户名不只要报错，目录必须真的没被创建出来。"""
    escaped = isolated_users_dir.parent / "etc"

    with pytest.raises(ValueError):
        user_service.create_user("../etc")

    assert not escaped.exists()


# ============================================================
# 创建与偏好读写
# ============================================================

def test_create_user_writes_default_preferences():
    prefs = user_service.create_user("alice")

    assert prefs["username"] == "alice"
    assert prefs["keywords"]                      # 有默认关注词
    assert prefs["last_generated"] is None
    assert user_service.user_exists("alice")
    assert user_service.get_preferences("alice") == prefs


def test_create_existing_user_raises():
    user_service.create_user("alice")
    with pytest.raises(ValueError, match="已存在"):
        user_service.create_user("alice")


def test_preferences_missing_user_raises():
    with pytest.raises(ValueError):
        user_service.get_preferences("nobody")


def test_update_only_touches_allowed_fields():
    """请求体里塞别的字段不该生效——不然用户能自己改 username 或生成时间。"""
    user_service.create_user("alice")

    updated = user_service.update_preferences("alice", {
        "keywords": ["RAG", "向量数据库"],
        "username": "hacker",            # 不在白名单
        "last_generated": "1970-01-01",  # 不在白名单
    })

    assert updated["keywords"] == ["RAG", "向量数据库"]
    assert updated["username"] == "alice"
    assert updated["last_generated"] is None


def test_update_persists_to_disk():
    user_service.create_user("alice")
    user_service.update_preferences("alice", {"topics": ["大模型"]})

    # 重新读一遍，确认真的写盘了而不是只改了内存里的 dict
    assert user_service.get_preferences("alice")["topics"] == ["大模型"]


def test_update_missing_user_raises():
    with pytest.raises(ValueError):
        user_service.update_preferences("nobody", {"keywords": ["x"]})


# ============================================================
# 简报文件
# ============================================================

@pytest.mark.parametrize(
    "stem",
    [
        "../../preferences",   # 穿越到偏好文件
        "..",
        "2026-10-12/../x",     # 分隔符
        "abc",
        "2026-10-12.md",       # 带后缀（上层会自己补 .md）
    ],
)
def test_get_brief_rejects_bad_stem(stem):
    user_service.create_user("alice")
    with pytest.raises(ValueError):
        user_service.get_brief("alice", stem)


@pytest.mark.parametrize("stem", ["2026-10-12", "2026-10-12_00-13-07"])
def test_get_brief_accepts_valid_stem(stem):
    user_service.create_user("alice")
    (user_service.get_user_dir("alice") / "briefs" / f"{stem}.md").write_text(
        "内容", encoding="utf-8"
    )
    assert user_service.get_brief("alice", stem) == "内容"


def test_get_missing_brief_raises():
    user_service.create_user("alice")
    with pytest.raises(ValueError, match="不存在"):
        user_service.get_brief("alice", "2026-01-01")


def test_list_briefs_is_sorted_newest_first():
    user_service.create_user("alice")
    briefs_dir = user_service.get_user_dir("alice") / "briefs"
    for stem in ["2026-10-10", "2026-10-12", "2026-10-11"]:
        (briefs_dir / f"{stem}.md").write_text(stem, encoding="utf-8")

    dates = [item["date"] for item in user_service.list_briefs("alice")]

    assert dates == ["2026-10-12", "2026-10-11", "2026-10-10"]


def test_list_briefs_empty_for_new_user():
    user_service.create_user("alice")
    assert user_service.list_briefs("alice") == []
