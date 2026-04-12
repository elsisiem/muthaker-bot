import logging
from datetime import datetime, timedelta
import pytz

from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .db import list_active_users

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)
CAIRO_TZ = pytz.timezone("Africa/Cairo")

reminder_scheduler = AsyncIOScheduler()
bot_application = None


def set_application(app):
    global bot_application
    bot_application = app


async def start_user_reminder_scheduler():
    if not reminder_scheduler.running:
        reminder_scheduler.start()
        logger.info("User reminder scheduler active")


def clear_jobs(prefixes: tuple[str, ...] = ("user_reminder_", "prayer_reminder_")):
    for job in reminder_scheduler.get_jobs():
        if any(job.id.startswith(p) for p in prefixes):
            reminder_scheduler.remove_job(job.id)


async def send_text_reminder(telegram_id: str, text_value: str):
    if not bot_application:
        return
    await bot_application.bot.send_message(chat_id=int(telegram_id), text=text_value)


def add_interval_job(telegram_id: str, seconds: int, text_value: str):
    reminder_scheduler.add_job(
        send_text_reminder,
        trigger=IntervalTrigger(seconds=max(60, seconds), timezone=CAIRO_TZ),
        args=[telegram_id, text_value],
        id=f"user_reminder_{telegram_id}",
        replace_existing=True,
        misfire_grace_time=60,
    )


def add_prayer_job(telegram_id: str, run_time, text_value: str, job_suffix: str, timezone_name: str | None = None):
    tz = pytz.timezone(timezone_name or "Africa/Cairo")
    reminder_scheduler.add_job(
        send_text_reminder,
        trigger=DateTrigger(run_date=run_time, timezone=tz),
        args=[telegram_id, text_value],
        id=f"prayer_reminder_{telegram_id}_{job_suffix}",
        replace_existing=True,
        misfire_grace_time=300,
    )


async def rebuild_all_jobs(reminder_builder):
    clear_jobs()
    users = await list_active_users()
    for user in users:
        await reminder_builder(user)
    logger.info("User reminder scheduler refreshed: %s jobs", len(reminder_scheduler.get_jobs()))


async def stop_user_reminder_scheduler():
    if reminder_scheduler.running:
        reminder_scheduler.shutdown(wait=False)
        logger.info("User reminder scheduler stopped")
