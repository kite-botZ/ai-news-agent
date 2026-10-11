"""ReAct 循环测试。

用假的 LLM 跑，不联网、不花 API 钱。测的是循环本身的控制流：
- 模型不调工具 → 一轮就结束
- 模型调工具 → 结果正确回填进消息历史，且 tool_call_id 必须配对
- 模型一直要求调工具 → 到 MAX_ITERATIONS 必须停下来，不能转圈到死
- 跑完沙箱必须恢复，否则下一个用户的请求会串到别人的目录

换掉 LLM 之后，循环就是一个普通的状态机，可以逐个出口验证。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import react
from app.agent.tools import _get_sandbox, set_sandbox
from app.config import DATA_DIR


# ============================================================
# 假 LLM：按脚本依次返回，并记录每次收到的消息历史
# ============================================================

def _response(content=None, tool_calls=None):
    """造一个结构和 OpenAI 返回一致的最小对象。"""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(call_id: str, name: str, args: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


class ScriptedLLM:
    """按脚本依次应答的假模型。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def __call__(self, messages, tools=None, **kwargs):
        # 深拷贝：循环会继续往 messages 里 append，不拷的话快照会被污染
        self.calls.append(json.loads(json.dumps(messages, ensure_ascii=False)))
        if not self._responses:
            raise AssertionError("模型被调用的次数超过了脚本预期（说明循环没停下来）")
        return self._responses.pop(0)


class ScriptedStream:
    """按脚本依次返回事件流的假流式模型。"""

    def __init__(self, scripts):
        self._scripts = list(scripts)

    def __call__(self, messages, tools=None, **kwargs):
        events = self._scripts.pop(0)

        def gen():
            yield from events

        return gen()


@pytest.fixture
def sandbox(tmp_path):
    (tmp_path / "preferences.json").write_text(
        '{"keywords": ["AI"]}', encoding="utf-8"
    )
    set_sandbox(tmp_path)
    yield tmp_path
    set_sandbox(None)


# ============================================================
# 出口 1：模型直接回答，不调工具
# ============================================================

def test_no_tool_call_finishes_in_one_iteration(monkeypatch):
    llm = ScriptedLLM([_response(content="今天没有值得关注的事。")])
    monkeypatch.setattr(react, "chat", llm)

    result = react.run_react(system_prompt="s", user_message="u")

    assert result["iterations"] == 1
    assert result["tool_calls"] == []
    assert result["answer"] == "今天没有值得关注的事。"


# ============================================================
# 出口 2：调了工具，再给出最终回答
# ============================================================

def test_tool_result_is_appended_with_matching_id(monkeypatch, sandbox):
    llm = ScriptedLLM([
        _response(tool_calls=[_tool_call("call_1", "read_file", {"path": "preferences.json"})]),
        _response(content="简报写好了。"),
    ])
    monkeypatch.setattr(react, "chat", llm)

    result = react.run_react(system_prompt="s", user_message="u", sandbox_dir=sandbox)

    assert result["iterations"] == 2
    assert [record["name"] for record in result["tool_calls"]] == ["read_file"]
    assert result["answer"] == "简报写好了。"

    # 第二轮时模型看到的历史：assistant(tool_calls) 后面必须紧跟配对的 tool 消息。
    # 顺序错了或 id 对不上，真实 API 会直接 400。
    history = llm.calls[1]
    assert [m["role"] for m in history] == ["system", "user", "assistant", "tool"]
    assert history[2]["tool_calls"][0]["id"] == "call_1"
    assert history[3]["tool_call_id"] == "call_1"
    assert "keywords" in json.loads(history[3]["content"])["content"]


def test_multiple_tool_calls_in_one_turn_all_execute(monkeypatch, sandbox):
    """模型一口气要调两个工具时，两个都要执行、都要回填。"""
    llm = ScriptedLLM([
        _response(tool_calls=[
            _tool_call("c1", "list_dir", {}),
            _tool_call("c2", "read_file", {"path": "preferences.json"}),
        ]),
        _response(content="done"),
    ])
    monkeypatch.setattr(react, "chat", llm)

    result = react.run_react(system_prompt="s", user_message="u", sandbox_dir=sandbox)

    assert [r["name"] for r in result["tool_calls"]] == ["list_dir", "read_file"]
    assert len(llm.calls[1]) == 5          # system + user + assistant + 两条 tool


def test_bad_tool_arguments_do_not_crash_the_loop(monkeypatch, sandbox):
    """模型偶尔会吐出非法 JSON，循环必须扛住而不是抛异常。"""
    llm = ScriptedLLM([
        _response(tool_calls=[
            SimpleNamespace(
                id="c1",
                function=SimpleNamespace(name="list_dir", arguments="{不是合法 JSON"),
            )
        ]),
        _response(content="done"),
    ])
    monkeypatch.setattr(react, "chat", llm)

    result = react.run_react(system_prompt="s", user_message="u", sandbox_dir=sandbox)

    assert result["iterations"] == 2       # 没崩，正常走到第二轮
    assert result["tool_calls"][0]["args"] == {}


# ============================================================
# 出口 3：模型一直要调工具 → 必须被轮数上限拦住
# ============================================================

def test_stops_at_max_iterations(monkeypatch, sandbox):
    """永不满足的模型不能让后端无限转圈下去。"""
    llm = ScriptedLLM([
        _response(tool_calls=[_tool_call(f"c{i}", "list_dir", {})])
        for i in range(react.MAX_ITERATIONS + 5)
    ])
    monkeypatch.setattr(react, "chat", llm)

    result = react.run_react(system_prompt="s", user_message="u", sandbox_dir=sandbox)

    assert result["iterations"] == react.MAX_ITERATIONS
    assert len(llm.calls) == react.MAX_ITERATIONS   # 一次都没有多问
    assert "最大" in result["answer"]


# ============================================================
# 沙箱必须在 finally 里恢复
# ============================================================

def test_sandbox_is_restored_after_run(monkeypatch, sandbox):
    llm = ScriptedLLM([_response(content="ok")])
    monkeypatch.setattr(react, "chat", llm)

    react.run_react(system_prompt="s", user_message="u", sandbox_dir=sandbox)

    # 不恢复的话，下一个请求可能操作到上一个用户的目录
    assert _get_sandbox() == Path(DATA_DIR)


def test_sandbox_is_restored_even_if_llm_raises(monkeypatch, sandbox):
    def boom(messages, tools=None, **kwargs):
        raise RuntimeError("模型挂了")

    monkeypatch.setattr(react, "chat", boom)

    with pytest.raises(RuntimeError):
        react.run_react(system_prompt="s", user_message="u", sandbox_dir=sandbox)

    assert _get_sandbox() == Path(DATA_DIR)


# ============================================================
# 流式版：前端真正走的那条路径
# ============================================================

def test_stream_emits_text_tool_events_then_done(monkeypatch, sandbox):
    stream = ScriptedStream([
        [
            {"type": "content", "text": "先看看目录。"},
            {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "name": "list_dir", "arguments": "{}"},
            ]},
        ],
        [{"type": "content", "text": "这是最终简报。"}],
    ])
    monkeypatch.setattr(react, "chat_stream", stream)

    events = list(react.run_react_stream_realtime(
        system_prompt="s", user_message="u", sandbox_dir=sandbox,
    ))

    types = [e["type"] for e in events]

    assert types[-1] == "done"
    assert events[-1]["content"] == "这是最终简报。"
    assert "tool_call" in types
    assert "tool_result" in types

    # 中间的模型输出必须原样透传——前端的打字机效果靠的就是这些 text 事件
    assert any(
        e["type"] == "text" and e["content"] == "先看看目录。" for e in events
    )
