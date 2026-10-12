"""LLM 流式封装测试：把供应商的 chunk 翻译成本项目的内部事件。

重点是 reasoning_content。Qwen3 开思考后会逐 token 推这个字段，漏读不会报错，
只是内容已经从网上传过来了、面板上却什么都没有。
"""

from types import SimpleNamespace

import pytest

from app.agent import llm


def _chunk(content=None, reasoning=None, tool_calls=None):
    delta = SimpleNamespace(
        content=content, reasoning_content=reasoning, tool_calls=tool_calls
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_call_delta(index, call_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


@pytest.fixture
def fake_stream(monkeypatch):
    """把全局 client 换成一个只会按脚本吐 chunk 的假货。不联网。"""

    def install(chunks):
        class _Completions:
            @staticmethod
            def create(**kwargs):
                return iter(chunks)

        class _Chat:
            completions = _Completions()

        class _Client:
            chat = _Chat()

        monkeypatch.setattr(llm, "_client", _Client())

    return install


# ============================================================
# 思考过程
# ============================================================

def test_reasoning_chunks_are_yielded(fake_stream):
    fake_stream([
        _chunk(reasoning="先看用户偏好"),
        _chunk(reasoning="，再决定拉几个源"),
        _chunk(content="好的。"),
    ])

    events = list(llm.chat_stream(messages=[]))

    assert [e["type"] for e in events] == ["reasoning", "reasoning", "content"]
    assert events[0]["text"] == "先看用户偏好"
    assert events[-1]["text"] == "好的。"


def test_chunks_without_reasoning_emit_no_reasoning_event(fake_stream):
    """关掉思考时 delta 上根本没有这个字段，不能凭空造出空事件。"""
    fake_stream([_chunk(content="直接回答")])

    events = list(llm.chat_stream(messages=[]))

    assert [e["type"] for e in events] == ["content"]


def test_empty_reasoning_is_not_emitted(fake_stream):
    """空字符串同样是"没有"，否则会往面板上推一堆看不见的片段。"""
    fake_stream([_chunk(reasoning=""), _chunk(content="x")])

    events = list(llm.chat_stream(messages=[]))

    assert [e["type"] for e in events] == ["content"]


# ============================================================
# tool_calls：流式下是分片拼起来的，别被思考字段的改动碰坏
# ============================================================

def test_tool_calls_are_reassembled_from_fragments(fake_stream):
    fake_stream([
        _chunk(reasoning="该读偏好文件了"),
        _chunk(tool_calls=[_tool_call_delta(0, call_id="c1", name="read_file")]),
        _chunk(tool_calls=[_tool_call_delta(0, arguments='{"path": "pref')]),
        _chunk(tool_calls=[_tool_call_delta(0, arguments='erences.json"}')]),
    ])

    events = list(llm.chat_stream(messages=[]))

    assert [e["type"] for e in events] == ["reasoning", "tool_calls"]
    call = events[-1]["tool_calls"][0]
    assert call["name"] == "read_file"
    assert call["arguments"] == '{"path": "preferences.json"}'


def test_parallel_tool_calls_are_kept_apart(fake_stream):
    """模型一条回复里要并发拉两个源，两片的 index 不能串。"""
    fake_stream([
        _chunk(tool_calls=[_tool_call_delta(0, call_id="c1", name="fetch_rss")]),
        _chunk(tool_calls=[_tool_call_delta(1, call_id="c2", name="fetch_rss")]),
        _chunk(tool_calls=[_tool_call_delta(0, arguments='{"url": "a"}')]),
        _chunk(tool_calls=[_tool_call_delta(1, arguments='{"url": "b"}')]),
    ])

    events = list(llm.chat_stream(messages=[]))
    calls = events[-1]["tool_calls"]

    assert len(calls) == 2
    assert calls[0]["arguments"] == '{"url": "a"}'
    assert calls[1]["arguments"] == '{"url": "b"}'


# ============================================================
# 请求参数
# ============================================================

def test_thinking_budget_goes_through_extra_body(monkeypatch):
    """两个思考参数都不是 OpenAI 标准字段，走 extra_body 才有用。"""
    from app.config import ENABLE_THINKING, THINKING_BUDGET

    if not ENABLE_THINKING:
        pytest.skip("当前配置关掉了思考")

    kwargs = llm._build_kwargs(messages=[], tools=None, stream=True)

    if THINKING_BUDGET:
        assert kwargs["extra_body"] == {"thinking_budget": THINKING_BUDGET}
    else:
        assert "extra_body" not in kwargs
