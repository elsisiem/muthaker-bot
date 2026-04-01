import asyncio
import logging
import os
from datetime import datetime
from aiohttp import web
from telegram import Update

# Channel bot imports
from fazkerbot import (
    scheduler as channel_scheduler,
    CAIRO_TZ,
    test_telegram_connection,
    test_prayer_times,
    log_status_message,
    schedule_tasks,
    heartbeat
)

# User side imports
from user_side import web_app, application, init_db, start_user_reminder_scheduler, stop_user_reminder_scheduler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce noise from third-party libraries
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

async def run_channel_bot():
    """Run the channel posting bot (Quran + Athkar to channel)"""
    logger.info("Initializing channel bot...")

    await test_telegram_connection()
    logger.info("Telegram connection verified")

    prayer_test_result = await test_prayer_times()
    if not prayer_test_result:
        logger.warning("Prayer times test failed - scheduling may have issues")
    else:
        logger.info("Prayer times API verified")

    await log_status_message()

    channel_scheduler.start()
    logger.info("Scheduler started")

    await schedule_tasks()
    logger.info("Daily tasks scheduled")

    asyncio.create_task(heartbeat())
    logger.info("Channel bot initialized")

    last_scheduled_date = datetime.now(CAIRO_TZ).date()

    while True:
        now = datetime.now(CAIRO_TZ)
        current_date = now.date()

        if current_date != last_scheduled_date:
            logger.info(f"New day detected ({current_date}); refreshing schedules")
            await schedule_tasks()
            await log_status_message()
            last_scheduled_date = current_date

        await asyncio.sleep(60)

async def run_user_bot():
    """Run the user bot with polling to receive /start commands"""
    logger.info("User bot polling starting...")
    try:
        await application.initialize()
        await application.start()

        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("User bot polling active")

        await start_user_reminder_scheduler()
        logger.info("User reminder scheduler active")

        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logger.info("User bot polling stopped")
        await stop_user_reminder_scheduler()
        if application.updater and application.updater.running:
            await application.updater.stop()
        await application.stop()
    except Exception as e:
        logger.error(f"Error in user bot polling: {e}", exc_info=True)
        raise

async def main():
    """Main function to run all bot components concurrently."""
    try:
        logger.info("=" * 60)
        logger.info("MUTHAKER BOT - STARTING")
        logger.info("=" * 60)

        await init_db()
        logger.info("User database initialized")

        channel_task = asyncio.create_task(run_channel_bot())
        user_bot_task = asyncio.create_task(run_user_bot())

        runner = web.AppRunner(web_app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Web server started on port {port}")

        logger.info("=" * 60)
        logger.info("ALL COMPONENTS STARTED")
        logger.info("- Channel Bot (Quran + Athkar)")
        logger.info("- User Bot (listening for /start)")
        logger.info(f"- Web Server (port {port})")
        logger.info("=" * 60)

        while True:
            if channel_task.done():
                exc = channel_task.exception()
                raise RuntimeError(f"Channel bot task stopped unexpectedly: {exc}")

            if user_bot_task.done():
                exc = user_bot_task.exception()
                raise RuntimeError(f"User bot polling task stopped unexpectedly: {exc}")

            await asyncio.sleep(30)

    except Exception as e:
        logger.exception("Fatal error in main execution")
        raise
    finally:
        logger.info("Shutting down...")
        if channel_scheduler.running:
            channel_scheduler.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)
