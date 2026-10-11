"""定时任务：每天自动为所有用户生成新闻简报。

对应题目要求里的「每天自动为用户整理一份 AI 新闻简报」。

由 main.py 在应用启动时挂载（BackgroundScheduler，跑在后台线程里）。
通过环境变量控制：
- SCHEDULER_ENABLED    是否开启（默认 true）
- BRIEF_SCHEDULE_HOUR  每天几点（默认 8）
- BRIEF_SCHEDULE_MINUTE 分钟（默认 0）
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.agent.service import generate_all_briefs
from app.config import (
    BRIEF_SCHEDULE_HOUR,
    BRIEF_SCHEDULE_MINUTE,
    SCHEDULER_ENABLED,
)

logger = logging.getLogger("news_agent.scheduler")

_scheduler: BackgroundScheduler | None = None


def _run_daily_job() -> None:
    """定时任务体：给所有用户生成简报。"""
    logger.info("定时任务开始：为所有用户生成简报")
    try:
        results = generate_all_briefs()
        ok = [r for r in results if r["ok"]]
        failed = [r for r in results if not r["ok"]]
        logger.info("定时任务完成：成功 %d 个，失败 %d 个", len(ok), len(failed))
        for r in failed:
            logger.warning("用户 %s 生成失败：%s", r["username"], r.get("error"))
    except Exception:
        logger.exception("定时任务执行异常")


def start_scheduler() -> BackgroundScheduler | None:
    """启动后台调度器。未启用或已启动时返回现有实例/None。"""
    global _scheduler

    if not SCHEDULER_ENABLED:
        logger.info("定时任务未启用（SCHEDULER_ENABLED=false）")
        return None
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_daily_job,
        CronTrigger(hour=BRIEF_SCHEDULE_HOUR, minute=BRIEF_SCHEDULE_MINUTE),
        id="daily_brief",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "定时任务已启动：每天 %02d:%02d 为所有用户生成简报",
        BRIEF_SCHEDULE_HOUR,
        BRIEF_SCHEDULE_MINUTE,
    )
    return _scheduler


def shutdown_scheduler() -> None:
    """停止调度器（应用退出时调用）。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("定时任务已停止")
