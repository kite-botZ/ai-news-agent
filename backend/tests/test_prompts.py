"""提示词卫生测试：钉住三条容易在改动时被破坏的规则。

1. 提示词里的示例文件名会被模型照抄，同一天第二次生成会覆盖上一份简报，
   所以不允许出现具体的时间戳。
2. 提示词里的 RSS 源清单是手抄的，必须和 rss.py 的白名单一致。
3. README 里的源清单同理——它现在是用户挑关键词的依据，漏了一个源，
   照着 README 填偏好的用户就永远等不到那一类新闻，而且不会报错。
"""

import re
from pathlib import Path

from app.agent.prompts import NEWS_AGENT_PROMPT
from app.rss import RSS_SOURCES

TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")
URL = re.compile(r"https?://\S+")

README = Path(__file__).resolve().parents[2] / "README.md"


def _urls(text):
    """取出文本里的 URL，并去掉紧跟其后的标点（README 里 URL 是写在反引号里的）。"""
    return {u.rstrip("`),.;:，。") for u in URL.findall(text)}


def test_prompt_contains_no_literal_timestamp():
    found = TIMESTAMP.findall(NEWS_AGENT_PROMPT)

    assert found == [], (
        f"提示词里出现了具体的时间戳 {found}。模型会照抄它当文件名，"
        "同一天第二次生成就会覆盖掉第一份简报（静默丢数据）。"
        "请改成 <年>-<月>-<日> 这样的占位符。"
    )


def test_prompt_tells_the_model_the_filename_is_a_placeholder():
    """只删例子还不够，得明说那个位置是占位符，别自己编时间。"""
    assert "占位符" in NEWS_AGENT_PROMPT
    assert "原样用" in NEWS_AGENT_PROMPT


def test_prompt_still_describes_the_exact_filename_shape():
    """提醒占位符的同时，不能让模型失去"文件名长什么样"的线索。"""
    assert "briefs/<年>-<月>-<日>_<时>-<分>-<秒>.md" in NEWS_AGENT_PROMPT


def test_prompt_lists_exactly_the_whitelisted_sources():
    """提示词里的源清单必须和 rss.py 的白名单逐字一致。

    这份清单是手抄的，改 rss.py 忘了改这里，模型就会去试已经被删掉的源，
    或者压根不知道新加的源。两边对不上时这个断言会直接点出差在哪。
    """
    listed = _urls(NEWS_AGENT_PROMPT)
    whitelisted = {s["url"] for s in RSS_SOURCES}

    assert listed == whitelisted, (
        f"提示词里多出 {sorted(listed - whitelisted)}，"
        f"缺少 {sorted(whitelisted - listed)}。"
        "请把提示词「可选 RSS 源」一节同步成 rss.py 的 RSS_SOURCES。"
    )


def test_readme_lists_every_whitelisted_source():
    """README「内置的新闻源」表必须覆盖 rss.py 的全部源。

    只查「白名单是否都在 README 里」，不查相等——README 还有硅基流动之类的
    别的链接。漏一个源是最坏的情况：用户照 README 挑关键词，那一类新闻永远
    搜不出来，还不报错。
    """
    listed = _urls(README.read_text(encoding="utf-8"))
    missing = {s["url"] for s in RSS_SOURCES} - listed

    assert not missing, (
        f"README 里缺少这些源 {sorted(missing)}。"
        "请把 README「内置的新闻源」一节同步成 rss.py 的 RSS_SOURCES。"
    )
