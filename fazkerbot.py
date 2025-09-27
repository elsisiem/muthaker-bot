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
COORDINATES_API_URL = "https://api.aladhan.com/v1/timings"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}

# Updated image URLs to use the working GitHub repository
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"

# Fallback prayer times for Cairo (approximate times that can be used when API fails)
FALLBACK_PRAYER_TIMES = {
    'Fajr': '04:30',
    'Dhuhr': '12:00',
    'Asr': '16:30',
    'Maghrib': '19:00',
    'Isha': '20:30'
}

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reduce noise from third-party libraries
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Initialize bot and scheduler
bot = Bot(TOKEN)
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)

async def validate_api_response(data, requested_date):
    """Validate that API returned data for the correct date"""
    try:
        api_date_str = data.get('data', {}).get('date', {}).get('readable')
        gregorian_date = data.get('data', {}).get('date', {}).get('gregorian', {}).get('date')
        
        if not api_date_str or not gregorian_date:
            logger.warning("API response missing date information")
            return False
        
        # Parse the gregorian date (format: DD-MM-YYYY)
        try:
            api_date = datetime.strptime(gregorian_date, '%d-%m-%Y').date()
            if api_date != requested_date:
                logger.warning(f"API date mismatch: requested {requested_date}, got {api_date}")
                # For dates close to today, allow the mismatch (API might be in different timezone)
                date_diff = abs((api_date - requested_date).days)
                if date_diff <= 1:
                    logger.info(f"Accepting API response with 1-day difference: {api_date} vs {requested_date}")
                    return True
                else:
                    logger.error(f"API date too far off: requested {requested_date}, got {api_date}")
                    return False
        except ValueError as e:
            logger.error(f"Could not parse API gregorian date '{gregorian_date}': {e}")
            return False
        
        logger.info(f"API response validated: correct date {requested_date}")
        return True
        
    except Exception as e:
        logger.error(f"Error validating API response: {e}")
        return False

async def fetch_prayer_times_with_fallback(target_date=None):
    """Fetch prayer times with multiple API attempts and fallback"""
    if target_date is None:
        target_date = datetime.now(CAIRO_TZ).date()
    
    date_str = target_date.strftime('%d-%m-%Y')
    logger.info(f"Attempting to fetch prayer times for {date_str}")
    
    # Try city-based API first
    timings = await try_city_api(target_date, date_str)
    if timings:
        return timings
    
    # Try coordinates API as backup
    timings = await try_coordinates_api(target_date, date_str)
    if timings:
        return timings
    
    # If both APIs fail, use fallback times with warning
    logger.warning(f"All APIs failed for {date_str}, using fallback prayer times")
    return FALLBACK_PRAYER_TIMES

async def try_city_api(target_date, date_str):
    """Try the city-based API"""
    try:
        # Build URL with date as path parameter
        api_url_with_date = f"{API_URL}/{date_str}"
        params = {
            'city': 'Cairo', 
            'country': 'Egypt', 
            'method': 3  # Muslim World League
        }
        
        logger.info(f"🔄 Trying city API for {date_str}")
        logger.info(f"🌐 URL: {api_url_with_date}")
        logger.info(f"🔧 Params: {params}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url_with_date, params=params, timeout=15) as response:
                logger.info(f"🌐 City API response status: {response.status}")
                
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"City API failed with status {response.status}, response: {response_text[:200]}")
                    return None
                    
                data = await response.json()
                logger.info(f"📅 City API response received successfully")
                
                # Log more details about the response
                if 'data' in data and 'date' in data['data']:
                    date_info = data['data']['date']
                    logger.info(f"📅 API returned date: {date_info.get('readable', 'N/A')}")
                    logger.info(f"📅 API gregorian date: {date_info.get('gregorian', {}).get('date', 'N/A')}")
                
                # Validate response date with relaxed validation
                if not await validate_api_response(data, target_date):
                    logger.warning("City API date validation failed, but continuing...")
                
                timings = data.get('data', {}).get('timings')
                if not timings:
                    logger.error("City API missing timings data")
                    return None
                    
                if not all(prayer in timings for prayer in ['Fajr', 'Asr']):
                    logger.error(f"City API missing required prayers. Available: {list(timings.keys())}")
                    return None
                
                logger.info(f"✅ City API success for {date_str}")
                logger.info(f"🕌 Fajr: {timings.get('Fajr')}, Asr: {timings.get('Asr')}")
                return timings
                
    except Exception as e:
        logger.error(f"❌ City API error for {date_str}: {e}")
        return None

async def try_coordinates_api(target_date, date_str):
    """Try the coordinates-based API as backup"""
    try:
        # Build URL with date as path parameter
        api_url_with_date = f"{COORDINATES_API_URL}/{date_str}"
        params = {
            'latitude': 30.0444,  # Cairo coordinates
            'longitude': 31.2357,
            'method': 3  # Muslim World League
        }
        
        logger.info(f"🔄 Trying coordinates API for {date_str}")
        logger.info(f"🌐 URL: {api_url_with_date}")
        logger.info(f"🔧 Params: {params}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url_with_date, params=params, timeout=15) as response:
                logger.info(f"🌐 Coordinates API response status: {response.status}")
                
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"Coordinates API failed with status {response.status}, response: {response_text[:200]}")
                    return None
                    
                data = await response.json()
                logger.info(f"📅 Coordinates API response received successfully")
                
                # Validate response date with relaxed validation
                if not await validate_api_response(data, target_date):
                    logger.warning("Coordinates API date validation failed, but continuing...")
                
                timings = data.get('data', {}).get('timings')
                if not timings:
                    logger.error("Coordinates API missing timings data")
                    return None
                    
                if not all(prayer in timings for prayer in ['Fajr', 'Asr']):
                    logger.error(f"Coordinates API missing required prayers. Available: {list(timings.keys())}")
                    return None
                
                logger.info(f"✅ Coordinates API success for {date_str}")
                logger.info(f"🕌 Fajr: {timings.get('Fajr')}, Asr: {timings.get('Asr')}")
                return timings
                
    except Exception as e:
        logger.error(f"❌ Coordinates API error for {date_str}: {e}")
        return None

async def fetch_prayer_times(target_date=None):
    """Main function to fetch prayer times - updated to use new fallback system"""
    return await fetch_prayer_times_with_fallback(target_date)

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
    """Calculate next Quran pages based on anchor date"""
    # Recalibrated anchor to align with May 26th, 2025 target (pages 2-3)
    anchor_date = datetime(2025, 5, 26).date()  # New anchor date: May 26th, 2025
    anchor_page1 = 2  # Anchor page
    anchor_page2 = 3  # Anchor page
    total_pages = 604  # Maximum page number

    today = datetime.now(CAIRO_TZ).date()
    days_diff = (today - anchor_date).days
    
    logger.info(f"📅 Date: {today}")
    logger.info(f"📅 Anchor date: {anchor_date}")
    logger.info(f"📅 Days difference: {days_diff}")

    # Increment pages by 2 per day
    page1 = anchor_page1 + days_diff * 2
    page2 = anchor_page2 + days_diff * 2

    # Wrapping logic: if page exceeds total_pages, wrap around to 1.
    def wrap(page):
        if page <= 0:
            # Handle negative pages by wrapping from the end
            while page <= 0:
                page += total_pages
        elif page > total_pages:
            # Handle pages beyond total by wrapping to beginning
            page = ((page - 1) % total_pages) + 1
        return page

    page1 = wrap(page1)
    page2 = wrap(page2)

    logger.info(f"📖 Quran pages for {today}: {page1}-{page2}")
    return int(page1), int(page2)

def get_next_quran_pages_for_date(target_date):
    """Calculate Quran pages for a specific date"""
    anchor_date = datetime(2025, 5, 26).date()
    anchor_page1 = 2
    anchor_page2 = 3
    total_pages = 604

    days_diff = (target_date - anchor_date).days
    
    logger.info(f"📅 Target date: {target_date}")
    logger.info(f"📅 Days difference from anchor: {days_diff}")

    page1 = anchor_page1 + days_diff * 2
    page2 = anchor_page2 + days_diff * 2

    def wrap(page):
        if page <= 0:
            while page <= 0:
                page += total_pages
        elif page > total_pages:
            page = ((page - 1) % total_pages) + 1
        return page

    page1 = wrap(page1)
    page2 = wrap(page2)

    logger.info(f"📖 Quran pages for {target_date}: {page1}-{page2}")
    return int(page1), int(page2)

async def send_athkar(athkar_type):
    """Send athkar without deletion logic"""
    logger.info(f"🌅 Sending {athkar_type} Athkar")
    
    # No caption for athkar messages
    caption = None  
    image_url = f"{ATHKAR_URL}/{'أذكار_الصباح' if athkar_type == 'morning' else 'أذكار_المساء'}.jpg"
    
    # Validate URL first
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"❌ Athkar image not accessible: {image_url} (status {response.status})")
                    return
                content = await response.content.read(10)
                if not content.startswith(b'\xff\xd8'):
                    logger.error(f"❌ Invalid image format for athkar: {image_url}")
                    return
    except Exception as e:
        logger.error(f"❌ Error validating athkar image URL {image_url}: {e}")
        return
    
    try:
        # Send the athkar image
        new_message = await bot.send_photo(
            chat_id=CHAT_ID,
            photo=image_url,
            caption=caption
        )

        if new_message:
            logger.info(f"✅ Successfully sent {athkar_type} athkar: {new_message.message_id}")
        else:
            logger.error(f"❌ Failed to send {athkar_type} athkar message")
            
    except Exception as e:
        logger.error(f"❌ Error in send_athkar: {e}")
        # Retry once after a short delay
        try:
            await asyncio.sleep(5)
            new_message = await bot.send_photo(
                chat_id=CHAT_ID,
                photo=image_url,
                caption=caption
            )
            logger.info(f"✅ Successfully sent {athkar_type} athkar on retry: {new_message.message_id}")
        except Exception as retry_error:
            logger.error(f"❌ Retry also failed for {athkar_type} athkar: {retry_error}")

async def send_quran_pages(target_date=None):
    """Send Quran pages for a specific date"""
    logger.info("📖 Entering send_quran_pages function")
    
    # Use the target date if provided, otherwise use today's date
    if target_date is None:
        target_date = datetime.now(CAIRO_TZ).date()
    else:
        # If target_date is a datetime object, extract the date
        if isinstance(target_date, datetime):
            target_date = target_date.date()
    
    page1, page2 = get_next_quran_pages_for_date(target_date)
    page_1_url = f"{QURAN_PAGES_URL}/photo_{page1}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{page2}.jpg"
    
    logger.info(f"📖 Sending Quran pages {page1}-{page2} for {target_date}")
    logger.info(f"📖 Page URLs: {page_1_url}, {page_2_url}")
    
    # Validate URLs first
    async with aiohttp.ClientSession() as session:
        for i, url in enumerate([page_1_url, page_2_url], 1):
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status != 200:
                        logger.error(f"❌ Quran page {i} not found: {url} (status {response.status})")
                        return
                    content = await response.content.read(10)
                    if not content.startswith(b'\xff\xd8'):
                        logger.error(f"❌ Invalid image format for page {i}: {url}")
                        return
                    logger.info(f"✅ Page {i} validated: {url}")
            except Exception as e:
                logger.error(f"❌ Error validating Quran page {i} URL {url}: {e}")
                return
    
    media = [
        {"type": "photo", "media": page_1_url},
        {"type": "photo", "media": page_2_url, "caption": "ورد اليوم"}
    ]
    
    try:
        logger.info("📖 Attempting to send Quran media group")
        message_ids = await send_media_group(CHAT_ID, media)
        
        if message_ids:
            logger.info(f"✅ Successfully sent Quran pages {page1}-{page2}. Message IDs: {message_ids}")
        else:
            logger.error(f"❌ Failed to send Quran pages {page1}-{page2}: No message IDs returned")
    except Exception as e:
        logger.error(f"❌ Error sending Quran pages {page1}-{page2}: {e}")
    finally:
        logger.info("📖 Exiting send_quran_pages function")

DAILY_TASKS = []  # Global list to store all scheduled tasks for the day

async def schedule_tasks():
    try:
        logger.info("Starting task scheduling process...")
        
        global DAILY_TASKS
        DAILY_TASKS.clear()
        
        now = datetime.now(CAIRO_TZ)
        today = now.date()
        tomorrow = today + timedelta(days=1)
        
        logger.info(f"Current time: {now}")
        logger.info(f"Today: {today}")
        logger.info(f"Tomorrow: {tomorrow}")

        # Fetch prayer times for today with new fallback system
        prayer_times_today = await fetch_prayer_times(today)
        if not prayer_times_today:
            logger.error("Failed to fetch today's prayer times even with fallback, using conservative scheduling")
            # Use conservative fallback scheduling
            await schedule_fallback_tasks(now, today, tomorrow)
            return

        logger.info("Today's prayer times fetched successfully")
        
        # Log prayer times for verification
        for prayer, time in prayer_times_today.items():
            if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                logger.info(f"  {prayer}: {time}")

        def get_prayer_time(prayer, target_date, prayer_times_data):
            try:
                time_str = prayer_times_data[prayer]
                if not time_str or len(time_str.split(':')) != 2:
                    logger.error(f"Invalid time format for {prayer}: {time_str}")
                    return None
                
                hour, minute = map(int, time_str.split(':'))
                prayer_time = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
                localized_time = CAIRO_TZ.localize(prayer_time)
                logger.info(f"Parsed {prayer} time for {target_date}: {localized_time}")
                return localized_time
            except Exception as e:
                logger.error(f"Error parsing prayer time for {prayer} on {target_date}: {e}")
                return None

        # Calculate today's prayer times
        fajr_time_today = get_prayer_time('Fajr', today, prayer_times_today)
        asr_time_today = get_prayer_time('Asr', today, prayer_times_today)
        
        if not fajr_time_today or not asr_time_today:
            logger.error("Critical prayer times are invalid for today, cannot schedule tasks")
            return

        logger.info(f"Using today's prayer times - Fajr: {fajr_time_today}, Asr: {asr_time_today}")
        
        # Calculate today's task times
        morning_athkar_time = fajr_time_today + timedelta(minutes=35)
        evening_athkar_time = asr_time_today + timedelta(minutes=30)
        quran_time = evening_athkar_time + timedelta(minutes=10)

        logger.info(f"Initial calculated times for today:")
        logger.info(f"Morning Athkar: {morning_athkar_time}")
        logger.info(f"Evening Athkar: {evening_athkar_time}")
        logger.info(f"Quran time: {quran_time}")

        # Check if we need tomorrow's prayer times
        need_tomorrow_times = False
        tasks_for_tomorrow = []

        # Handle morning athkar scheduling
        if morning_athkar_time <= now:
            need_tomorrow_times = True
            tasks_for_tomorrow.append('morning_athkar')
            logger.info("Morning athkar time has passed, will schedule for tomorrow")
        else:
            DAILY_TASKS.append({
                'type': 'morning_athkar',
                'time': morning_athkar_time,
                'description': '🌅 Morning Athkar'
            })

        # Handle evening tasks scheduling
        if evening_athkar_time <= now:
            need_tomorrow_times = True
            tasks_for_tomorrow.extend(['evening_athkar', 'quran'])
            logger.info("Evening athkar time has passed, will schedule evening tasks for tomorrow")
        elif quran_time <= now:
            need_tomorrow_times = True
            tasks_for_tomorrow.append('quran')
            logger.info("Quran time has passed, will schedule for tomorrow")
            # Add today's evening athkar
            DAILY_TASKS.append({
                'type': 'evening_athkar',
                'time': evening_athkar_time,
                'description': '🌙 Evening Athkar'
            })
        else:
            # Add both evening tasks for today
            today_pages = get_next_quran_pages_for_date(today)
            DAILY_TASKS.extend([
                {
                    'type': 'evening_athkar',
                    'time': evening_athkar_time,
                    'description': '🌙 Evening Athkar'
                },
                {
                    'type': 'quran',
                    'time': quran_time,
                    'description': f'📖 Quran Pages {today_pages[0]}-{today_pages[1]}'
                }
            ])

        # Fetch tomorrow's prayer times if needed
        if need_tomorrow_times:
            logger.info("Fetching tomorrow's prayer times...")
            prayer_times_tomorrow = await fetch_prayer_times(tomorrow)
            if not prayer_times_tomorrow:
                logger.error("Failed to fetch tomorrow's prayer times")
                return

            fajr_time_tomorrow = get_prayer_time('Fajr', tomorrow, prayer_times_tomorrow)
            asr_time_tomorrow = get_prayer_time('Asr', tomorrow, prayer_times_tomorrow)
            
            if not fajr_time_tomorrow or not asr_time_tomorrow:
                logger.error("Critical prayer times are invalid for tomorrow")
                return

            logger.info(f"Tomorrow's prayer times - Fajr: {fajr_time_tomorrow}, Asr: {asr_time_tomorrow}")

            # Schedule tomorrow's tasks
            if 'morning_athkar' in tasks_for_tomorrow:
                morning_athkar_tomorrow = fajr_time_tomorrow + timedelta(minutes=35)
                DAILY_TASKS.append({
                    'type': 'morning_athkar',
                    'time': morning_athkar_tomorrow,
                    'description': '🌅 Morning Athkar'
                })
                logger.info(f"Scheduled morning athkar for tomorrow: {morning_athkar_tomorrow}")

            if 'evening_athkar' in tasks_for_tomorrow or 'quran' in tasks_for_tomorrow:
                evening_athkar_tomorrow = asr_time_tomorrow + timedelta(minutes=30)
                quran_time_tomorrow = evening_athkar_tomorrow + timedelta(minutes=10)
                
                if 'evening_athkar' in tasks_for_tomorrow:
                    DAILY_TASKS.append({
                        'type': 'evening_athkar',
                        'time': evening_athkar_tomorrow,
                        'description': '🌙 Evening Athkar'
                    })
                    logger.info(f"Scheduled evening athkar for tomorrow: {evening_athkar_tomorrow}")

                if 'quran' in tasks_for_tomorrow:
                    # Calculate tomorrow's Quran pages using tomorrow's date
                    tomorrow_pages = get_next_quran_pages_for_date(tomorrow)
                    DAILY_TASKS.append({
                        'type': 'quran',
                        'time': quran_time_tomorrow,
                        'description': f'📖 Quran Pages {tomorrow_pages[0]}-{tomorrow_pages[1]}'
                    })
                    logger.info(f"📖 Scheduled Quran pages {tomorrow_pages[0]}-{tomorrow_pages[1]} for {tomorrow}")

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
                # Pass the exact date to ensure correct pages are sent
                task_date = task['time'].date()
                scheduler.add_job(
                    send_quran_pages,
                    trigger=DateTrigger(run_date=task['time'], timezone=CAIRO_TZ),
                    args=[task_date],  # Pass the specific date
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
        now = datetime.now(CAIRO_TZ)
        scheduled_count = len(DAILY_TASKS) if DAILY_TASKS else 0
        logger.info(f"💓 Bot running | {now.strftime('%H:%M')} | {scheduled_count} tasks scheduled")
        await asyncio.sleep(300)  # Every 5 minutes instead of every minute

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
        today = datetime.now(CAIRO_TZ).date()
        prayer_times = await fetch_prayer_times(today)
        if prayer_times:
            now = datetime.now(CAIRO_TZ)
            
            logger.info("=" * 50)
            logger.info(f"📊 BOT STATUS REPORT - {today} {now.strftime('%H:%M')}")
            logger.info("=" * 50)
            
            logger.info("🕌 Prayer times:")
            for prayer, time in prayer_times.items():
                if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                    logger.info(f"   {prayer}: {time}")
            
            if DAILY_TASKS:
                logger.info("📅 Scheduled tasks:")
                for task in sorted(DAILY_TASKS, key=lambda x: x['time']):
                    task_date = task['time'].strftime('%m/%d')
                    task_time = task['time'].strftime('%H:%M')
                    logger.info(f"   {task['description']} - {task_date} at {task_time}")
            else:
                logger.info("📅 No tasks scheduled")
            
            # Show today's Quran pages
            today_pages = get_next_quran_pages()
            logger.info(f"📖 Today's Quran pages: {today_pages[0]}-{today_pages[1]}")
            
            logger.info("=" * 50)
    except Exception as e:
        logger.error(f"Error creating status log: {e}")

async def test_prayer_times():
    """Test function to verify prayer times API and parsing"""
    logger.info("Testing prayer times API with new fallback system...")
    
    today = datetime.now(CAIRO_TZ).date()
    tomorrow = today + timedelta(days=1)
    
    # Test today's prayer times
    prayer_times_today = await fetch_prayer_times(today)
    if not prayer_times_today:
        logger.error("Failed to fetch today's prayer times in test")
        return False
    else:
        logger.info(f"Today's prayer times: Fajr={prayer_times_today.get('Fajr')}, Asr={prayer_times_today.get('Asr')}")
    
    # Test tomorrow's prayer times
    prayer_times_tomorrow = await fetch_prayer_times(tomorrow)
    if not prayer_times_tomorrow:
        logger.error("Failed to fetch tomorrow's prayer times in test")
        return False
    else:
        logger.info(f"Tomorrow's prayer times: Fajr={prayer_times_tomorrow.get('Fajr')}, Asr={prayer_times_tomorrow.get('Asr')}")
    
    return True

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
    
    # Test Telegram connection and prayer times
    await test_telegram_connection()
    prayer_test_result = await test_prayer_times()
    if not prayer_test_result:
        logger.warning("Prayer times test failed - scheduling may not work correctly")
    
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
        try:
            if scheduler.running:
                scheduler.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down scheduler: {e}")
