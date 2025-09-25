import asyncio
import logging
from fazkerbot import (
    bot as channel_bot,
    scheduler as channel_scheduler,
    test_telegram_connection,
    test_prayer_times,
    log_status_message,
    schedule_tasks,
    heartbeat
)
from user_side import application as user_app, init_application

# Setup detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def run_channel_bot():
    """Run the channel posting bot."""
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

async def run_user_interaction_bot():
    """Run the user interaction bot."""
    logger.info("👥 Starting user interaction bot...")

    # Initialize user interaction system
    await init_application()
    logger.info("✅ User interaction system initialized")

    # Start polling for user interactions
    await user_app.run_polling(drop_pending_updates=True)

async def main():
    """Main function to run both bots concurrently."""
    try:
        logger.info("🎬 Starting combined bot system...")

        # Run both bots concurrently
        await asyncio.gather(
            run_channel_bot(),
            run_user_interaction_bot()
        )
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
