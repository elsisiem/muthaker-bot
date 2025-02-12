import os
import logging
import pytz
from datetime import datetime, timedelta
import asyncio
import aiohttp
from telegram import Bot, InputMediaPhoto
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
import json

# Constants - all sensitive information from environment variables
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
CAIRO_TZ = pytz.timezone('Africa/Cairo')
API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}

GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname%s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize bot and scheduler
bot = Bot(TOKEN)
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)

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

async def find_previous_athkar(chat_id):
    """Find the previous athkar message by searching recent messages"""
    try:
        messages = await bot.get_updates()
        for update in messages:
            if (update.channel_post and 
                update.channel_post.chat.id == int(chat_id) and
                update.channel_post.caption and
                ("#أذكار_الصباح" in update.channel_post.caption or 
                 "#أذكار_المساء" in update.channel_post.caption)):
                return update.channel_post.message_id
    except Exception as e:
        logger.error(f"Error finding previous athkar: {e}")
    return None

def get_next_quran_pages():
    """Calculate next Quran pages starting from Feb 13, 2025, pages 460, 461"""
    logger.info("Calculating next Quran pages based on date")

    # Define the start date and initial page numbers
    start_date = datetime(2025, 2, 13).date()
    start_page1 = 460
    start_page2 = 461
    total_pages = 604 - 460 + 1  # Total number of pages in the sequence
    loop_start = 460  # The page number to loop back to

    # Get the current date
    today = datetime.now(CAIRO_TZ).date()

    # Calculate the difference in days between the current date and the start date
    days_diff = (today - start_date).days
    logger.debug(f"Days since start date: {days_diff}")

    # Calculate the page numbers based on the day difference
    page1 = (start_page1 + days_diff) % total_pages
    page2 = (start_page2 + days_diff) % total_pages

    # Adjust page numbers to be within the desired range (loopStart to 604)
    page1 = loop_start + page1
    page2 = loop_start + page2

    # Ensure that page numbers loop back to the start
    if page1 > 604:
        page1 = loop_start + (page1 - 605)
    if page2 > 604:
        page2 = loop_start + (page2 - 605)

    # Validation and logging
    logger.info(f"Date: {today}, Start Date: {start_date}")
    logger.info(f"Days passed: {days_diff}")
    logger.info(f"Calculated pages: {page1}, {page2}")

    return int(page1), int(page2)

async def send_athkar(athkar_type):
    """Send athkar with reliable message cleanup"""
    logger.info(f"Sending {athkar_type} Athkar")
    
    caption = "#أذكار_الصباح" if athkar_type == "morning" else "#أذكار_المساء"
    image_url = f"{ATHKAR_URL}/{'أذكار_الصباح' if athkar_type == 'morning' else 'أذكار_المساء'}.jpg"
    
    # Determine the tag of the athkar to be deleted
    delete_tag = "#أذكار_المساء" if athkar_type == "morning" else "#أذكار_الصباح"
    
    try:
        # First, get channel history and find existing athkar messages
        messages = await bot.get_chat_history(chat_id=CHAT_ID, limit=100)
        
        # Find the athkar message with the tag to be deleted
        for message in messages:
            if (hasattr(message, 'caption') and 
                message.caption and 
                delete_tag in message.caption):
                try:
                    await bot.delete_message(chat_id=CHAT_ID, message_id=message.message_id)
                    logger.info(f"Deleted previous athkar message: {message.message_id} with tag {delete_tag}")
                except Exception as e:
                    logger.error(f"Failed to delete message {message.message_id}: {e}")
                break  # Delete only the most recent message with the tag
        
        # Send new athkar message
        new_message = await bot.send_photo(
            chat_id=CHAT_ID,
            photo=image_url,
            caption=caption
        )
        
        if new_message:
            logger.info(f"Successfully sent new {athkar_type} athkar: {new_message.message_id}")
        else:
            logger.error("Failed to send new athkar message")
            
    except Exception as e:
        logger.error(f"Error in send_athkar: {e}", exc_info=True)
        # Retry once on failure
        try:
            await asyncio.sleep(5)
            new_message = await bot.send_photo(
                chat_id=CHAT_ID,
                photo=image_url,
                caption=caption
            )
            logger.info("Successfully sent athkar on retry")
        except Exception as retry_error:
            logger.error(f"Retry also failed: {retry_error}")

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
                    if response.status != 200:
                        logger.error(f"Image not found: {url}")
                        return
                    content = await response.content.read(10)
                    if not content.startswith(b'\xff\xd8'):
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

async def log_status_message():
    """Log status message without sending to channel"""
    try:
        prayer_times = await fetch_prayer_times()
        if prayer_times:
            now = datetime.now(CAIRO_TZ)
            today = now.date()
            
            # Create status message for logs only
            status_msg = f"Bot Status Report - {today.strftime('%Y-%m-%d')} {now.strftime('%H:%M')}\n"
            status_msg += "Prayer times today:\n"
            
            for prayer, time in prayer_times.items():
                if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                    status_msg += f"- {prayer}: {time}\n"
            
            status_msg += "\nScheduled tasks:\n"
            for task in sorted(DAILY_TASKS, key=lambda x: x['time']):
                status_msg += f"- {task['description']} at {task['time'].strftime('%H:%M')}\n"
            
            logger.info(status_msg)
    except Exception as e:
        logger.error(f"Error creating status log: {e}")

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

    # Test Telegram connection and log initial status
    await test_telegram_connection()
    await log_status_message()  # Log status without sending to channel
    
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
                await log_status_message()  # Log daily status
                last_scheduled_date = current_date

            await asyncio.sleep(60)
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