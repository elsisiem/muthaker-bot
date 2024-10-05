import os
import sys
import telegram
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import requests
import json
import logging
from zoneinfo import ZoneInfo
import random

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Set up bot and chat details
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
bot = telegram.Bot(token=TOKEN)

# GitHub raw content URLs
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"
MISC_URL = f"{GITHUB_RAW_URL}/%D9%85%D9%86%D9%88%D8%B9"

# File paths for JSON files
COUNTER_FILE = "quran_page_counter.json"
MESSAGE_IDS_FILE = "message_ids.json"
RANDOM_ATHKAR_FILE = "random_athkar_ids.json"

# Cairo timezone
CAIRO_TZ = ZoneInfo("Africa/Cairo")

# Prayer times API setup
API_URL = "https://api.aladhan.com/v1/timingsByCity"
params = {
    'city': 'Cairo',
    'country': 'Egypt',
    'method': 3  # Muslim World League
}

# Random athkar messages
RANDOM_ATHKAR = [
    "قولوا : سبحانَ اللهِ ، و الحمدُ للهِ ، ولَا إلهَ إلَّا اللهِ ، واللهُ أكبرُ...",
    "يا عبدالله بن قيس، ألا أدلك على كنز من كنوز الجنة؟ لا حول ولا قوة إلا بالله...",
    "من استغفر للمؤمنين والمؤمنات...",
    "من دخل السوق، فقال: لا إله إلا الله...",
    "﴿ فَمَنْ يَعْمَلْ مِثْقَالَ ذَرَّةٍ خَيْرًا يَرَهُ * وَمَنْ يَعْمَلْ مِثْقَالَ ذَرَّةٍ شَرًّا يَرَهُ ﴾",
    "﴿ فَمَنْ ثَقُلَتْ مَوَازِينُهُ فَأُولَئِكَ هُمُ الْمُفْلِحُونَ...",
    "﴿ فَأَمَّا مَنْ ثَقُلَتْ مَوَازِينُهُ...",
    "«من قال في يوم مائتي مرة..."
]

# Load/Save JSON helper functions
def load_json_file(file_path, default_value):
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
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f)
        logging.info(f"Successfully saved data to {file_path}")
    except Exception as e:
        logging.error(f"Failed to save data to {file_path}: {str(e)}")

# Quran page number logic
def load_quran_page_number():
    return load_json_file(COUNTER_FILE, {'page_number': 200}).get('page_number', 200)

def save_quran_page_number(page_number):
    save_json_file(COUNTER_FILE, {'page_number': page_number})

# Message ID logic
def load_message_ids():
    return load_json_file(MESSAGE_IDS_FILE, {"morning": None, "night": None})

def save_message_ids(message_ids):
    save_json_file(MESSAGE_IDS_FILE, message_ids)

# Random Athkar management
def load_random_athkar_ids():
    return load_json_file(RANDOM_ATHKAR_FILE, [])

def save_random_athkar_ids(ids):
    save_json_file(RANDOM_ATHKAR_FILE, ids)

# Fetch prayer times
def get_prayer_times():
    max_retries = 3
    retry_delay = 60  # 1 minute
    for attempt in range(max_retries):
        try:
            logging.info(f"Attempting to fetch prayer times (Attempt {attempt + 1})")
            response = requests.get(API_URL, params=params)
            logging.info(f"Response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            timings = data['data']['timings']
            date = data['data']['date']['gregorian']['date']
            logging.info(f"Fetched prayer times for {date}: {timings}")
            return timings, date
        except requests.RequestException as e:
            logging.error(f"Error fetching prayer times (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                logging.info(f"Retrying in {retry_delay} seconds...")
                asyncio.sleep(retry_delay)
            else:
                logging.error("Max retries reached. Using fallback times.")
                return None, None

# Schedule test messages
async def send_test_message():
    message = random.choice(RANDOM_ATHKAR)
    try:
        await bot.send_message(chat_id=CHAT_ID, text=f"«{message}»")
        logging.info("Test message sent.")
    except telegram.error.TelegramError as e:
        logging.error(f"Error sending test message: {str(e)}")

# Schedule Salah notifications with image
async def send_prayer_notification(prayer_name):
    try:
        image_url = f"{MISC_URL}/حيعلىالصلاة.png"
        await bot.send_photo(chat_id=CHAT_ID, photo=image_url, caption=f"صلاة {prayer_name}")
        logging.info(f"Successfully sent prayer notification for {prayer_name}")
    except telegram.error.TelegramError as e:
        logging.error(f"Error sending prayer notification: {str(e)}")

# Testing: send random athkar every 10 minutes for debugging
async def schedule_test_athkar(scheduler):
    scheduler.add_job(send_test_message, 'interval', minutes=10)
    logging.info("Test athkar scheduled every 10 minutes.")

# Main function
async def main():
    timings, date = get_prayer_times()

    # Schedule prayers and test messages
    scheduler = AsyncIOScheduler()
    scheduler.start()

    if timings:
        # Log next scheduled messages
        for prayer, time in timings.items():
            next_occurrence = get_next_occurrence(time)
            logging.info(f"{prayer} scheduled at {time}, occurring at {next_occurrence}")

        # Example of scheduling prayers with image notifications
        scheduler.add_job(send_prayer_notification, 'date', run_date=get_next_occurrence(timings['Asr']), args=['العصر'])

        # Testing function for athkar every 10 minutes
        await schedule_test_athkar(scheduler)

if __name__ == '__main__':
    asyncio.run(main())
