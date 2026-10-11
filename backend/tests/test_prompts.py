"""提示词卫生测试。

提示词里的**示例文件名**会被模型照抄，这不是猜测，是实测：

    例子写的是   write_file("briefs/2026-10-10_14-30-25.md", "...")
    模型真的写了 briefs/2026-10-11_14-30-25.md

日期换成了当天，但时间部分 `14-30-25` 原样搬了过来——文件名叫 14:30，
实际写入时间是 23:36，差了 9 小时。这个特征就是这么确认的。

后果不是"文件名叫错"这么轻：同一天第二次生成会写到和第一次**完全相同**的路径，
把上一份简报直接覆盖掉。历史里少一份，不报错、不留痕。

所以这里钉死一条规则：**提示词里不允许出现具体的时间戳**。
写例子可以，但只能用 <年>-<月>-<日> 这种占位符。
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
    """只删掉例子还不够——得明说那个位置是占位符，别自己编时间。"""
    assert "占位符" in NEWS_AGENT_PROMPT
    assert "原样用" in NEWS_AGENT_PROMPT


def test_prompt_still_describes_the_exact_filename_shape():
    """提醒占位符的同时，不能让模型失去"文件名长什么样"的线索。"""
    assert "briefs/<年>-<月>-<日>_<时>-<分>-<秒>.md" in NEWS_AGENT_PROMPT
