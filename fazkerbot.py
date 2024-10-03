import os
import telegram
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import requests
from pytz import timezone

# Set up bot and chat details
TOKEN = os.getenv("TELEGRAM_TOKEN")  # Use the environment variable for the bot token
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Use the environment variable for the chat ID
bot = telegram.Bot(token=TOKEN)

# Folder paths for images (adjusted for GitHub repository structure)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Base directory of the script
QURAN_PAGES_FOLDER = os.path.join(BASE_DIR, 'المصحف')  # Adjusted path
ATHKAR_FOLDER = os.path.join(BASE_DIR, 'الأذكار')  # Adjusted path
FASTING_FOLDER = os.path.join(BASE_DIR, 'الصيام')  # Adjusted path

# Quran page counter, starting from 196
quran_page_number = 196

# Cairo timezone using pytz
CAIRO_TZ = timezone('Africa/Cairo')

# Prayer times for Egypt (Cairo)
API_URL = "http://api.aladhan.com/v1/timingsByCity"
params = {
    'city': 'Cairo',
    'country': 'Egypt',
    'method': 3  # Muslim World League
}

async def get_prayer_times():
    response = requests.get(API_URL, params=params)
    data = response.json()
    timings = data['data']['timings']
    return timings

async def send_image(image_path, caption=""):
    with open(image_path, 'rb') as image_file:
        await bot.send_photo(chat_id=CHAT_ID, photo=image_file, caption=caption)

async def send_quran_pages():
    global quran_page_number
    page_1 = f'{QURAN_PAGES_FOLDER}/photo_{quran_page_number}.jpg'
    page_2 = f'{QURAN_PAGES_FOLDER}/photo_{quran_page_number + 1}.jpg'
    
    await bot.send_media_group(
        chat_id=CHAT_ID,
        media=[
            telegram.InputMediaPhoto(open(page_1, 'rb')),
            telegram.InputMediaPhoto(open(page_2, 'rb'))
        ],
        caption='ورد اليوم'
    )
    
    quran_page_number += 2
    if quran_page_number > 604:
        quran_page_number = 1

async def send_athkar(time_of_day):
    athkar_image = f'{ATHKAR_FOLDER}/أذكار_{"الصباح" if time_of_day == "morning" else "المساء"}.jpg'
    await send_image(athkar_image)

async def send_fasting_reminder(day):
    fasting_image = f'{FASTING_FOLDER}/صيام_{"الإثنين" if day == "sunday" else "الخميس"}.jpg'
    await send_image(fasting_image)

async def schedule_prayer_times():
    timings = await get_prayer_times()
    fajr_time = datetime.strptime(timings['Fajr'], '%H:%M') + timedelta(minutes=30)
    asr_time = datetime.strptime(timings['Asr'], '%H:%M') + timedelta(minutes=30)
    
    fajr_time = CAIRO_TZ.localize(datetime.combine(datetime.now().date(), fajr_time.time()))
    asr_time = CAIRO_TZ.localize(datetime.combine(datetime.now().date(), asr_time.time()))
    
    return fajr_time, asr_time

scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)

async def schedule_tasks():
    fajr_time, asr_time = await schedule_prayer_times()
    
    scheduler.add_job(send_athkar, 'date', run_date=fajr_time, args=['morning'])
    scheduler.add_job(send_athkar, 'date', run_date=asr_time, args=['night'])
    
    quran_send_time = asr_time + timedelta(minutes=15)
    scheduler.add_job(send_quran_pages, 'date', run_date=quran_send_time)
    
    scheduler.add_job(send_fasting_reminder, 'cron', day_of_week='sun', hour=20, minute=0, args=['sunday'], timezone=CAIRO_TZ)
    scheduler.add_job(send_fasting_reminder, 'cron', day_of_week='wed', hour=20, minute=0, args=['wednesday'], timezone=CAIRO_TZ)
    
    scheduler.start()

if __name__ == "__main__":
    print("Bot started at", datetime.now())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(schedule_tasks())
    loop.run_forever()
