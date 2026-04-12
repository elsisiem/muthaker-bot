import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

reminder_scheduler = AsyncIOScheduler()


async def start_user_reminder_scheduler():
    if not reminder_scheduler.running:
        reminder_scheduler.start()
        logger.info("User reminder scheduler active")


async def stop_user_reminder_scheduler():
    if reminder_scheduler.running:
        reminder_scheduler.shutdown(wait=False)
        logger.info("User reminder scheduler stopped")
