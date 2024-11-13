import os
import logging
import pytz
from datetime import datetime, timedelta
import asyncio
import aiohttp
from telegram import Bot, InputMediaPhoto
from psycopg2 import pool
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

def get_next_quran_pages():
    logger.info("Entering get_next_quran_pages function")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute('SELECT last_page FROM quran_progress WHERE id = 1')
            result = cur.fetchone()
            logger.debug(f"Database query result: {result}")
            if result and result['last_page'] is not None:
                last_page = result['last_page']
                next_page = last_page + 1
                if next_page > 604:
                    next_page = 220
            else:
                logger.info("No valid entry in database, starting from page 220")
                next_page = 220
            
            next_next_page = next_page + 1 if next_page < 604 else 220
            
            cur.execute('INSERT INTO quran_progress (id, last_page) VALUES (1, %s) ON CONFLICT (id) DO UPDATE SET last_page = %s', (next_next_page, next_next_page))
            conn.commit()
            
            logger.info(f"Next Quran pages: {next_page} and {next_next_page}")
            return next_page, next_next_page
    except Exception as e:
        logger.error(f"Error getting next Quran pages: {e}")
        return 220, 221  # Return default values in case of error
    finally:
        release_db_connection(conn)
        logger.info("Exiting get_next_quran_pages function")

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

DAILY_TASKS = []  # Global list to store all scheduled tasks for the day

async def schedule_tasks():
    try:
        prayer_times = await fetch_prayer_times()
        if not prayer_times:
            logger.error("Failed to fetch prayer times")
            return

        global DAILY_TASKS
        DAILY_TASKS.clear()
        
        now = datetime.now(CAIRO_TZ)
        today = now.date()
        tomorrow = today + timedelta(days=1)

        def get_prayer_time(prayer, for_tomorrow=False):
            target_date = tomorrow if for_tomorrow else today
            return CAIRO_TZ.localize(datetime.strptime(f"{target_date} {prayer_times[prayer]}", "%Y-%m-%d %H:%M"))

        # Calculate all task times for today first
        fajr_time = get_prayer_time('Fajr')
        asr_time = get_prayer_time('Asr')
        
        morning_athkar_time = fajr_time + timedelta(minutes=35)
        evening_athkar_time = asr_time + timedelta(minutes=35)
        quran_time = asr_time + timedelta(minutes=45)
        
        # If morning athkar time has passed, schedule for tomorrow
        if morning_athkar_time <= now:
            morning_athkar_time = get_prayer_time('Fajr', True) + timedelta(minutes=35)
        
        # Add morning athkar task
        DAILY_TASKS.append({
            'type': 'morning_athkar',
            'time': morning_athkar_time,
            'description': '🌅 Morning Athkar'
        })
        
        # Only move evening tasks to tomorrow if both have passed
        if evening_athkar_time <= now and quran_time <= now:
            evening_athkar_time = get_prayer_time('Asr', True) + timedelta(minutes=35)
            quran_time = get_prayer_time('Asr', True) + timedelta(minutes=45)
        
        # Add evening tasks
        next_pages = get_next_quran_pages()
        DAILY_TASKS.extend([
            {
                'type': 'evening_athkar',
                'time': evening_athkar_time,
                'description': '🌙 Evening Athkar'
            },
            {
                'type': 'quran',
                'time': quran_time,
                'description': f'📖 Quran Pages {next_pages[0]}-{next_pages[1]}'
            }
        ])

        # Schedule jobs
        for task in DAILY_TASKS:
            if task['type'] == 'morning_athkar':
                scheduler.add_job(
                    send_athkar,
                    trigger=DateTrigger(run_date=task['time'], timezone=CAIRO_TZ),
                    args=["morning"],
                    id=f"morning_athkar_{task['time'].strftime('%Y%m%d')}",
                    replace_existing=True,
                    misfire_grace_time=300
                )
            elif task['type'] == 'evening_athkar':
                scheduler.add_job(
                    send_athkar,
                    trigger=DateTrigger(run_date=task['time'], timezone=CAIRO_TZ),
                    args=["night"],
                    id=f"night_athkar_{task['time'].strftime('%Y%m%d')}",
                    replace_existing=True,
                    misfire_grace_time=300
                )
            elif task['type'] == 'quran':
                scheduler.add_job(
                    send_quran_pages,
                    trigger=DateTrigger(run_date=task['time'], timezone=CAIRO_TZ),
                    args=[],
                    id=f"quran_pages_{task['time'].strftime('%Y%m%d')}",
                    replace_existing=True,
                    misfire_grace_time=300
                )

        # Log scheduled jobs
        logger.info(f"Total tasks scheduled: {len(DAILY_TASKS)}")
        for task in sorted(DAILY_TASKS, key=lambda x: x['time']):
            logger.info(f"Task: {task['description']} scheduled for {task['time']}")

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

from aiohttp import web

async def handle(request):
    return web.Response(text="Bot is running!")

def format_time_until(target_time, now):
    """Format time difference until target time in a human readable format"""
    diff = target_time - now
    hours = int(diff.total_seconds() // 3600)
    minutes = int((diff.total_seconds() % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

async def send_status_message():
    """Send a detailed status message with schedule and countdown"""
    try:
        prayer_times = await fetch_prayer_times()
        if prayer_times:
            now = datetime.now(CAIRO_TZ)
            today = now.date()

            # Format message header
            status_msg = "🤖 *Bot Status Report*\n"
            status_msg += "─────────────────\n\n"
            
            # Current time
            status_msg += f"📅 Date: {today.strftime('%Y-%m-%d')}\n"
            status_msg += f"🕐 Current time: {now.strftime('%H:%M')}\n\n"
            
            # Prayer times
            status_msg += "🕌 *Prayer Times Today*\n"
            
            # Process prayer times
            for prayer, time in prayer_times.items():
                if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                    prayer_time = CAIRO_TZ.localize(datetime.strptime(f"{today} {time}", "%Y-%m-%d %H:%M"))
                    if prayer_time < now:
                        status_msg += f"✓ {prayer}: {time}\n"
                    else:
                        time_until = format_time_until(prayer_time, now)
                        status_msg += f"⏳ {prayer}: {time} (in {time_until})\n"
            
            # Tasks schedule
            status_msg += "\n📋 *Today's Schedule*\n"
            remaining_tasks = False
            
            sorted_tasks = sorted(DAILY_TASKS, key=lambda x: x['time'])
            today_tasks = [task for task in sorted_tasks if task['time'].date() == today]
            
            if today_tasks:
                for task in today_tasks:
                    time_str = task['time'].strftime('%H:%M')
                    if task['time'] > now:
                        time_until = format_time_until(task['time'], now)
                        status_msg += f"⏳ {task['description']} at {time_str} (in {time_until})\n"
                        remaining_tasks = True
                    else:
                        status_msg += f"✓ {task['description']} at {time_str}\n"
            else:
                status_msg += "No tasks scheduled for today\n"
            
            # Show tomorrow's schedule if no remaining tasks
            if not remaining_tasks:
                status_msg += "\n📅 *Tomorrow's Events*\n"
                # Calculate tomorrow's prayer times and events
                tomorrow = today + timedelta(days=1)
                tomorrow_fajr = CAIRO_TZ.localize(datetime.strptime(f"{tomorrow} {prayer_times['Fajr']}", "%Y-%m-%d %H:%M"))
                tomorrow_asr = CAIRO_TZ.localize(datetime.strptime(f"{tomorrow} {prayer_times['Asr']}", "%Y-%m-%d %H:%M"))
                
                # Morning Athkar
                tomorrow_morning_athkar = tomorrow_fajr + timedelta(minutes=35)
                time_until_morning = format_time_until(tomorrow_morning_athkar, now)
                status_msg += f"🌅 Morning Athkar at {tomorrow_morning_athkar.strftime('%H:%M')} (in {time_until_morning})\n"
                
                # Evening Athkar
                tomorrow_evening_athkar = tomorrow_asr + timedelta(minutes=35)
                time_until_evening = format_time_until(tomorrow_evening_athkar, now)
                status_msg += f"🌙 Evening Athkar at {tomorrow_evening_athkar.strftime('%H:%M')} (in {time_until_evening})\n"
                
                # Quran Pages
                tomorrow_quran_time = tomorrow_asr + timedelta(minutes=45)
                time_until_quran = format_time_until(tomorrow_quran_time, now)
                next_pages = get_next_quran_pages()  # Get tomorrow's pages
                status_msg += f"📖 Quran Pages {next_pages[0]}-{next_pages[1]} at {tomorrow_quran_time.strftime('%H:%M')} (in {time_until_quran})\n"
            
            # Next status update
            status_msg += "\n⏱ *Next Status Update*\n"
            next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            time_to_next = format_time_until(next_hour, now)
            status_msg += f"Next status report in {time_to_next}\n"
            
            await send_message(CHAT_ID, status_msg, parse_mode='Markdown')
            logger.info("Status message sent successfully")
    except Exception as e:
        logger.error(f"Error sending status message: {e}")

async def main():
    # Setup web app
    app = web.Application()
    app.router.add_get("/", handle)
    
    # Start web server
    port = int(os.environ.get('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server started on port {port}")

    # Test Telegram connection and send immediate test message
    await test_telegram_connection()
    await send_status_message()
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started")
    
    # Schedule initial tasks
    await schedule_tasks()
    
    # Start heartbeat
    heartbeat_task = asyncio.create_task(heartbeat())
    
    last_scheduled_date = datetime.now(CAIRO_TZ).date()
    
    while True:
        try:
            now = datetime.now(CAIRO_TZ)
            current_date = now.date()

            if last_scheduled_date != current_date:
                logger.info(f"Scheduling tasks for new date: {current_date}")
                await schedule_tasks()
                last_scheduled_date = current_date
            
            # Send status message every hour
            if now.minute == 0:
                await send_status_message()
            
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Critical error in main execution: {e}", exc_info=True)
    finally:
        scheduler.shutdown()
        connection_pool.closeall()