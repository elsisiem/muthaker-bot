import os
import sys
import telegram
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import requests
import json
import logging
import signal
from zoneinfo import ZoneInfo

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

# GitHub raw content URLs for your image folders
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"

# File paths for JSON files
COUNTER_FILE = "quran_page_counter.json"
MESSAGE_IDS_FILE = "message_ids.json"

# Cairo timezone using zoneinfo
CAIRO_TZ = ZoneInfo("Africa/Cairo")

# Prayer times API setup
API_URL = "https://api.aladhan.com/v1/timingsByCity"
params = {
    'city': 'Cairo',
    'country': 'Egypt',
    'method': 3  # Muslim World League
}

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

def load_quran_page_number():
    data = load_json_file(COUNTER_FILE, {'page_number': 200})
    return data.get('page_number', 200)

def save_quran_page_number(page_number):
    save_json_file(COUNTER_FILE, {'page_number': page_number})

def load_message_ids():
    return load_json_file(MESSAGE_IDS_FILE, {"morning": None, "night": None})

def save_message_ids(message_ids):
    save_json_file(MESSAGE_IDS_FILE, message_ids)

quran_page_number = load_quran_page_number()
message_ids = load_message_ids()

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
    if base_time is None:
        base_time = datetime.now(CAIRO_TZ)
    time = datetime.strptime(time_str, '%H:%M').time()
    next_occurrence = base_time.replace(hour=time.hour, minute=time.minute, second=0, microsecond=0)
    if next_occurrence <= base_time:
        next_occurrence += timedelta(days=1)
    return next_occurrence

async def send_image_from_url(image_url, caption=""):
    try:
        await bot.send_photo(chat_id=CHAT_ID, photo=image_url, caption=caption)
        logging.info(f"Successfully sent image: {image_url}")
    except telegram.error.TelegramError as e:
        logging.error(f"Telegram error sending image {image_url}: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error sending image {image_url}: {str(e)}")

async def send_quran_pages():
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
    global message_ids
    athkar_image_url = f"{ATHKAR_URL}/أذكار_{'الصباح' if time_of_day == 'morning' else 'المساء'}.jpg"
    try:
        message = await bot.send_photo(chat_id=CHAT_ID, photo=athkar_image_url)
        logging.info(f"Successfully sent {time_of_day} Athkar")
        # Delete the previous Athkar message
        previous_time = 'night' if time_of_day == 'morning' else 'morning'
        if message_ids[previous_time]:
            try:
                await bot.delete_message(chat_id=CHAT_ID, message_id=message_ids[previous_time])
                logging.info(f"Deleted previous {previous_time} Athkar message")
            except telegram.error.BadRequest as e:
                if 'Message to delete not found' in str(e):
                    logging.info(f"Previous {previous_time} Athkar message already deleted")
                else:
                    logging.error(f"Error deleting previous {previous_time} Athkar message: {str(e)}")
        # Update message IDs
        message_ids[previous_time] = None
        message_ids[time_of_day] = message.message_id
        save_message_ids(message_ids)
    except telegram.error.TelegramError as e:
        logging.error(f"Telegram error sending {time_of_day} Athkar: {str(e)}")
    except Exception as e:
        logging.error(f"Unexpected error sending {time_of_day} Athkar: {str(e)}")

def schedule_prayer_times():
    timings = get_prayer_times()
    now = datetime.now(CAIRO_TZ)
    if timings:
        try:
            fajr_time = get_next_occurrence(timings['Fajr'], now) + timedelta(minutes=30)
            asr_time = get_next_occurrence(timings['Asr'], now) + timedelta(minutes=30)
            quran_send_time = asr_time + timedelta(minutes=15)
            logging.info(f"Scheduled Fajr time: {fajr_time}, Asr time: {asr_time}, Quran send time: {quran_send_time}")
            return fajr_time, asr_time, quran_send_time
        except ValueError as e:
            logging.error(f"Error parsing prayer times: {str(e)}")
    # Fallback to default times if API fails
    fajr_time = get_next_occurrence("05:00", now)
    asr_time = get_next_occurrence("15:00", now)
    quran_send_time = get_next_occurrence("16:00", now)
    logging.warning(f"Using default times: Fajr {fajr_time}, Asr {asr_time}, Quran {quran_send_time}")
    return fajr_time, asr_time, quran_send_time

async def reschedule_daily_tasks(scheduler):
    while True:
        fajr_time, asr_time, quran_send_time = schedule_prayer_times()
        now = datetime.now(CAIRO_TZ)

        # Remove existing jobs before scheduling new ones
        scheduler.remove_all_jobs()

        # Schedule new jobs
        if fajr_time > now:
            scheduler.add_job(send_athkar, 'date', run_date=fajr_time, args=['morning'])
        if asr_time > now:
            scheduler.add_job(send_athkar, 'date', run_date=asr_time, args=['night'])
        if quran_send_time > now:
            scheduler.add_job(send_quran_pages, 'date', run_date=quran_send_time)
        
        # If all times have passed for today, schedule for tomorrow
        if all(time <= now for time in [fajr_time, asr_time, quran_send_time]):
            tomorrow = now + timedelta(days=1)
            fajr_time, asr_time, quran_send_time = schedule_prayer_times()
            scheduler.add_job(send_athkar, 'date', run_date=fajr_time, args=['morning'])
            scheduler.add_job(send_athkar, 'date', run_date=asr_time, args=['night'])
            scheduler.add_job(send_quran_pages, 'date', run_date=quran_send_time)

        # Log the next scheduled times
        logging.info(f"Next scheduled messages:\nMorning Athkar at {fajr_time}\nNight Athkar at {asr_time}\nQuran pages at {quran_send_time}")

        # Wait until the next day to reschedule
        next_schedule_time = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        await asyncio.sleep((next_schedule_time - now).total_seconds())

def shutdown(signal, frame, scheduler):
    logging.info("Shutting down the bot...")
    scheduler.shutdown()
    asyncio.get_event_loop().stop()

async def main():
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

async def cyclic_test():
    logging.info("Starting cyclic test...")
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=10)
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
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            asyncio.run(test_bot())
        elif sys.argv[1] == "cyclic_test":
            asyncio.run(cyclic_test())
        else:
            print("Unknown test type. Use 'test' or 'cyclic_test'.")
    else:
        asyncio.run(main())