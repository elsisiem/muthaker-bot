import asyncio
from fazkerbot import send_athkar, send_quran_pages, get_next_quran_pages, CHAT_ID

async def test_all():
    print("Testing Quran page calculation...")
    pages = get_next_quran_pages()
    print(f"Next Quran pages would be: {pages}")
    
    print("\nTesting Athkar sending...")
    print("Sending morning athkar...")
    await send_athkar('morning')
    await asyncio.sleep(5)  # Wait 5 seconds
    
    print("Sending evening athkar...")
    await send_athkar('night')
    await asyncio.sleep(5)  # Wait 5 seconds
    
    print("\nTesting Quran pages sending...")
    await send_quran_pages()

if __name__ == "__main__":
    asyncio.run(test_all())
