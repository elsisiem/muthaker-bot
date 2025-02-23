import asyncio
from fazkerbot import main as bot_main
from user_side import application as user_app, engine, Base

async def combined_main():
    # Initialize user_side database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Start both applications
    await asyncio.gather(
        bot_main(),
        user_app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)
    )

if __name__ == "__main__":
    asyncio.run(combined_main())
