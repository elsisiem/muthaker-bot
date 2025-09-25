import os
import asyncio
import logging
from aiohttp import web

# Import the channel bot components 
from fazkerbot import (
    bot, scheduler, test_telegram_connection, test_prayer_times,
    log_status_message, schedule_tasks, heartbeat, handle
)

# Import user interaction components  
from user_side import init_application

# Setup detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def combined_main():
    """Main function that runs both channel bot and user interaction with the SAME bot"""
    try:
        logger.info("🚀 Starting combined bot system (single bot for both functions)...")
        
        # Initialize user interaction database and handlers
        logger.info("📋 Initializing user interaction system...")
        await init_application()
        logger.info("✅ User interaction system initialized")
        
        # Setup web server for Heroku
        app = web.Application()
        app.router.add_get("/", handle)
        
        port = int(os.environ.get('PORT', 8080))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"🌐 Web server started on port {port}")
        
        # Test connections for the bot (same bot for both functions)
        logger.info("🔍 Testing Telegram connection...")
        await test_telegram_connection()
        
        prayer_test_result = await test_prayer_times()
        if not prayer_test_result:
            logger.warning("⚠️ Prayer times test failed - scheduling may not work correctly")
        
        await log_status_message()
        
        # Start the scheduler for channel posts
        logger.info("📅 Starting channel message scheduler...")
        scheduler.start()
        logger.info("✅ Scheduler started")
        
        # Schedule initial tasks for channel
        await schedule_tasks()
        
        # Start heartbeat for channel bot
        heartbeat_task = asyncio.create_task(heartbeat())
        logger.info("💓 Heartbeat started")
        
        # Start user interaction polling with the SAME bot
        logger.info("👥 Starting user interaction polling (same bot)...")
        from user_side import application as user_app
        user_polling_task = asyncio.create_task(
            user_app.run_polling(drop_pending_updates=True)
        )
        logger.info("✅ User interaction polling started")
        
        # Channel bot scheduling loop (from original fazkerbot main)
        last_scheduled_date = None
        
        logger.info("🎯 Both systems are now running with ONE bot!")
        logger.info("📢 Channel posting: Active (same bot)")  
        logger.info("👤 User interactions: Active (same bot)")
        
        # Main loop for channel scheduling
        while True:
            try:
                from datetime import datetime
                import pytz
                CAIRO_TZ = pytz.timezone('Africa/Cairo')
                
                now = datetime.now(CAIRO_TZ)
                current_date = now.date()

                if last_scheduled_date != current_date:
                    logger.info(f"📅 Scheduling tasks for new date: {current_date}")
                    await schedule_tasks()
                    await log_status_message()
                    last_scheduled_date = current_date

                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(60)
                
    except Exception as e:
        logger.exception("💥 Fatal error in combined_main")
        raise
    finally:
        logger.info("🛑 Shutting down...")
        try:
            if scheduler.running:
                scheduler.shutdown()
            if 'heartbeat_task' in locals():
                heartbeat_task.cancel()
            if 'user_polling_task' in locals():
                user_polling_task.cancel()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

if __name__ == "__main__":
    logger.info("🎬 Starting muthaker bot application...")
    try:
        asyncio.run(combined_main())
    except KeyboardInterrupt:
        logger.info("👋 Application stopped by user")
    except Exception as e:
        logger.critical(f"💀 Critical error in main execution: {e}", exc_info=True)
