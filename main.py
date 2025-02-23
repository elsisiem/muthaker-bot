import os
import asyncio
import logging
from aiohttp import web
from telegram import Update

from fazkerbot import main as bot_main, handle
from user_side import application as user_app, init_application

# Setup logging to debug bot interactions
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def combined_main():
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
            user_app.initialize(),  # Make sure bot is initialized
            user_app.start(),       # Start receiving updates
            bot_main()
        )
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(combined_main())
