import asyncio
import logging
import os
from aiohttp import web

# Channel bot imports
from fazkerbot import (
    bot as channel_bot,
    scheduler as channel_scheduler,
    test_telegram_connection,
    test_prayer_times,
    log_status_message,
    schedule_tasks,
    heartbeat
)

# User side imports
from user_side import web_app, application, init_db
from user_reminders import init_user_reminders

# Setup detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def run_channel_bot():
    """Run the channel posting bot (Quran + Athkar to channel)"""
    logger.info("🚀 Starting channel bot...")

    # Test Telegram connection
    await test_telegram_connection()

    # Test prayer times API
    prayer_test_result = await test_prayer_times()
    if not prayer_test_result:
        logger.warning("⚠️ Prayer times test failed - scheduling may not work correctly")

    # Log initial status message
    await log_status_message()

    # Start the scheduler
    logger.info("📅 Starting channel message scheduler...")
    channel_scheduler.start()
    logger.info("✅ Scheduler started")

    # Schedule initial tasks
    await schedule_tasks()

    # Start heartbeat
    asyncio.create_task(heartbeat())
    logger.info("💓 Heartbeat started")

    # Keep the channel bot running
    while True:
        await asyncio.sleep(60)

async def main():
    """Main function to run all bot components concurrently."""
    try:
        logger.info("=" * 60)
        logger.info("🎬 MUTHAKER BOT - STARTING ALL COMPONENTS")
        logger.info("=" * 60)

        # Initialize database and user side bot
        logger.info("📦 Initializing user preferences database...")
        await init_db()
        await application.initialize()
        logger.info("✅ User preferences database ready")

        # Start the channel posting bot
        logger.info("📡 Starting channel posting bot...")
        channel_task = asyncio.create_task(run_channel_bot())

        # Start user reminders scheduler
        logger.info("🔔 Starting user reminder scheduler...")
        user_reminder_task = await init_user_reminders()

        # Start the web server for webhook handling (for Telegram updates)
        logger.info("🌐 Starting web server for Telegram webhook...")
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
        await site.start()
        port = int(os.environ.get("PORT", 8080))
        logger.info(f"✅ Web server started on port {port}")

        logger.info("=" * 60)
        logger.info("🎉 ALL COMPONENTS STARTED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info("📊 Running:")
        logger.info("   • Channel Bot (Quran + Athkar posting)")
        logger.info("   • User Preferences (configuration)")
        logger.info("   • User Reminders (personalized DMs)")
        logger.info("=" * 60)

        # Keep the event loop running
        while True:
            await asyncio.sleep(3600)

    except Exception as e:
        logger.exception("💥 Fatal error in main execution")
        raise
    finally:
        logger.info("🛑 Shutting down...")
        if channel_scheduler.running:
            channel_scheduler.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Application stopped by user")
    except Exception as e:
        logger.critical(f"💀 Critical error: {e}", exc_info=True)
