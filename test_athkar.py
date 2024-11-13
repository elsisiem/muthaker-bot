import os
import telegram
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from pytz import timezone

# Set up bot and chat details from environment variables
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
bot = telegram.Bot(token=TOKEN)

# Folder paths for images
ATHKAR_FOLDER = r'C:\Users\hatem\OneDrive\Desktop\FazkerBot\الأذكار'

# Cairo timezone using pytz
CAIRO_TZ = timezone('Africa/Cairo')

# Async function to send images with an optional caption
async def send_image(image_path, caption=""):
    with open(image_path, 'rb') as image_file:
        await bot.send_photo(chat_id=CHAT_ID, photo=image_file, caption=caption)

# Async function to send Athkar based on the time of day
async def send_athkar(time_of_day):
    if time_of_day == 'morning':
        athkar_image = f'{ATHKAR_FOLDER}\\أذكار_الصباح.jpg'
    else:
        athkar_image = f'{ATHKAR_FOLDER}\\أذكار_المساء.jpg'
    
    await send_image(athkar_image)  # No caption for Athkar

# Scheduler setup
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)  # Use Cairo timezone

# Function to test sending Athkar every minute
def test_send_athkar_every_minute():
    print(f"Test started at {datetime.now()}")
    scheduler.add_job(send_athkar, 'interval', minutes=1, args=['morning'])  # Sends morning Athkar every minute for testing

if __name__ == "__main__":
    print("Bot started at", datetime.now())

    # Initialize the event loop for asyncio
    loop = asyncio.get_event_loop()

    # Test Athkar sending every minute
    test_send_athkar_every_minute()

    # Start the scheduler
    scheduler.start()

    # Run the asyncio loop
    loop.run_forever()
