import os
import logging
import requests
import pytz
from datetime import datetime, timedelta
import asyncio
import aiohttp
from telegram import Bot
import psycopg2
from psycopg2.extras import DictCursor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

# Constants
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
DATABASE_URL = os.environ['DATABASE_URL']
CAIRO_TZ = pytz.timezone('Africa/Cairo')
API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}

GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"
MISC_URL = f"{GITHUB_RAW_URL}/%D9%85%D9%86%D9%88%D8%B9"

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize bot and scheduler
bot = Bot(TOKEN)
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)

# Database setup
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def setup_database():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS messages
                          (id SERIAL PRIMARY KEY, message_id INTEGER, message_type TEXT)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS quran_progress
                          (id SERIAL PRIMARY KEY, last_page INTEGER)''')
            conn.commit()

setup_database()

async def fetch_prayer_times():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=API_PARAMS) as response:
            data = await response.json()
            return data['data']['timings']

def get_next_quran_pages():
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT last_page FROM quran_progress WHERE id = 1')
            result = cur.fetchone()
            if result:
                last_page = result['last_page']
            else:
                last_page = 219  # Start from page 220
                cur.execute('INSERT INTO quran_progress (id, last_page) VALUES (1, 219)')

            next_page = last_page + 2
            if next_page > 604:
                next_page = 1

            cur.execute('UPDATE quran_progress SET last_page = %s WHERE id = 1', (next_page,))
            conn.commit()

    return next_page, next_page + 1

async def send_message(chat_id, text, parse_mode='HTML'):
    message = await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    return message.message_id

async def send_photo(chat_id, photo_url, caption=None):
    message = await bot.send_photo(chat_id=chat_id, photo=photo_url, caption=caption)
    return message.message_id

async def send_media_group(chat_id, media):
    messages = await bot.send_media_group(chat_id=chat_id, media=media)
    return [message.message_id for message in messages]

async def delete_message(chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

async def send_athkar(athkar_type):
    caption = "#أذكار_الصباح" if athkar_type == "morning" else "#أذكار_المساء"
    image_url = f"{ATHKAR_URL}/{'أذاكر_الصباح' if athkar_type == 'morning' else 'أذكار_المساء'}.png"
    
    message_id = await send_photo(CHAT_ID, image_url, caption)
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO messages (message_id, message_type) VALUES (%s, %s)', (message_id, athkar_type))
            
            if athkar_type == "morning":
                cur.execute('SELECT message_id FROM messages WHERE message_type = %s', ('night',))
            else:
                cur.execute('SELECT message_id FROM messages WHERE message_type = %s', ('morning',))
            
            old_message = cur.fetchone()
            if old_message:
                await delete_message(CHAT_ID, old_message[0])
                cur.execute('DELETE FROM messages WHERE message_id = %s', (old_message[0],))
            conn.commit()

async def send_quran_pages():
    page1, page2 = get_next_quran_pages()
    page_1_url = f"{QURAN_PAGES_URL}/photo_{page1}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{page2}.jpg"
    
    media = [
        {"type": "photo", "media": page_1_url},
        {"type": "photo", "media": page_2_url, "caption": "#ورد_اليوم"}
    ]
    
    message_ids = await send_media_group(CHAT_ID, media)
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for message_id in message_ids:
                cur.execute('INSERT INTO messages (message_id, message_type) VALUES (%s, %s)', (message_id, "quran"))
            conn.commit()

async def send_prayer_notification(prayer_name):
    prayer_image_url = f"{MISC_URL}/حي_على_الصلاة.png"
    caption = f"صلاة {prayer_name}"
    
    message_id = await send_photo(CHAT_ID, prayer_image_url, caption)
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO messages (message_id, message_type) VALUES (%s, %s)', (message_id, "prayer"))
            conn.commit()

async def schedule_tasks():
    prayer_times = await fetch_prayer_times()
    
    now = datetime.now(CAIRO_TZ)
    schedule_info = []

    for prayer, time_str in prayer_times.items():
        if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
            prayer_time = CAIRO_TZ.localize(datetime.strptime(f"{now.date()} {time_str}", "%Y-%m-%d %H:%M"))
            
            if prayer == 'Fajr':
                athkar_time = prayer_time + timedelta(minutes=35)
                scheduler.add_job(send_athkar, trigger=DateTrigger(run_date=athkar_time, timezone=CAIRO_TZ), args=["morning"])
                schedule_info.append(f"Morning Athkar: {athkar_time.strftime('%H:%M')}")
            
            elif prayer == 'Asr':
                athkar_time = prayer_time + timedelta(minutes=35)
                quran_time = prayer_time + timedelta(minutes=45)
                scheduler.add_job(send_athkar, trigger=DateTrigger(run_date=athkar_time, timezone=CAIRO_TZ), args=["night"])
                scheduler.add_job(send_quran_pages, trigger=DateTrigger(run_date=quran_time, timezone=CAIRO_TZ))
                schedule_info.append(f"Night Athkar: {athkar_time.strftime('%H:%M')}")
                schedule_info.append(f"Quran Pages: {quran_time.strftime('%H:%M')}")
            
            scheduler.add_job(send_prayer_notification, trigger=DateTrigger(run_date=prayer_time, timezone=CAIRO_TZ), args=[prayer])
            schedule_info.append(f"{prayer} Prayer: {prayer_time.strftime('%H:%M')}")

    schedule_message = "Today's Schedule:\n" + "\n".join(schedule_info)
    await send_message(CHAT_ID, schedule_message)

    logger.info(f"Tasks scheduled for {now.date()}")

async def main():
    while True:
        now = CAIRO_TZ.localize(datetime.now())
        next_day = CAIRO_TZ.localize(now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        
        await schedule_tasks()
        
        wait_seconds = (next_day - now).total_seconds()
        await asyncio.sleep(wait_seconds)

if __name__ == "__main__":
    scheduler.start()
    asyncio.run(main())