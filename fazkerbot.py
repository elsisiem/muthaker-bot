import os
import telegram
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import requests
from pytz import timezone

# Set up bot and chat details
TOKEN = "7365741617:AAE_TGjBcXAt81r5Hfe4rFlci-Os0q50nPk"  # Use the actual bot token
CHAT_ID = "-1002450375757"  # Use the actual chat ID for your private channel
bot = telegram.Bot(token=TOKEN)

# Folder paths for images
QURAN_PAGES_FOLDER = r'C:\Users\hatem\OneDrive\Desktop\FazkerBot\المصحف'
ATHKAR_FOLDER = r'C:\Users\hatem\OneDrive\Desktop\FazkerBot\الأذكار'
FASTING_FOLDER = r'C:\Users\hatem\OneDrive\Desktop\FazkerBot\الصيام'

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

# Async function to send images with an optional caption
async def send_image(image_path, caption=""):
    with open(image_path, 'rb') as image_file:
        await bot.send_photo(chat_id=CHAT_ID, photo=image_file, caption=caption)

# Async function to send Quran pages
async def send_quran_pages():
    global quran_page_number
    page_1 = f'{QURAN_PAGES_FOLDER}\\photo_{quran_page_number}.jpg'
    page_2 = f'{QURAN_PAGES_FOLDER}\\photo_{quran_page_number + 1}.jpg'
    
    # Send both pages together with the caption
    await bot.send_media_group(
        chat_id=CHAT_ID,
        media=[
            telegram.InputMediaPhoto(open(page_1, 'rb')),
            telegram.InputMediaPhoto(open(page_2, 'rb'))
        ],
        caption='ورد اليوم'  # Caption for the Quran pages
    )
    
    quran_page_number += 2
    if quran_page_number > 604:  # Reset after all 604 pages are sent
        quran_page_number = 1

# Async function to send Athkar based on the time of day
async def send_athkar(time_of_day):
    if time_of_day == 'morning':
        athkar_image = f'{ATHKAR_FOLDER}\\أذكار_الصباح.jpg'
    else:
        athkar_image = f'{ATHKAR_FOLDER}\\أذكار_المساء.jpg'
    
    await send_image(athkar_image)  # No caption for Athkar

# Async function to send fasting reminders twice a week
async def send_fasting_reminder(day):
    if day == 'sunday':
        fasting_image = f'{FASTING_FOLDER}\\صيام_الإثنين.jpg'
    else:
        fasting_image = f'{FASTING_FOLDER}\\صيام_الخميس.jpg'
    
    await send_image(fasting_image)  # Fasting reminder, no caption needed

# Calculate the next prayer times
async def schedule_prayer_times():
    timings = await get_prayer_times()
    fajr_time = datetime.strptime(timings['Fajr'], '%H:%M') + timedelta(minutes=30)
    asr_time = datetime.strptime(timings['Asr'], '%H:%M') + timedelta(minutes=30)
    
    fajr_time = CAIRO_TZ.localize(datetime.combine(datetime.now().date(), fajr_time.time()))
    asr_time = CAIRO_TZ.localize(datetime.combine(datetime.now().date(), asr_time.time()))
    
    return fajr_time, asr_time

# Scheduler setup
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)

async def schedule_tasks():
    fajr_time, asr_time = await schedule_prayer_times()
    
    # Schedule Athkar 30 mins after Fajr and Asr
    scheduler.add_job(send_athkar, 'date', run_date=fajr_time, args=['morning'])
    scheduler.add_job(send_athkar, 'date', run_date=asr_time, args=['night'])
    
    # Schedule Quran pages 15 minutes after night Athkar (Asr)
    quran_send_time = asr_time + timedelta(minutes=15)
    scheduler.add_job(send_quran_pages, 'date', run_date=quran_send_time)
    
    # Schedule fasting reminders twice a week (Sunday and Wednesday at 8 PM Cairo time)
    scheduler.add_job(send_fasting_reminder, 'cron', day_of_week='sun', hour=20, minute=0, args=['sunday'], timezone=CAIRO_TZ)
    scheduler.add_job(send_fasting_reminder, 'cron', day_of_week='wed', hour=20, minute=0, args=['wednesday'], timezone=CAIRO_TZ)
    
    # Start the scheduler
    scheduler.start()

if __name__ == "__main__":
    print("Bot started at", datetime.now())

    # Initialize the asyncio event loop
    loop = asyncio.get_event_loop()

    # Schedule all tasks
    loop.run_until_complete(schedule_tasks())

    # Run the asyncio loop
    loop.run_forever()
