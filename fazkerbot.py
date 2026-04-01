import os
import logging
import pytz
from datetime import datetime, timedelta
import asyncio
import aiohttp
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

# Constants - all sensitive information from environment variables
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
CAIRO_TZ = pytz.timezone('Africa/Cairo')
API_URL = "https://api.aladhan.com/v1/timingsByCity"
COORDINATES_API_URL = "https://api.aladhan.com/v1/timings"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}

# Image URLs for channel posts
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"
FASTING_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "الصيام")

# Weekly fasting reminders: Sunday -> Monday fast, Wednesday -> Thursday fast
FASTING_REMINDER_CONFIG = {
    6: {
        "job_key": "monday",
        "image": "صيام الإثنين.jpg",
        "caption": "#صيام_الإثنين",
    },
    2: {
        "job_key": "thursday",
        "image": "صيام الخميس.jpg",
        "caption": "#صيام_الخميس",
    },
}

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
        api_url_with_date = f"{API_URL}/{date_str}"
        params = {
            'city': 'Cairo', 
            'country': 'Egypt', 
            'method': 3
        }
        
        logger.info(f"Fetching prayer times for {date_str} (city API)")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url_with_date, params=params, timeout=15) as response:
                
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"City API failed with status {response.status}")
                    return None
                    
                data = await response.json()
                
                # Validate response date with relaxed validation
                if not await validate_api_response(data, target_date):
                    logger.warning("City API date validation failed, but continuing...")
                
                timings = data.get('data', {}).get('timings')
                if not timings or not all(prayer in timings for prayer in ['Fajr', 'Asr']):
                    logger.error(f"City API missing required prayer data")
                    return None
                
                logger.info(f"City API success: Fajr {timings.get('Fajr')}, Asr {timings.get('Asr')}")
                return timings
                
    except Exception as e:
        logger.error(f"City API error: {e}")
        return None

async def try_coordinates_api(target_date, date_str):
    """Try the coordinates-based API as backup"""
    try:
        api_url_with_date = f"{COORDINATES_API_URL}/{date_str}"
        params = {
            'latitude': 30.0444,
            'longitude': 31.2357,
            'method': 3
        }
        
        logger.info(f"Fetching prayer times for {date_str} (coordinates API)")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url_with_date, params=params, timeout=15) as response:
                
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"Coordinates API failed with status {response.status}")
                    return None
                    
                data = await response.json()
                
                # Validate response date with relaxed validation
                if not await validate_api_response(data, target_date):
                    logger.warning("Coordinates API date validation failed, but continuing...")
                
                timings = data.get('data', {}).get('timings')
                if not timings or not all(prayer in timings for prayer in ['Fajr', 'Asr']):
                    logger.error(f"Coordinates API missing required prayer data")
                    return None
                
                logger.info(f"Coordinates API success: Fajr {timings.get('Fajr')}, Asr {timings.get('Asr')}")
                return timings
                
    except Exception as e:
        logger.error(f"Coordinates API error: {e}")
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

async def send_athkar(athkar_type):
    """Send athkar without deletion logic"""
    logger.info(f"Sending {athkar_type} Athkar")
    
    caption = None  
    image_url = f"{ATHKAR_URL}/{'أذكار_الصباح' if athkar_type == 'morning' else 'أذكار_المساء'}.jpg"
    
    # Validate URL first
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Athkar image not accessible: {image_url} (status {response.status})")
                    return
                content = await response.content.read(10)
                if not content.startswith(b'\xff\xd8'):
                    logger.error(f"Invalid image format for athkar: {image_url}")
                    return
    except Exception as e:
        logger.error(f"Error validating athkar image URL: {e}")
        return
    
    try:
        new_message = await bot.send_photo(
            chat_id=CHAT_ID,
            photo=image_url,
            caption=caption
        )

        if new_message:
            logger.info(f"Successfully sent {athkar_type} athkar: {new_message.message_id}")
        else:
            logger.error(f"Failed to send {athkar_type} athkar message")
            
    except Exception as e:
        logger.error(f"Error in send_athkar: {e}")
        # Retry once
        try:
            await asyncio.sleep(5)
            new_message = await bot.send_photo(
                chat_id=CHAT_ID,
                photo=image_url,
                caption=caption
            )
            logger.info(f"Successfully sent {athkar_type} athkar on retry")
        except Exception as retry_error:
            logger.error(f"Retry also failed for {athkar_type} athkar: {retry_error}")

async def send_fasting_reminder(reminder_key):
    """Send Sunday/Wednesday fasting reminder image posts."""
    config = None
    for item in FASTING_REMINDER_CONFIG.values():
        if item["job_key"] == reminder_key:
            config = item
            break

    if not config:
        logger.error(f"Unknown fasting reminder key: {reminder_key}")
        return

    image_path = os.path.join(FASTING_IMAGES_DIR, config["image"])
    if not os.path.exists(image_path):
        logger.error(f"Fasting reminder image not found: {image_path}")
        return

    try:
        with open(image_path, "rb") as photo_file:
            message = await bot.send_photo(
                chat_id=CHAT_ID,
                photo=photo_file,
                caption=config["caption"]
            )
        logger.info(f"Fasting reminder sent ({reminder_key}): {message.message_id}")
    except Exception as e:
        logger.error(f"Failed to send fasting reminder ({reminder_key}): {e}")

def parse_prayer_time_for_date(prayer, target_date, prayer_times_data):
    """Parse HH:MM and HH:MM (+TZ) prayer strings into localized Cairo datetimes."""
    try:
        raw_time = prayer_times_data.get(prayer)
        if not raw_time:
            logger.error(f"Missing prayer time for {prayer} on {target_date}")
            return None

        clean_time = raw_time.split(" ")[0]
        if len(clean_time.split(':')) != 2:
            logger.error(f"Invalid time format for {prayer}: {raw_time}")
            return None

        hour, minute = map(int, clean_time.split(':'))
        prayer_time = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
        localized_time = CAIRO_TZ.localize(prayer_time)
        return localized_time
    except Exception as e:
        logger.error(f"Error parsing prayer time for {prayer} on {target_date}: {e}")
        return None

DAILY_TASKS = []  # Global list to store all scheduled tasks for the day

async def schedule_fallback_tasks(now, today, tomorrow):
    """Schedule tasks using fallback prayer times when API is unavailable."""
    global DAILY_TASKS
    DAILY_TASKS.clear()

    def parse_time(day, hhmm):
        hour, minute = map(int, hhmm.split(':'))
        dt = datetime.combine(day, datetime.min.time().replace(hour=hour, minute=minute))
        return CAIRO_TZ.localize(dt)

    fajr_today = parse_time(today, FALLBACK_PRAYER_TIMES['Fajr'])
    asr_today = parse_time(today, FALLBACK_PRAYER_TIMES['Asr'])
    isha_today = parse_time(today, FALLBACK_PRAYER_TIMES['Isha'])
    morning_today = fajr_today + timedelta(minutes=35)
    evening_today = asr_today + timedelta(minutes=30)
    fasting_today = isha_today + timedelta(minutes=30)

    # If a slot already passed, queue the same slot for tomorrow.
    fajr_tomorrow = parse_time(tomorrow, FALLBACK_PRAYER_TIMES['Fajr'])
    asr_tomorrow = parse_time(tomorrow, FALLBACK_PRAYER_TIMES['Asr'])
    isha_tomorrow = parse_time(tomorrow, FALLBACK_PRAYER_TIMES['Isha'])
    morning_tomorrow = fajr_tomorrow + timedelta(minutes=35)
    evening_tomorrow = asr_tomorrow + timedelta(minutes=30)
    fasting_tomorrow = isha_tomorrow + timedelta(minutes=30)

    DAILY_TASKS.append({
        'type': 'morning_athkar',
        'time': morning_today if morning_today > now else morning_tomorrow,
        'description': '🌅 Morning Athkar (fallback)'
    })

    DAILY_TASKS.append({
        'type': 'evening_athkar',
        'time': evening_today if evening_today > now else evening_tomorrow,
        'description': '🌙 Evening Athkar (fallback)'
    })

    for day, candidate_time in ((today, fasting_today), (tomorrow, fasting_tomorrow)):
        config = FASTING_REMINDER_CONFIG.get(day.weekday())
        if config and candidate_time > now:
            DAILY_TASKS.append({
                'type': 'fasting_reminder',
                'time': candidate_time,
                'reminder_key': config['job_key'],
                'description': f"🥗 Fasting Reminder {config['caption']} (fallback)"
            })

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
        elif task['type'] == 'fasting_reminder':
            scheduler.add_job(
                send_fasting_reminder,
                trigger=DateTrigger(run_date=task['time'], timezone=CAIRO_TZ),
                args=[task['reminder_key']],
                id=f"fasting_{task['reminder_key']}_{task['time'].strftime('%Y%m%d')}",
                replace_existing=True,
                misfire_grace_time=300
            )

    logger.warning("Fallback schedule applied due to prayer API failure")
    for task in sorted(DAILY_TASKS, key=lambda x: x['time']):
        logger.info(f"Fallback task: {task['description']} at {task['time']}")

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

        prayer_times_today = await fetch_prayer_times(today)
        if not prayer_times_today:
            logger.error("Failed to fetch today's prayer times even with fallback, using conservative scheduling")
            await schedule_fallback_tasks(now, today, tomorrow)
            return

        prayer_times_tomorrow = await fetch_prayer_times(tomorrow)
        if not prayer_times_tomorrow:
            logger.error("Failed to fetch tomorrow's prayer times, using conservative fallback")
            await schedule_fallback_tasks(now, today, tomorrow)
            return

        logger.info("Today's prayer times fetched successfully")
        for prayer, time in prayer_times_today.items():
            if prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
                logger.info(f"  {prayer}: {time}")

        for day, prayer_times in ((today, prayer_times_today), (tomorrow, prayer_times_tomorrow)):
            fajr_time = parse_prayer_time_for_date('Fajr', day, prayer_times)
            asr_time = parse_prayer_time_for_date('Asr', day, prayer_times)
            isha_time = parse_prayer_time_for_date('Isha', day, prayer_times)

            if not fajr_time or not asr_time or not isha_time:
                logger.error(f"Skipping schedule for {day}: missing Fajr/Asr/Isha")
                continue

            morning_athkar_time = fajr_time + timedelta(minutes=35)
            evening_athkar_time = asr_time + timedelta(minutes=30)

            if morning_athkar_time > now:
                DAILY_TASKS.append({
                    'type': 'morning_athkar',
                    'time': morning_athkar_time,
                    'description': f'🌅 Morning Athkar ({day})'
                })

            if evening_athkar_time > now:
                DAILY_TASKS.append({
                    'type': 'evening_athkar',
                    'time': evening_athkar_time,
                    'description': f'🌙 Evening Athkar ({day})'
                })

            reminder_config = FASTING_REMINDER_CONFIG.get(day.weekday())
            if reminder_config:
                fasting_reminder_time = isha_time + timedelta(minutes=30)
                if fasting_reminder_time > now:
                    DAILY_TASKS.append({
                        'type': 'fasting_reminder',
                        'time': fasting_reminder_time,
                        'reminder_key': reminder_config['job_key'],
                        'description': f"🥗 Fasting Reminder {reminder_config['caption']} ({day})"
                    })

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
            elif task['type'] == 'fasting_reminder':
                scheduler.add_job(
                    send_fasting_reminder,
                    trigger=DateTrigger(run_date=task['time'], timezone=CAIRO_TZ),
                    args=[task['reminder_key']],
                    id=f"fasting_{task['reminder_key']}_{task['time'].strftime('%Y%m%d')}",
                    replace_existing=True,
                    misfire_grace_time=300
                )

        # Log scheduled jobs
        logger.info(f"Total tasks scheduled: {len(DAILY_TASKS)}")
        for task in sorted(DAILY_TASKS, key=lambda x: x['time']):
            logger.info(f"Task: {task['description']} scheduled for {task['time']}")
        
        # Also log the actual scheduler jobs
        scheduled_jobs = scheduler.get_jobs()
        logger.info(f"Scheduler has {len(scheduled_jobs)} jobs:")
        for job in scheduled_jobs:
            logger.info(f"  Job ID: {job.id}, Next run: {job.next_run_time}")

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
        scheduler_jobs = len(scheduler.get_jobs()) if scheduler.running else 0
        logger.info(f"Heartbeat: {now.strftime('%H:%M')} | {scheduled_count} tasks | {scheduler_jobs} scheduler jobs | Running: {scheduler.running}")
        await asyncio.sleep(300)

from aiohttp import web

async def handle(request):
    # Quran posting is paused for now.
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
