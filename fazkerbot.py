import os
import logging
import requests
import pytz
from datetime import datetime, timedelta
import psycopg2
from telegram import Bot
from apscheduler.schedulers.background import BackgroundScheduler

# CONSTANTS
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

# Initialize bot and logger
bot = Bot(token=TOKEN)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

# Database connection
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Scheduler for dynamic scheduling
scheduler = BackgroundScheduler()

def fetch_prayer_times():
    """Fetch prayer times for the current day from Aladhan API."""
    response = requests.get(API_URL, params=API_PARAMS)
    data = response.json()
    timings = data['data']['timings']
    return {
        'Fajr': timings['Fajr'],
        'Asr': timings['Asr'],
        'Maghrib': timings['Maghrib'],
        'Isha': timings['Isha']
    }

def get_scheduled_times(prayer_times):
    """Calculate times for athkar and Quran based on fetched prayer times."""
    fajr_time = datetime.strptime(prayer_times['Fajr'], "%H:%M").replace(tzinfo=CAIRO_TZ)
    asr_time = datetime.strptime(prayer_times['Asr'], "%H:%M").replace(tzinfo=CAIRO_TZ)
    
    return {
        'morning_athkar': fajr_time + timedelta(minutes=35),
        'night_athkar': asr_time + timedelta(minutes=35),
        'quran_pages': asr_time + timedelta(minutes=45),
        'prayer_notifications': {
            'Asr': asr_time,
            'Maghrib': datetime.strptime(prayer_times['Maghrib'], "%H:%M").replace(tzinfo=CAIRO_TZ),
            'Isha': datetime.strptime(prayer_times['Isha'], "%H:%M").replace(tzinfo=CAIRO_TZ)
        }
    }

def send_morning_athkar():
    """Send morning athkar and delete the previous night's athkar."""
    photo_url = f"{ATHKAR_URL}/أذاكر_الصباح.png"
    message = bot.send_photo(chat_id=CHAT_ID, photo=photo_url, caption="#أذكار_الصباح")
    log_message_and_delete_previous("morning_athkar", message.message_id, "night_athkar")

def send_night_athkar():
    """Send night athkar and delete the previous morning's athkar."""
    photo_url = f"{ATHKAR_URL}/أذكار_المساء.png"
    message = bot.send_photo(chat_id=CHAT_ID, photo=photo_url, caption="#أذكار_المساء")
    log_message_and_delete_previous("night_athkar", message.message_id, "morning_athkar")

def send_quran_pages():
    """Send two Quran pages with the caption #ورد_اليوم."""
    cur.execute("SELECT page_number FROM quran_progress WHERE id = 1")
    quran_page_number = cur.fetchone()[0]
    
    page_1_url = f"{QURAN_PAGES_URL}/photo_{quran_page_number}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{quran_page_number + 1}.jpg"
    
    bot.send_media_group(
        chat_id=CHAT_ID,
        media=[
            {"type": "photo", "media": page_1_url},
            {"type": "photo", "media": page_2_url}
        ],
        caption="#ورد_اليوم"
    )
    
    # Update next Quran page in the database
    next_page = quran_page_number + 2 if quran_page_number < 603 else 1
    cur.execute("UPDATE quran_progress SET page_number = %s WHERE id = 1", (next_page,))
    conn.commit()

def send_prayer_notification(prayer_name):
    """Send a notification image at prayer times."""
    prayer_image_url = f"{MISC_URL}/حي_على_الصلاة.png"
    caption = f"صلاة {prayer_name}"
    bot.send_photo(chat_id=CHAT_ID, photo=prayer_image_url, caption=caption)

def log_message_and_delete_previous(current_athkar, new_message_id, previous_athkar):
    """Log message ID and delete the previous athkar message."""
    cur.execute(f"SELECT message_id FROM athkar_messages WHERE name = '{previous_athkar}'")
    previous_message_id = cur.fetchone()[0]
    if previous_message_id:
        try:
            bot.delete_message(chat_id=CHAT_ID, message_id=previous_message_id)
        except:
            logger.warning(f"Failed to delete {previous_athkar} message.")
    
    cur.execute(f"UPDATE athkar_messages SET message_id = %s WHERE name = %s", (new_message_id, current_athkar))
    conn.commit()

def schedule_tasks():
    """Fetch new prayer times daily and schedule tasks."""
    prayer_times = fetch_prayer_times()
    scheduled_times = get_scheduled_times(prayer_times)
    
    # Log schedule and send initial message
    log_day_schedule(prayer_times, scheduled_times)

    # Schedule tasks
    scheduler.add_job(send_morning_athkar, 'date', run_date=scheduled_times['morning_athkar'])
    scheduler.add_job(send_night_athkar, 'date', run_date=scheduled_times['night_athkar'])
    scheduler.add_job(send_quran_pages, 'date', run_date=scheduled_times['quran_pages'])

    # Schedule prayer notifications
    for prayer_name, prayer_time in scheduled_times['prayer_notifications'].items():
        scheduler.add_job(send_prayer_notification, 'date', run_date=prayer_time, args=[prayer_name])

    scheduler.start()

def log_day_schedule(prayer_times, scheduled_times):
    """Log the schedule for the day and send an overview to the Telegram channel."""
    message = f"""
*Prayer Times Overview:*
- Fajr: {prayer_times['Fajr']}
- Asr: {prayer_times['Asr']}
- Maghrib: {prayer_times['Maghrib']}
- Isha: {prayer_times['Isha']}

*Today's Schedule:*
- Morning Athkar: {scheduled_times['morning_athkar'].strftime('%H:%M')}
- Night Athkar: {scheduled_times['night_athkar'].strftime('%H:%M')}
- Quran Pages: {scheduled_times['quran_pages'].strftime('%H:%M')}

*Prayer Notifications:*
- Asr: {scheduled_times['prayer_notifications']['Asr'].strftime('%H:%M')}
- Maghrib: {scheduled_times['prayer_notifications']['Maghrib'].strftime('%H:%M')}
- Isha: {scheduled_times['prayer_notifications']['Isha'].strftime('%H:%M')}
"""
    bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')

# Main execution
if __name__ == '__main__':
    schedule_tasks()
