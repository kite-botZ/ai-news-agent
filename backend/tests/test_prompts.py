"""提示词卫生测试。

提示词里的示例文件名会被模型照抄，同一天第二次生成会写到和第一次相同的路径、
直接覆盖上一份简报。所以钉一条规则：提示词里不允许出现具体的时间戳，只能用 <年>-<月>-<日> 占位符。
"""

import re

from app.agent.prompts import NEWS_AGENT_PROMPT

TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}")


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
