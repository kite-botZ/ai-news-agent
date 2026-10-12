"""ReAct 循环测试：用假 LLM 跑，不联网、不花钱，只验证循环的控制流。

换掉 LLM 后循环就是个普通状态机，可以逐个出口验证：不调工具一轮就结束；调了工具结果要
回填进消息历史且 tool_call_id 配对；一直要调工具时到 MAX_ITERATIONS 必须停；跑完沙箱必须恢复。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from starlette.concurrency import iterate_in_threadpool

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
    """一个模拟的用户目录（含 preferences.json）。

    故意不调 set_sandbox：沙箱现在靠 execute_tool 的显式参数传，不是全局状态。
    """
    (tmp_path / "preferences.json").write_text(
        '{"keywords": ["AI"]}', encoding="utf-8"
    )
    return tmp_path


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
# 沙箱：靠显式传参，不靠全局状态
# ============================================================

def test_tools_run_inside_the_given_sandbox(monkeypatch, sandbox):
    """run_react(sandbox_dir=X) 时，工具必须真的在 X 里操作。"""
    llm = ScriptedLLM([
        _response(tool_calls=[_tool_call("c1", "read_file", {"path": "preferences.json"})]),
        _response(content="done"),
    ])
    monkeypatch.setattr(react, "chat", llm)

    result = react.run_react(system_prompt="s", user_message="u", sandbox_dir=sandbox)

    tool_result = result["tool_calls"][0]["result"]
    assert "error" not in tool_result, f"沙箱没生效：{tool_result}"
    assert "AI" in tool_result["content"]


def test_run_react_leaves_global_sandbox_untouched(monkeypatch, sandbox):
    """循环不该去动全局沙箱，动了就会在并发时串到别人的目录。"""
    set_sandbox(None)
    llm = ScriptedLLM([_response(content="ok")])
    monkeypatch.setattr(react, "chat", llm)

    react.run_react(system_prompt="s", user_message="u", sandbox_dir=sandbox)

    assert _get_sandbox() == Path(DATA_DIR)


def test_run_react_leaves_global_sandbox_untouched_on_error(monkeypatch, sandbox):
    set_sandbox(None)

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

    # 中间的模型输出必须原样透传，前端的打字机效果靠的就是这些 text 事件
    assert any(
        e["type"] == "text" and e["content"] == "先看看目录。" for e in events
    )


def test_stream_forwards_reasoning_without_polluting_the_answer(monkeypatch, sandbox):
    """思考过程要推给前端，但不能混进最终回答（done 的 content 会落盘成简报）。"""
    stream = ScriptedStream([
        [
            {"type": "reasoning", "text": "用户要看 AI 新闻，"},
            {"type": "reasoning", "text": "先读偏好。"},
            {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "name": "list_dir", "arguments": "{}"},
            ]},
        ],
        [
            {"type": "reasoning", "text": "目录里没有 briefs。"},
            {"type": "content", "text": "今天的简报已生成并保存。"},
        ],
    ])
    monkeypatch.setattr(react, "chat_stream", stream)

    events = list(react.run_react_stream_realtime(
        system_prompt="s", user_message="u", sandbox_dir=sandbox,
    ))

    reasoning = [e["content"] for e in events if e["type"] == "reasoning"]
    assert "先读偏好。" in reasoning

    done = [e for e in events if e["type"] == "done"]
    assert done[0]["content"] == "今天的简报已生成并保存。"
    assert "内心戏" not in done[0]["content"]
    assert "用户要看" not in done[0]["content"], "思考过程漏进最终回答了"


def test_reasoning_is_not_treated_as_final_text(monkeypatch, sandbox):
    """只有思考、没有任何 content 时，回答仍应判为"未生成"，不能拿思考顶替。"""
    stream = ScriptedStream([
        [{"type": "reasoning", "text": "我不知道该干嘛"}],
    ])
    monkeypatch.setattr(react, "chat_stream", stream)

    events = list(react.run_react_stream_realtime(
        system_prompt="s", user_message="u", sandbox_dir=sandbox,
    ))

    assert not [e for e in events if e["type"] == "text"]
    assert [e for e in events if e["type"] == "done"][0]["content"] == "（未生成最终回答）"


# ============================================================
# 回归：纯空白输出不能透传给前端
# ============================================================

def test_stream_drops_whitespace_only_text_chunks(monkeypatch, sandbox):
    """调工具的轮次里模型会推 "\\n\\n" 这类纯空白，不能透传给前端。

    JS 里 "\\n\\n" 是真值，前端攒进 streamText 后 `streamText || event.content` 兜底失效，
    用户会看到一块什么都不显示的空白面板。
    """
    stream = ScriptedStream([
        [
            {"type": "content", "text": "\n\n"},
            {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "name": "list_dir", "arguments": "{}"},
            ]},
        ],
        [{"type": "content", "text": "最终简报"}],
    ])
    monkeypatch.setattr(react, "chat_stream", stream)

    events = list(react.run_react_stream_realtime(
        system_prompt="s", user_message="u", sandbox_dir=sandbox,
    ))

    texts = [e["content"] for e in events if e["type"] == "text"]
    assert texts == ["最终简报"], f"纯空白被透传给前端了：{texts}"


def test_empty_or_whitespace_final_answer_is_reported_as_missing(monkeypatch, sandbox):
    """模型最后一条回复是空白（或什么都没说）时，done 必须带上「未生成」提示。

    模型把内容全写进文件时，最后一条回复会只剩 "\\n\\n"。它 truthy，
    直接透传会顶掉提示，前端弹空白弹窗。
    """
    for blank in ("\n\n", "", "   "):
        stream = ScriptedStream([[{"type": "content", "text": blank}]])
        monkeypatch.setattr(react, "chat_stream", stream)

        events = list(react.run_react_stream_realtime(
            system_prompt="s", user_message="u", sandbox_dir=sandbox,
        ))

        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        assert done[0]["content"] == "（未生成最终回答）", f"blank={blank!r}"


# ============================================================
# 回归：走 HTTP SSE 时沙箱不能失效
# ============================================================

def test_sandbox_survives_starlette_threadpool(monkeypatch, tmp_path):
    """必须用和 Starlette 一样的方式消费生成器，用 list() 直接消费抓不到这个坑。

    前端走的是 HTTP SSE，Starlette 用 iterate_in_threadpool 消费同步生成器，每调一次
    next() 就是一次新的线程池调度，anyio 会从事件循环线程重新拷一份上下文。生成器里
    set 的全局沙箱于是下一次恢复时就没了，_get_sandbox() 静默退回 data/：模型读不到偏好
    却照样硬写简报，A 用户还能读到 B 用户的文件。
    """
    user_dir = tmp_path / "users" / "alice"
    user_dir.mkdir(parents=True)
    (user_dir / "preferences.json").write_text(
        '{"keywords": ["AI", "大模型"]}', encoding="utf-8"
    )

    stream = ScriptedStream([
        [
            {"type": "tool_calls", "tool_calls": [
                {"id": "c1", "name": "read_file",
                 "arguments": '{"path": "preferences.json"}'},
            ]},
        ],
        [{"type": "content", "text": "ok"}],
    ])
    monkeypatch.setattr(react, "chat_stream", stream)

    # 确保全局沙箱处于默认值，否则"读到"可能只是上一次测试的残留
    set_sandbox(None)

    results = []

    async def consume():
        async for event in iterate_in_threadpool(
            react.run_react_stream_realtime(
                system_prompt="s", user_message="u", sandbox_dir=user_dir,
            )
        ):
            if event["type"] == "tool_result":
                results.append(event["result"])

    anyio.run(consume)

    assert len(results) == 1
    assert "error" not in results[0], (
        f"沙箱没跟着生成器走，工具读的是 data/ 而不是用户目录：{results[0]}"
    )
    assert "大模型" in results[0]["content"]
