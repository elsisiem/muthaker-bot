import os
import sys
import asyncio
import logging
import json
import random
import signal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque

import pytz
import telegram
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Constants
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"
MISC_URL = f"{GITHUB_RAW_URL}/%D9%85%D9%86%D9%88%D8%B9"
COUNTER_FILE = "quran_page_counter.json"
MESSAGE_IDS_FILE = "message_ids.json"
CAIRO_TZ = pytz.timezone('Africa/Cairo')
API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {
    'city': 'Cairo',
    'country': 'Egypt',
    'method': 3  # Muslim World League
}

# Initialize bot and global variables
bot = telegram.Bot(token=TOKEN)
VERSE_MESSAGES = deque(maxlen=8)
quran_page_number = 206  # Starting from page 206
message_ids = {"morning": [], "night": []}

# Verses to send randomly
VERSES = [
    "قولوا : سبحانَ اللهِ ، و الحمدُ للهِ ، ولَا إلهَ إلَّا اللهِ ، واللهُ أكبرُ ، فإِنَّهنَّ يأتينَ يومَ القيامةِ مُقَدِّمَاتٍ وَمُعَقِّبَاتٍ وَمُجَنِّبَاتٍ ، وَهُنَّ الْبَاقِيَاتُ الصَّالِحَاتُ.",
    "يا عبدالله بن قيس، ألا أدلك على كنز من كنوز الجنة؟ لا حول ولا قوة إلا بالله",
    "من استغفر للمؤمنين والمؤمنات، كتب الله له بكل مؤمن ومؤمنة حسنة",
    "من دخل السوق، فقال: لا إله إلا الله، وحده لا شريك له، له الملك وله الحمد، يحيي ويميت، وهو حي لا يموت، بيده الخير، وهو على كل شيء قدير، كتب الله له ألف ألف حسنة، ومحا عنه ألف ألف سيئة، ورفع له ألف ألف درجة",
    "﴿ فَمَنْ يَعْمَلْ مِثْقَالَ ذَرَّةٍ خَيْرًا يَرَهُ * وَمَنْ يَعْمَلْ مِثْقَالَ ذَرَّةٍ شَرًّا يَرَهُ ﴾",
    "﴿ فَمَنْ ثَقُلَتْ مَوَازِينُهُ فَأُولَئِكَ هُمُ الْمُفْلِحُونَ * وَمَنْ خَفَّتْ مَوَازِينُهُ فَأُولَئِكَ الَّذِينَ خَسِرُوا أَنْفُسَهُمْ فِي جَهَنَّمَ خَالِدُونَ ﴾",
    "﴿ فَأَمَّا مَنْ ثَقُلَتْ مَوَازِينُهُ * فَهُوَ فِي عِيشَةٍ رَاضِيَةٍ * وَأَمَّا مَنْ خَفَّتْ مَوَازِينُهُ * فَأُمُّهُ هَاوِيَةٌ * وَمَا أَدْرَاكَ مَا هِيَهْ * نَارٌ حَامِيَةٌ ﴾",
    "«من قال في يوم مائتي مرة [مائة إذا أصبح، ومائة إذا أمسى]: لا إله إلا الله وحده لا شريك له، له الملك وله الحمد، وهو على كل شيء قدير، لم يسبقه أحد كان قبله، ولا يدركه أحد بعده، إلا من عمل أفضل من عمله"
]

def load_json_file(file_path, default_value):
    """Load JSON file or create it with default value if not exists."""
    if not os.path.exists(file_path):
        logging.info(f"File {file_path} not found. Creating with default value.")
        save_json_file(file_path, default_value)
        return default_value
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        logging.info(f"Successfully loaded data from {file_path}")
        return data
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {file_path}: {str(e)}")
        return default_value

def save_json_file(file_path, data):
    """Save data to JSON file."""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f)
        logging.info(f"Successfully saved data to {file_path}")
    except Exception as e:
        logging.error(f"Failed to save data to {file_path}: {str(e)}")

def load_quran_page_number():
    """Load the current Quran page number."""
    data = load_json_file(COUNTER_FILE, {'page_number': 206})
    return data.get('page_number', 206)

def save_quran_page_number(page_number):
    """Save the current Quran page number."""
    save_json_file(COUNTER_FILE, {'page_number': page_number})

def load_message_ids():
    """Load message IDs for deletion tracking."""
    return load_json_file(MESSAGE_IDS_FILE, {"morning": [], "night": []})

def save_message_ids(message_ids):
    """Save message IDs for deletion tracking."""
    save_json_file(MESSAGE_IDS_FILE, message_ids)

def get_prayer_times():
    """Fetch prayer times from the API."""
    max_retries = 3
    retry_delay = 60  # 1 minute
    for attempt in range(max_retries):
        try:
            logging.info(f"Attempting to fetch prayer times (Attempt {attempt + 1})")
            response = requests.get(API_URL, params=API_PARAMS)
            logging.info(f"Response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            timings = data['data']['timings']
            logging.info(f"Fetched prayer times: {timings}")
            return timings
        except requests.RequestException as e:
            logging.error(f"Error fetching prayer times (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying in {retry_delay} seconds...")
                asyncio.sleep(retry_delay)
            else:
                logging.error("Max retries reached. Using fallback times.")
                return None

def get_next_occurrence(time_str, base_time=None):
    """Get the next occurrence of a given time."""
    if base_time is None:
        base_time = datetime.now(CAIRO_TZ)
    time = datetime.strptime(time_str, '%H:%M').time()
    next_occurrence = base_time.replace(hour=time.hour, minute=time.minute, second=0, microsecond=0)
    if next_occurrence <= base_time:
        next_occurrence += timedelta(days=1)
    return next_occurrence

async def send_image_from_url(image_url, caption=""):
    """Send an image from a URL to the chat."""
    try:
        await bot.send_photo(chat_id=CHAT_ID, photo=image_url, caption=caption)
        logging.info(f"Successfully sent image: {image_url}")
    except telegram.error.TelegramError as e:
        logging.error(f"Telegram error sending image {image_url}: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error sending image {image_url}: {str(e)}")

async def send_quran_pages():
    """Send two Quran pages to the chat."""
    global quran_page_number
    page_1_url = f"{QURAN_PAGES_URL}/photo_{quran_page_number}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{quran_page_number + 1}.jpg"
    try:
        await bot.send_media_group(
            chat_id=CHAT_ID,
            media=[
                telegram.InputMediaPhoto(page_1_url),
                telegram.InputMediaPhoto(page_2_url)
            ],
            caption=f'ورد اليوم - الصفحات {quran_page_number} و {quran_page_number + 1}'
        )
        logging.info(f"Successfully sent Quran pages {quran_page_number} and {quran_page_number + 1}")
        # Increment and save page number
        quran_page_number += 2
        if quran_page_number > 604:
            quran_page_number = 1
        save_quran_page_number(quran_page_number)
    except telegram.error.TelegramError as e:
        logging.error(f"Telegram error sending Quran pages: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error sending Quran pages: {str(e)}")

async def send_athkar(time_of_day):
    """Send Athkar (morning or night) to the chat."""
    global message_ids
    athkar_image_url = f"{ATHKAR_URL}/أذكار_{'الصباح' if time_of_day == 'morning' else 'المساء'}.jpg"
    try:
        message = await bot.send_photo(chat_id=CHAT_ID, photo=athkar_image_url)
        logging.info(f"Successfully sent {time_of_day} Athkar")
        
        # Update message IDs
        message_ids[time_of_day].append(message.message_id)
        if len(message_ids[time_of_day]) > 30:
            oldest_message_id = message_ids[time_of_day].pop(0)
            try:
                await bot.delete_message(chat_id=CHAT_ID, message_id=oldest_message_id)
                logging.info(f"Deleted oldest {time_of_day} Athkar message")
            except telegram.error.BadRequest as e:
                if 'Message to delete not found' in str(e):
                    logging.info(f"Oldest {time_of_day} Athkar message already deleted")
                else:
                    logging.error(f"Error deleting oldest {time_of_day} Athkar message: {str(e)}")
        
        save_message_ids(message_ids)
    except telegram.error.TelegramError as e:
        logging.error(f"Telegram error sending {time_of_day} Athkar: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error sending {time_of_day} Athkar: {str(e)}")
    
async def send_random_verse():
    logging.info("Attempting to send a random verse.")
    if not VERSES:
        logging.warning("No verses available in the database.")
        return
    verse = random.choice(VERSES)
    try:
        message = await bot.send_message(chat_id=CHAT_ID, text=f"«{verse}»")
        VERSE_MESSAGES.append(message.message_id)
        if len(VERSE_MESSAGES) == VERSE_MESSAGES.maxlen:
            oldest_message_id = VERSE_MESSAGES.popleft()
            await bot.delete_message(chat_id=CHAT_ID, message_id=oldest_message_id)
        logging.info(f"Sent random verse: {verse[:20]}...")
    except Exception as e:
        logging.error(f"Error sending random verse: {str(e)}")

async def send_prayer_notification(prayer_name):
    """Send a prayer notification to the chat."""
    prayer_image_url = f"{MISC_URL}/حي_على_الصلاة.png"
    caption = f"صلاة {prayer_name}"
    try:
        await send_image_from_url(prayer_image_url, caption)
        logging.info(f"Successfully sent prayer notification for {prayer_name}")
    except Exception as e:
        logging.error(f"Error sending prayer notification for {prayer_name}: {str(e)}")

def schedule_prayer_times():
    """Schedule prayer times and other daily tasks."""
    timings = get_prayer_times()
    now = datetime.now(CAIRO_TZ)
    prayer_schedule = {}
    if timings:
        try:
            prayer_names = {
                'Fajr': 'الفجر',
                'Dhuhr': 'الظهر',
                'Asr': 'العصر',
                'Maghrib': 'المغرب',
                'Isha': 'العشاء'
            }
            for prayer, arabic_name in prayer_names.items():
                prayer_time = get_next_occurrence(timings[prayer], now)
                prayer_schedule[prayer] = (prayer_time, arabic_name)
            
            morning_athkar_time = prayer_schedule['Fajr'][0] + timedelta(minutes=30)
            night_athkar_time = prayer_schedule['Asr'][0] + timedelta(minutes=30)
            quran_send_time = night_athkar_time + timedelta(minutes=15)
            
            logging.info(f"Prayer schedule for {now.date()}:")
            for prayer, (time, _) in prayer_schedule.items():
                logging.info(f"  {prayer}: {time.strftime('%H:%M')}")
            logging.info(f"Scheduled Morning Athkar: {morning_athkar_time.strftime('%H:%M')}")
            logging.info(f"Scheduled Night Athkar: {night_athkar_time.strftime('%H:%M')}")
            logging.info(f"Scheduled Quran pages: {quran_send_time.strftime('%H:%M')}")
            
            return prayer_schedule, morning_athkar_time, night_athkar_time, quran_send_time
        except ValueError as e:
            logging.error(f"Error parsing prayer times: {str(e)}")
    
    # Fallback to default times if API fails
    logging.warning("Using default prayer times")
    default_times = {
        'Fajr': ('05:00', 'الفجر'),
        'Dhuhr': ('12:00', 'الظهر'),
        'Asr': ('15:00', 'العصر'),
        'Maghrib': ('18:00', 'المغرب'),
        'Isha': ('19:30', 'العشاء')
    }
    prayer_schedule = {prayer: (get_next_occurrence(time), arabic_name) for prayer, (time, arabic_name) in default_times.items()}
    morning_athkar_time = get_next_occurrence("05:30")
    night_athkar_time = get_next_occurrence("15:30")
    quran_send_time = get_next_occurrence("16:00")
    return prayer_schedule, morning_athkar_time, night_athkar_time, quran_send_time

async def reschedule_daily_tasks(scheduler):
    """Reschedule daily tasks based on new prayer times."""
    while True:
        now = datetime.now(CAIRO_TZ)
        prayer_schedule, morning_athkar_time, night_athkar_time, quran_send_time = schedule_prayer_times()

        # Remove existing jobs before scheduling new ones
        scheduler.remove_all_jobs()

        # Schedule prayer notifications
        for prayer, (prayer_time, arabic_name) in prayer_schedule.items():
            if prayer_time > now:
                scheduler.add_job(send_prayer_notification, 'date', run_date=prayer_time, args=[arabic_name])

        # Schedule Athkar and Quran pages
        if morning_athkar_time > now:
            scheduler.add_job(send_athkar, 'date', run_date=morning_athkar_time, args=['morning'])
        if night_athkar_time > now:
            scheduler.add_job(send_athkar, 'date', run_date=night_athkar_time, args=['night'])
        if quran_send_time > now:
            scheduler.add_job(send_quran_pages, 'date', run_date=quran_send_time)
        
        # Schedule random verse every 2 minutes
        scheduler.add_job(send_random_verse, 'interval', minutes=2)
        
        # Log the next scheduled times
        logging.info(f"Next scheduled messages:")
        for prayer, (time, arabic_name) in prayer_schedule.items():
            logging.info(f"  Prayer notification ({arabic_name}): {time.strftime('%H:%M')}")
        logging.info(f"  Morning Athkar: {morning_athkar_time.strftime('%H:%M')}")
        logging.info(f"  Night Athkar: {night_athkar_time.strftime('%H:%M')}")
        logging.info(f"  Quran pages: {quran_send_time.strftime('%H:%M')}")

        # Wait until the next day to reschedule
        next_schedule_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        await asyncio.sleep((next_schedule_time - now).total_seconds())

def shutdown(signal, frame, scheduler):
    """Gracefully shut down the bot."""
    logging.info("Shutting down the bot...")
    scheduler.shutdown()
    asyncio.get_event_loop().stop()

async def main():
    """Main function to run the bot."""
    global quran_page_number, message_ids
    
    # Load saved data
    quran_page_number = load_quran_page_number()
    message_ids = load_message_ids()
    
    scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)
    
    # Schedule initial tasks
    await reschedule_daily_tasks(scheduler)
    
    # Start the scheduler
    scheduler.start()
    
    # Set up signal handlers for graceful shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda s, f: shutdown(s, f, scheduler))
    
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logging.info("Bot operation cancelled.")
    finally:
        # Save data before exiting
        save_quran_page_number(quran_page_number)
        save_message_ids(message_ids)

async def cyclic_test():
    logging.info("Starting cyclic test...")
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=3)
    cycle_count = 0

    while datetime.now() < end_time:
        cycle_count += 1
        logging.info(f"Starting cycle {cycle_count}")
        
        await send_athkar('morning')
        await asyncio.sleep(10)
        
        await send_athkar('night')
        await asyncio.sleep(5)
        
        await send_quran_pages()
        
        logging.info(f"Completed cycle {cycle_count}")
        
        # Wait for the remainder of 30 seconds
        elapsed = (datetime.now() - start_time).total_seconds() % 30
        await asyncio.sleep(30 - elapsed)

    logging.info(f"Cyclic test completed. Total cycles: {cycle_count}")

async def test_bot():
    logging.info("Running bot test...")
    await send_athkar('morning')
    await send_athkar('night')
    await send_quran_pages()
    logging.info("Bot test completed.")

if __name__ == "__main__":
    asyncio.run(cyclic_test())
    asyncio.run(main())