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

# Setup detailed logging
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
    logger.info("🌅 Initializing channel bot...")

    # Test Telegram connection
    logger.info("🔗 Testing Telegram connection...")
    await test_telegram_connection()
    logger.info("✅ Telegram connection verified")

    # Test prayer times API
    logger.info("📍 Testing prayer times API...")
    prayer_test_result = await test_prayer_times()
    if not prayer_test_result:
        logger.warning("⚠️  Prayer times test failed - scheduling may have issues")
    else:
        logger.info("✅ Prayer times API verified")

    # Log initial status
    logger.info("📋 Logging initial bot status...")
    await log_status_message()

    # Start the scheduler
    logger.info("📅 Starting scheduler...")
    channel_scheduler.start()
    logger.info("✅ Scheduler running")

    # Schedule initial tasks
    logger.info("⏰ Scheduling daily tasks...")
    await schedule_tasks()
    logger.info("✅ Daily tasks scheduled")

    # Start heartbeat
    logger.info("💓 Starting heartbeat monitor...")
    asyncio.create_task(heartbeat())
    logger.info("✅ Channel bot fully initialized")
    logger.info("")

    # Keep the channel bot running
    while True:
        await asyncio.sleep(60)

async def main():
    """Main function to run all bot components concurrently."""
    try:
        logger.info("")
        logger.info("🎬 " + "=" * 56)
        logger.info("🎬 MUTHAKER BOT - STARTING ALL COMPONENTS")
        logger.info("🎬 " + "=" * 56)
        logger.info("")

        # Initialize database and user side bot
        logger.info("📦 Initializing user preferences database...")
        await init_db()
        await application.initialize()
        logger.info("✅ User preferences database initialized")
        logger.info("")

        # Start the channel posting bot
        logger.info("📡 Starting channel posting bot...")
        channel_task = asyncio.create_task(run_channel_bot())
        logger.info("✅ Channel bot task created")
        logger.info("")

        # Start the web server for webhook handling (for Telegram updates)
        logger.info("🌐 Starting web server for Telegram webhook...")
        runner = web.AppRunner(web_app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"✅ Web server started on port {port}")
        logger.info("")

        logger.info("🎉 " + "=" * 56)
        logger.info("🎉 ALL COMPONENTS STARTED SUCCESSFULLY")
        logger.info("🎉 " + "=" * 56)
        logger.info("")
        logger.info("📊 Running:")
        logger.info("   ✓ Channel Bot (Quran + Athkar → channel)")
        logger.info("   ✓ User Bot (preferences & personalized DMs)")
        logger.info("   ✓ Web Server (webhook @ port " + str(port) + ")")
        logger.info("")

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
        logger.info("")
        logger.info("👋 Application stopped by user")
    except Exception as e:
        logger.critical(f"💀 Critical error: {e}", exc_info=True)
