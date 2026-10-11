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

    这里**故意不调 set_sandbox**：沙箱现在是 execute_tool 的显式参数，不是全局状态。
    留着那句反而会把坑盖住——见文件末尾那条回归用例。
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
    """循环不该去动全局沙箱——动了就会在并发时串到别人的目录。"""
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

    # 中间的模型输出必须原样透传——前端的打字机效果靠的就是这些 text 事件
    assert any(
        e["type"] == "text" and e["content"] == "先看看目录。" for e in events
    )


# ============================================================
# 回归：空白输出曾经把前端整片挡住
# ============================================================

def test_stream_drops_whitespace_only_text_chunks(monkeypatch, sandbox):
    """调工具的轮次里模型会推 "\\n\\n" 这类纯空白，不能透传给前端。

    JS 里 "\\n\\n" 是**真值**：前端把它攒进 streamText 之后，
    `streamText || event.content` 这个兜底就整个失效了，
    用户看到的是一块有内容但什么都不显示的空白面板。
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
    """模型最后一条回复是空白（或干脆什么都没说）时，done 必须带上明确的提示。

    实测就会这样：模型把内容全写进文件，最后一条回复只剩 "\\n\\n"。
    它非空、truthy，直接透传的话会顶掉「未生成」这句提示，前端弹出一个空白弹窗。
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
# 回归：走 HTTP SSE 时沙箱曾经完全失效
# ============================================================

def test_sandbox_survives_starlette_threadpool(monkeypatch, tmp_path):
    """这条用例存在的唯一理由：上面那些用 list() 直接消费生成器的测试**抓不到**这个坑。

    前端真正走的是 HTTP SSE，Starlette 用 iterate_in_threadpool 消费同步生成器，
    每调用一次 next() 就是一次新的线程池调度，而 anyio 每次都从事件循环线程
    重新拷一份上下文。结果：生成器里 set 的全局沙箱在下一次恢复时就没了，
    _get_sandbox() 静默退回 data/。

    实测表现（改之前，走真 HTTP）：
        📖 正在读取偏好…
        ⚠️ read_file 失败：文件不存在：preferences.json
    模型读不到偏好，却照样硬写了一份简报 —— 不报错，只是内容不对。
    更糟的是沙箱隔离失效：A 用户可以读到 B 用户的文件。

    所以这里必须用和 Starlette **一模一样**的方式消费，否则等于没测。
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
