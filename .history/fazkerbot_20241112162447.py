import os
import logging
import pytz
from datetime import datetime, timedelta
import asyncio
import aiohttp
from aiohttp import web
from telegram import Bot, InputMediaPhoto
from psycopg2 import pool, OperationalError
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

# Add Heroku-specific constants
PORT = int(os.environ.get('PORT', 8080))
DYNO_URL = os.environ.get('HEROKU_APP_URL')  # Add this to your Heroku config vars

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize bot and scheduler
bot = Bot(TOKEN)
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)

# Modify database connection pool setup
class DatabasePool:
    def __init__(self):
        self.pool = None
        self.create_pool()

    def create_pool(self):
        try:
            if self.pool is not None:
                self.pool.closeall()
            self.pool = pool.SimpleConnectionPool(
                1, 5,  # Reduce max connections for Heroku basic dyno
                DATABASE_URL,
                sslmode='require',
                connect_timeout=10
            )
            logger.info("Database pool created successfully")
        except Exception as e:
            logger.error(f"Error creating database pool: {e}")

    async def health_check(self):
        """Periodic database health check"""
        while True:
            try:
                conn = self.pool.getconn()
                with conn.cursor() as cur:
                    cur.execute('SELECT 1')
                self.pool.putconn(conn)
                logger.debug("Database health check passed")
            except (OperationalError, Exception) as e:
                logger.error(f"Database health check failed: {e}")
                self.create_pool()
            await asyncio.sleep(300)  # Check every 5 minutes

db_pool = DatabasePool()

# Add web server routes for Heroku
async def handle_keep_alive(request):
    return web.Response(text="Bot is alive")

app = web.Application()
app.router.add_get("/", handle_keep_alive)

# Modify database functions
def get_db_connection():
    try:
        return db_pool.pool.getconn()
    except Exception as e:
        logger.error(f"Error getting database connection: {e}")
        db_pool.create_pool()
        return db_pool.pool.getconn()

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
        logger.info(f"Sending media group to chat {chat_id}")
        media_group = [InputMediaPhoto(media=item["media"], caption=item.get("caption")) for item in media]
        messages = await bot.send_media_group(chat_id=chat_id, media=media_group)
        logger.info(f"Successfully sent media group. Number of messages: {len(messages)}")
        return [message.message_id for message in messages]
    except Exception as e:
        logger.error(f"Error in send_media_group: {e}")
        return None

async def delete_message(chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

async def send_athkar(athkar_type):
    logger.info(f"Sending {athkar_type} Athkar")
    caption = "#أذكار_الصباح" if athkar_type == "morning" else "#أذكار_المساء"
    image_url = f"{ATHKAR_URL}/{'أذكار_الصباح' if athkar_type == 'morning' else 'أذكار_المساء'}.jpg"
    
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

# Modify get_next_quran_pages with better error handling
def get_next_quran_pages():
    retries = 3
    while retries > 0:
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=DictCursor) as cur:
                # First try to get the last page
                cur.execute('SELECT last_page FROM quran_progress WHERE id = 1')
                result = cur.fetchone()
                
                if result and result['last_page'] is not None:
                    last_page = result['last_page']
                    next_page = last_page + 1
                    if next_page > 604:
                        next_page = 220
                else:
                    # Initialize the table if empty
                    next_page = 220
                    cur.execute('INSERT INTO quran_progress (id, last_page) VALUES (1, 220) ON CONFLICT DO NOTHING')
                
                next_next_page = next_page + 1 if next_page < 604 else 220
                
                # Update with retry logic
                cur.execute(
                    'UPDATE quran_progress SET last_page = %s WHERE id = 1',
                    (next_next_page,)
                )
                conn.commit()
                return next_page, next_next_page
                
        except Exception as e:
            logger.error(f"Database error (attempt {4-retries}/3): {e}")
            if conn:
                conn.rollback()
            retries -= 1
            if retries > 0:
                time.sleep(1)
        finally:
            if conn:
                db_pool.pool.putconn(conn)
    
    logger.error("All database retries failed, using default values")
    return 220, 221

async def send_quran_pages():
    logger.info("Entering send_quran_pages function")
    page1, page2 = get_next_quran_pages()
    page_1_url = f"{QURAN_PAGES_URL}/photo_{page1}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{page2}.jpg"
    
    logger.info(f"Quran page URLs: {page_1_url}, {page_2_url}")
    
    # Verify that the images exist
    async with aiohttp.ClientSession() as session:
        for url in [page_1_url, page_2_url]:
            try:
                async with session.get(url) as response:
                    logger.info(f"GET request for {url}: status {response.status}")
                    if response.status != 200:
                        logger.error(f"Image not found: {url}")
                        return
                    # Read a small part of the response to ensure it's an image
                    content = await response.content.read(10)
                    if not content.startswith(b'\xff\xd8'):  # JPEG file signature
                        logger.error(f"URL does not point to a valid JPEG image: {url}")
                        return
            except Exception as e:
                logger.error(f"Error checking image URL {url}: {e}")
                return
    
    media = [
        {"type": "photo", "media": page_1_url},
        {"type": "photo", "media": page_2_url, "caption": "#ورد_اليوم"}
    ]
    
    try:
        logger.info("Attempting to send media group")
        message_ids = await send_media_group(CHAT_ID, media)
        
        if message_ids:
            logger.info(f"Successfully sent media group. Message IDs: {message_ids}")
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    for message_id in message_ids:
                        cur.execute('INSERT INTO messages (message_id, message_type) VALUES (%s, %s)', (message_id, "quran"))
                    conn.commit()
                logger.info("Successfully updated database with new message IDs")
            except Exception as e:
                logger.error(f"Error managing Quran messages in database: {e}")
                conn.rollback()
            finally:
                release_db_connection(conn)
        else:
            logger.error("Failed to send Quran pages: No message IDs returned")
    except Exception as e:
        logger.error(f"Error sending Quran pages: {e}")
    finally:
        logger.info("Exiting send_quran_pages function")

async def send_status_update(prayer_times):
    """Send a status message about current prayer times and next scheduled tasks."""
    now = datetime.now(CAIRO_TZ)
    status_msg = "🕌 Bot Status Update:\n"
    status_msg += f"Current time: {now.strftime('%H:%M')}\n\n"
    
    for prayer, time_str in prayer_times.items():
        if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
            prayer_time = CAIRO_TZ.localize(datetime.strptime(f"{now.date()} {time_str}", "%Y-%m-%d %H:%M"))
            status_msg += f"{prayer}: {time_str}"
            if prayer_time > now:
                status_msg += " (⏳ Coming up)"
            elif (now - prayer_time).total_seconds() < 3600:  # Within last hour
                status_msg += " (✅ Recent)"
            else:
                status_msg += " (⌛️ Passed)"
            status_msg += "\n"
    
    await send_message(CHAT_ID, status_msg)

async def schedule_tasks():
    try:
        prayer_times = await fetch_prayer_times()
        if not prayer_times:
            logger.error("Failed to fetch prayer times")
            return

        now = datetime.now(CAIRO_TZ)
        logger.info(f"Scheduling tasks for {now.date()}")

        # Clear existing jobs
        scheduler.remove_all_jobs()

        # Schedule status updates every minute
        scheduler.add_job(
            send_status_update,
            'interval',
            minutes=1,
            args=[prayer_times],
            next_run_time=datetime.now(CAIRO_TZ)
        )

        for prayer, time_str in prayer_times.items():
            if prayer in ['Fajr', 'Asr']:
                try:
                    prayer_time = CAIRO_TZ.localize(datetime.strptime(f"{now.date()} {time_str}", "%Y-%m-%d %H:%M"))
                    
                    # Adjust for next day if the prayer time has passed
                    if prayer_time < now:
                        prayer_time = prayer_time + timedelta(days=1)

                    if prayer == 'Fajr':
                        athkar_time = prayer_time + timedelta(minutes=35)
                        scheduler.add_job(
                            send_athkar,
                            trigger=DateTrigger(run_date=athkar_time, timezone=CAIRO_TZ),
                            args=["morning"],
                            id=f"morning_athkar_{athkar_time.strftime('%Y%m%d')}",
                            misfire_grace_time=300
                        )
                        logger.info(f"Scheduled morning Athkar for {athkar_time}")
                    
                    elif prayer == 'Asr':
                        athkar_time = prayer_time + timedelta(minutes=35)
                        quran_time = prayer_time + timedelta(minutes=45)
                        
                        scheduler.add_job(
                            send_athkar,
                            trigger=DateTrigger(run_date=athkar_time, timezone=CAIRO_TZ),
                            args=["night"],
                            id=f"night_athkar_{athkar_time.strftime('%Y%m%d')}",
                            misfire_grace_time=300
                        )
                        
                        scheduler.add_job(
                            send_quran_pages,
                            trigger=DateTrigger(run_date=quran_time, timezone=CAIRO_TZ),
                            id=f"quran_{quran_time.strftime('%Y%m%d')}",
                            misfire_grace_time=300
                        )
                        logger.info(f"Scheduled night Athkar for {athkar_time} and Quran for {quran_time}")
                
                except Exception as e:
                    logger.error(f"Error scheduling {prayer}: {e}")

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

# Modify main function to include web server and keep-alive
async def main():
    try:
        # Start web server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        logger.info(f"Web server started on port {PORT}")

        # Start database health check
        asyncio.create_task(db_pool.health_check())

        # Keep Heroku dyno alive
        async def keep_alive():
            if DYNO_URL:
                while True:
                    try:
                        async with aiohttp.ClientSession() as session:
                            await session.get(DYNO_URL)
                            logger.debug("Keep-alive ping sent")
                    except Exception as e:
                        logger.error(f"Keep-alive error: {e}")
                    await asyncio.sleep(1200)  # Ping every 20 minutes

        asyncio.create_task(keep_alive())

        # Start bot operations
        await test_telegram_connection()
        await schedule_tasks()

        # Reschedule every hour with error handling
        while True:
            try:
                await asyncio.sleep(3600)
                await schedule_tasks()
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    except Exception as e:
        logger.critical(f"Critical error in main: {e}", exc_info=True)
        # Attempt to restart the main function
        await asyncio.sleep(60)
        await main()

# Modify startup code
if __name__ == "__main__":
    try:
        scheduler.start()
        logger.info("Scheduler started")
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
    finally:
        scheduler.shutdown()
        if db_pool.pool:
            db_pool.pool.closeall()