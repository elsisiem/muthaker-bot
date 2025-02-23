import asyncio
from fazkerbot import main as bot_main
from user_side import main as user_main

async def combined_main():
    await asyncio.gather(
        bot_main(),
        user_main()
    )

if __name__ == "__main__":
    asyncio.run(combined_main())
