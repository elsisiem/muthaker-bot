import os
import asyncio
from aiohttp import web
from telegram import Update
from fazkerbot import main as bot_main, app
from user_side import application as user_app, init_application

async def combined_main():
    # Initialize web app
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
    await site.start()
    
    # Initialize user_side application and database
    await init_application()
    
    # Start both bots
    try:
        await asyncio.gather(
            bot_main(),
            user_app.start()
        )
    except Exception as e:
        print(f"Error in main: {e}")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(combined_main())
