import os
import asyncio
import logging
from aiohttp import web
from telegram import Update

from fazkerbot import main as bot_main, handle
from user_side import application as user_app, init_application

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def combined_main():
    try:
        logger.debug("Starting combined_main")
        
        # Initialize user_side application and database first
        logger.info("Initializing user application...")
        await init_application()
        
        # Create single web app
        app = web.Application()
        app.router.add_get("/", handle)
        
        # Setup web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
        await site.start()
        
        logger.info("Starting both bots...")
        try:
            await asyncio.gather(
                bot_main(),
                user_app.start_polling(drop_pending_updates=True)  # Changed to start_polling
            )
        except Exception as e:
            logger.exception("Error in bot execution")
            raise
    except Exception as e:
        logger.exception("Fatal error in combined_main")
        raise
    finally:
        logger.info("Shutting down...")

if __name__ == "__main__":
    logger.info("Starting application...")
    asyncio.run(combined_main())
