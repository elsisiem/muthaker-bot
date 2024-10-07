import os
import requests
import logging
from pytz import timezone
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
import pytz
import psycopg2

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

# Initialize bot and scheduler
bot = Bot(token=TOKEN)
scheduler = BackgroundScheduler(timezone=CAIRO_TZ)

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# Fetch prayer times from the API
def fetch_prayer_times():
    response = requests.get(API_URL, params=API_PARAMS)
    data = response.json()['data']['timings']
    
    # Convert prayer times to Cairo timezone
    prayer_times = {
        'Fajr': CAIRO_TZ.localize(datetime.strptime(data['Fajr'], "%H:%M")),
        'Dhuhr': CAIRO_TZ.localize(datetime.strptime(data['Dhuhr'], "%H:%M")),
        'Asr': CAIRO_TZ.localize(datetime.strptime(data['Asr'], "%H:%M")),
        'Maghrib': CAIRO_TZ.localize(datetime.strptime(data['Maghrib'], "%H:%M")),
        'Isha': CAIRO_TZ.localize(datetime.strptime(data['Isha'], "%H:%M"))
    }
    
    return prayer_times

# Schedule tasks
def schedule_tasks(prayer_times):
    # Schedule morning athkar 35 minutes after Fajr
    scheduler.add_job(send_athkar_morning, 'date', run_date=prayer_times['Fajr'] + timedelta(minutes=35), id="morning_athkar")

    # Schedule night athkar 35 minutes after Asr
    scheduler.add_job(send_athkar_night, 'date', run_date=prayer_times['Asr'] + timedelta(minutes=35), id="night_athkar")

    # Schedule Quran pages 45 minutes after Asr
    scheduler.add_job(send_quran_pages, 'date', run_date=prayer_times['Asr'] + timedelta(minutes=45), id="quran_pages")

    # Schedule prayer notifications for all prayers
    for prayer, time in prayer_times.items():
        scheduler.add_job(send_prayer_notification, 'date', run_date=time, args=[prayer], id=f"{prayer}_notification")

    scheduler.start()

# Send morning athkar
def send_athkar_morning():
    athkar_image_url = f"{ATHKAR_URL}/أذكار_الصباح.png"
    caption = "#أذكار_الصباح"
    message = bot.send_photo(chat_id=CHAT_ID, photo=athkar_image_url, caption=caption)
    
    # Store the message ID for deletion
    store_message_id('morning_athkar', message.message_id)
    
    logging.info("Sent morning athkar")

# Send night athkar
def send_athkar_night():
    athkar_image_url = f"{ATHKAR_URL}/أذكار_المساء.png"
    caption = "#أذكار_المساء"
    message = bot.send_photo(chat_id=CHAT_ID, photo=athkar_image_url, caption=caption)
    
    # Delete the previous morning athkar
    delete_previous_message('morning_athkar')
    
    # Store the message ID for deletion
    store_message_id('night_athkar', message.message_id)
    
    logging.info("Sent night athkar")

# Send Quran pages
def send_quran_pages():
    last_page = get_last_quran_page()
    page_1_url = f"{QURAN_PAGES_URL}/photo_{last_page}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{last_page + 1}.jpg"
    caption = "#ورد_اليوم"
    
    # Send Quran pages as a media group (photo album)
    bot.send_media_group(
        chat_id=CHAT_ID,
        media=[page_1_url, page_2_url],
        caption=caption
    )
    
    # Update the last Quran page
    update_last_quran_page(last_page + 2)
    
    logging.info(f"Sent Quran pages {last_page} and {last_page + 1}")

# Send prayer notification
def send_prayer_notification(prayer_name):
    arabic_prayers = {
        'Fajr': 'الفجر',
        'Dhuhr': 'الظهر',
        'Asr': 'العصر',
        'Maghrib': 'المغرب',
        'Isha': 'العشاء'
    }
    
    prayer_image_url = f"{MISC_URL}/حي_على_الصلاة.png"
    caption = f"صلاة {arabic_prayers[prayer_name]}"
    
    bot.send_photo(chat_id=CHAT_ID, photo=prayer_image_url, caption=caption)
    logging.info(f"Sent prayer notification for {prayer_name}")

# Database operations
def store_message_id(athkar_type, message_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (type, message_id) VALUES (%s, %s)", (athkar_type, message_id))
    conn.commit()
    cur.close()
    conn.close()

def delete_previous_message(athkar_type):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT message_id FROM messages WHERE type=%s ORDER BY id DESC LIMIT 1", (athkar_type,))
    result = cur.fetchone()
    if result:
        message_id = result[0]
        bot.delete_message(chat_id=CHAT_ID, message_id=message_id)
        logging.info(f"Deleted previous {athkar_type} message")
    cur.close()
    conn.close()

def get_last_quran_page():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT last_page FROM quran_pages LIMIT 1")
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else 220  # Default to page 220 if not found

def update_last_quran_page(page_number):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE quran_pages SET last_page = %s", (page_number,))
    conn.commit()
    cur.close()
    conn.close()

# Main function to start the bot
if __name__ == "__main__":
    # Fetch new prayer times every day
    prayer_times = fetch_prayer_times()
    
    # Log the prayer times and schedule
    logging.info(f"Today's prayer times: {prayer_times}")
    bot.send_message(
        chat_id=CHAT_ID, 
        text=f"*Today's Schedule:*\n"
             f"_Fajr:_ {prayer_times['Fajr'].strftime('%H:%M')} "
             f"_Dhuhr:_ {prayer_times['Dhuhr'].strftime('%H:%M')} "
             f"_Asr:_ {prayer_times['Asr'].strftime('%H:%M')} "
             f"_Maghrib:_ {prayer_times['Maghrib'].strftime('%H:%M')} "
             f"_Isha:_ {prayer_times['Isha'].strftime('%H:%M')}",
        parse_mode="Markdown"
    )
    
    # Schedule tasks
    schedule_tasks(prayer_times)
    
    # Keep the bot running indefinitely
    try:
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
