import os
import telegram
import asyncio
from datetime import datetime
import time

# Set up bot and chat details
TOKEN = "7365741617:AAE_TGjBcXAt81r5Hfe4rFlci-Os0q50nPk"  # Use the actual bot token
CHAT_ID = "-1002450375757"  # Use the actual chat ID for your private channel
bot = telegram.Bot(token=TOKEN)

# Folder path for images
QURAN_PAGES_FOLDER = r'C:\Users\hatem\OneDrive\Desktop\FazkerBot\المصحف'

# Quran page counter, starting from 196
quran_page_number = 196

async def send_image(image_path):
    with open(image_path, 'rb') as image_file:
        await bot.send_photo(chat_id=CHAT_ID, photo=image_file)

async def send_quran_pages():
    global quran_page_number
    page_1 = f'{QURAN_PAGES_FOLDER}\\photo_{quran_page_number}.jpg'
    page_2 = f'{QURAN_PAGES_FOLDER}\\photo_{quran_page_number + 1}.jpg'

    # Send both pages
    await bot.send_media_group(
        chat_id=CHAT_ID,
        media=[
            telegram.InputMediaPhoto(open(page_1, 'rb')),
            telegram.InputMediaPhoto(open(page_2, 'rb'))
        ],
        caption='ورد اليوم'  # Caption for the Quran pages
    )

    print(f'Sent pages: {quran_page_number} and {quran_page_number + 1}')  # Log for confirmation
    
    # Increment the page number by 2 for the next send
    quran_page_number += 2

async def main():
    while quran_page_number <= 604:  # Stop after the last page
        await send_quran_pages()
        await asyncio.sleep(20)  # Wait for 20 seconds before sending again

if __name__ == "__main__":
    print("Test script started at", datetime.now())

    # Initialize the asyncio event loop
    loop = asyncio.get_event_loop()

    # Run the main function
    loop.run_until_complete(main())
