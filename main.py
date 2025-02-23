import asyncio
from fazkerbot import main as bot_main
from user_side import application as user_app, init_db

async def combined_main():
    # Initialize user_side database
    await init_db()
    
    # Start both applications
    await asyncio.gather(
        bot_main(),
        user_app.run_polling(close_loop=False)
    )

if __name__ == "__main__":
    asyncio.run(combined_main())
