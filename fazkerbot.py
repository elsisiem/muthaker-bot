import os
import logging
import requests
import pytz
from datetime import datetime, timedelta
import asyncio
import aiohttp
from telegram import Bot
from psycopg2 import pool
from psycopg2.extras import DictCursor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

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
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize bot and scheduler
bot = Bot(TOKEN)
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)

# Database setup with connection pooling
min_connections = 1
max_connections = 10
connection_pool = pool.SimpleConnectionPool(min_connections, max_connections, DATABASE_URL, sslmode='require')

def get_db_connection():
    return connection_pool.getconn()

def release_db_connection(conn):
    connection_pool.putconn(conn)

def setup_database():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS messages
                          (id SERIAL PRIMARY KEY, message_id INTEGER, message_type TEXT)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS quran_progress
                          (id SERIAL PRIMARY KEY, last_page INTEGER)''')
            conn.commit()
    except Exception as e:
        logger.error(f"Error setting up database: {e}")
        conn.rollback()
    finally:
        release_db_connection(conn)

setup_database()

async def fetch_prayer_times():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, params=API_PARAMS) as response:
                data = await response.json()
                return data['data']['timings']
    except Exception as e:
        logger.error(f"Error fetching prayer times: {e}")
        return None

def get_next_quran_pages():
    conn = get_db_connection()
    try:
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
    except Exception as e:
        logger.error(f"Error getting next Quran pages: {e}")
        conn.rollback()
        return None, None
    finally:
        release_db_connection(conn)

    return next_page, next_page + 1

async def send_message(chat_id, text, parse_mode='HTML'):
    try:
        message = await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        return message.message_id
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

async def send_photo(chat_id, photo_url, caption=None):
    try:
        message = await bot.send_photo(chat_id=chat_id, photo=photo_url, caption=caption)
        return message.message_id
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        return None

async def send_media_group(chat_id, media):
    try:
        messages = await bot.send_media_group(chat_id=chat_id, media=media)
        return [message.message_id for message in messages]
    except Exception as e:
        logger.error(f"Error sending media group: {e}")
        return None

async def delete_message(chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

async def send_athkar(athkar_type):
    logger.info(f"Sending {athkar_type} Athkar")
    caption = "#أذكار_الصباح" if athkar_type == "morning" else "#أذكار_المساء"
    image_url = f"{ATHKAR_URL}/{'أذاكر_الصباح' if athkar_type == 'morning' else 'أذكار_المساء'}.png"
    
    message_id = await send_photo(CHAT_ID, image_url, caption)
    
    if message_id:
        conn = get_db_connection()
        try:
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
        except Exception as e:
            logger.error(f"Error managing Athkar messages in database: {e}")
            conn.rollback()
        finally:
            release_db_connection(conn)
    else:
        logger.error("Failed to send Athkar message")

async def send_quran_pages():
    logger.info("Sending Quran pages")
    page1, page2 = get_next_quran_pages()
    if page1 is None or page2 is None:
        logger.error("Failed to get next Quran pages")
        return

    page_1_url = f"{QURAN_PAGES_URL}/photo_{page1}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{page2}.jpg"
    
    media = [
        {"type": "photo", "media": page_1_url},
        {"type": "photo", "media": page_2_url, "caption": "#ورد_اليوم"}
    ]
    
    message_ids = await send_media_group(CHAT_ID, media)
    
    if message_ids:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                for message_id in message_ids:
                    cur.execute('INSERT INTO messages (message_id, message_type) VALUES (%s, %s)', (message_id, "quran"))
                conn.commit()
        except Exception as e:
            logger.error(f"Error managing Quran messages in database: {e}")
            conn.rollback()
        finally:
            release_db_connection(conn)
    else:
        logger.error("Failed to send Quran pages")

async def send_prayer_notification(prayer_name):
    logger.info(f"Sending prayer notification for {prayer_name}")
    prayer_image_url = f"{MISC_URL}/حي_على_الصلاة.png"
    caption = f"صلاة {prayer_name}"
    
    message_id = await send_photo(CHAT_ID, prayer_image_url, caption)
    
    if message_id:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute('INSERT INTO messages (message_id, message_type) VALUES (%s, %s)', (message_id, "prayer"))
                conn.commit()
        except Exception as e:
            logger.error(f"Error managing prayer notification in database: {e}")
            conn.rollback()
        finally:
            release_db_connection(conn)
    else:
        logger.error(f"Failed to send prayer notification for {prayer_name}")

async def schedule_tasks():
    try:
        prayer_times = await fetch_prayer_times()
        if not prayer_times:
            logger.error("Failed to fetch prayer times")
            return

        logger.debug(f"Fetched prayer times: {prayer_times}")
        
        now = datetime.now(CAIRO_TZ)
        schedule_info = []

        for prayer, time_str in prayer_times.items():
            if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                prayer_time = CAIRO_TZ.localize(datetime.strptime(f"{now.date()} {time_str}", "%Y-%m-%d %H:%M"))
                
                if prayer == 'Fajr':
                    athkar_time = prayer_time + timedelta(minutes=35)
                    scheduler.add_job(send_athkar, trigger=DateTrigger(run_date=athkar_time, timezone=CAIRO_TZ), args=["morning"])
                    logger.debug(f"Scheduled morning Athkar for {athkar_time}")
                    schedule_info.append(f"Morning Athkar: {athkar_time.strftime('%H:%M')}")
                
                elif prayer == 'Asr':
                    athkar_time = prayer_time + timedelta(minutes=35)
                    quran_time = prayer_time + timedelta(minutes=45)
                    scheduler.add_job(send_athkar, trigger=DateTrigger(run_date=athkar_time, timezone=CAIRO_TZ), args=["night"])
                    scheduler.add_job(send_quran_pages, trigger=DateTrigger(run_date=quran_time, timezone=CAIRO_TZ))
                    logger.debug(f"Scheduled night Athkar for {athkar_time} and Quran pages for {quran_time}")
                    schedule_info.append(f"Night Athkar: {athkar_time.strftime('%H:%M')}")
                    schedule_info.append(f"Quran Pages: {quran_time.strftime('%H:%M')}")
                
                scheduler.add_job(send_prayer_notification, trigger=DateTrigger(run_date=prayer_time, timezone=CAIRO_TZ), args=[prayer])
                logger.debug(f"Scheduled {prayer} prayer notification for {prayer_time}")
                schedule_info.append(f"{prayer} Prayer: {prayer_time.strftime('%H:%M')}")

        schedule_message = "Today's Schedule:\n" + "\n".join(schedule_info)
        await send_message(CHAT_ID, schedule_message)
        logger.info(f"Tasks scheduled for {now.date()}")
    except Exception as e:
        logger.error(f"Error in schedule_tasks: {e}", exc_info=True)

async def test_telegram_connection():
    try:
        await bot.get_me()
        logger.info("Successfully connected to Telegram API")
    except Exception as e:
        logger.error(f"Failed to connect to Telegram API: {e}")

async def heartbeat():
    while True:
        logger.info("Heartbeat: Bot is still running")
        await asyncio.sleep(60)  # Every minute

async def main():
    await test_telegram_connection()
    asyncio.create_task(heartbeat())

    last_scheduled_date = None
    while True:
        try:
            now = datetime.now(CAIRO_TZ)
            current_date = now.date()

            if last_scheduled_date != current_date:
                logger.info(f"Scheduling tasks for new date: {current_date}")
                await schedule_tasks()
                last_scheduled_date = current_date
            else:
                logger.debug(f"No new scheduling needed. Current date: {current_date}, Last scheduled: {last_scheduled_date}")

            next_check = now + timedelta(minutes=5)
            wait_seconds = (next_check - now).total_seconds()
            logger.debug(f"Waiting for {wait_seconds} seconds until next check")
            await asyncio.sleep(wait_seconds)
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            await asyncio.sleep(60)  # Wait a minute before retrying

if __name__ == "__main__":
    try:
        scheduler.start()
        logger.info("Scheduler started")
        scheduler.add_job(lambda: logger.info("Test job running"), 'interval', minutes=1)
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
    finally:
        connection_pool.closeall()