import os
import datetime
import pytz
import urllib.request
import telegram
import psycopg2

# Constants
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
DATABASE_URL = os.environ['DATABASE_URL']
CAIRO_TZ = pytz.timezone('Africa/Cairo')
API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}

# File paths
QURAN_PAGES_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"
MISC_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master/%D9%85%D9%86%D9%88%D8%B9"

# Function definitions
def get_prayer_times():
    response = urllib.request.urlopen(API_URL, data=urllib.parse.urlencode(API_PARAMS).encode())
    data = response.read().decode()
    prayer_times = json.loads(data)['data']['timings']
    return prayer_times

def format_prayer_time(prayer_time, prayer_name):
    prayer_time = datetime.datetime.strptime(prayer_time, '%H:%M:%S')
    prayer_time = prayer_time.replace(tzinfo=CAIRO_TZ)
    formatted_time = prayer_time.strftime('%H:%M')
    return f"صلاة {prayer_name} في {formatted_time}"

def schedule_message(context, message_type, delay, chat_id, image_url, caption):
    job = context.job_queue.run_once(send_message, delay, args=[chat_id, message_type, image_url, caption])
    return job.id

def send_message(chat_id, message_type, image_url, caption):
    with db_connection() as conn:
        with conn.cursor() as cursor:
            if message_type == "athkar":
                cursor.execute("DELETE FROM sent_messages WHERE message_type = 'athkar'")
            cursor.execute("INSERT INTO sent_messages (message_type, image_url) VALUES (%s, %s)", (message_type, image_url))
            conn.commit()

    bot = telegram.Bot(token=TOKEN)
    bot.send_photo(chat_id=chat_id, photo=open(image_url, 'rb'), caption=caption)

def send_quran_pages():
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT last_quran_page FROM quran_pages")
            last_quran_page = cursor.fetchone()[0]

    quran_page_number = last_quran_page + 1
    page_1_url = f"{QURAN_PAGES_URL}/photo_{quran_page_number}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{quran_page_number + 1}.jpg"

    page_1_data = urllib.request.urlopen(page_1_url).read()
    page_2_data = urllib.request.urlopen(page_2_url).read()

    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE quran_pages SET last_quran_page = %s", (quran_page_number + 1,))
            conn.commit()

    bot = telegram.Bot(token=TOKEN)
    bot.send_photo(chat_id=CHAT_ID, photo=page_1_data, caption="#ورد_اليوم")
    bot.send_photo(chat_id=CHAT_ID, photo=page_2_data, caption="#ورد_اليوم")

def download_image(url):
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.write(urllib.request.urlopen(url).read())
    temp_file.close()
    return temp_file.name

def db_connection():
    return psycopg2.connect(DATABASE_URL)

# Main block
if __name__ == '__main__':
    with db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("CREATE TABLE IF NOT EXISTS sent_messages (id SERIAL PRIMARY KEY, message_type TEXT, image_url TEXT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS quran_pages (last_quran_page INTEGER DEFAULT 0)")
            conn.commit()

    prayer_times = get_prayer_times()
    log_message = "**جدول الأذكار اليومية:**\n"
    for prayer_name, prayer_time in prayer_times.items():
        formatted_time = format_prayer_time(prayer_time, prayer_name)
        log_message += f"- {formatted_time}\n"

        if prayer_name == "Fajr":
            delay = datetime.datetime.strptime(prayer_time, '%H:%M:%S').replace(tzinfo=CAIRO_TZ) + datetime.timedelta(minutes=35) - datetime.datetime.now(CAIRO_TZ)
            athkar_image_url = f"{ATHKAR_URL}/أذاكر_الصباح.png"
            schedule_message(context, "athkar", delay.total_seconds(), CHAT_ID, athkar_image_url, "#أذكار_الصباح")
        elif prayer_name == "Asr":
            delay = datetime.datetime.strptime(prayer_time, '%H:%M:%S').replace(tzinfo=CAIRO_TZ) + datetime.timedelta(minutes=35) - datetime.datetime.now(CAIRO_TZ)
            athkar_image_url = f"{ATHKAR_URL}/أذاكر_المساء.png"
            schedule_message(context, "athkar", delay.total_seconds(), CHAT_ID, athkar_image_url, "#أذكار_المساء")
            delay = datetime.datetime.strptime(prayer_time, '%H:%M:%S').replace(tzinfo=CAIRO_TZ) + datetime.timedelta(minutes=45) - datetime.datetime.now(CAIRO_TZ)
            schedule_message(context, "quran", delay.total_seconds(), CHAT_ID, None, None)  # Schedule sending Quran pages later
        else:
            delay = datetime.datetime.strptime(prayer_time, '%H:%M:%S').replace(tzinfo=CAIRO_TZ) - datetime.datetime.now(CAIRO_TZ)
            prayer_image_url = f"{MISC_URL}/حي_على_الصلاة.png"
            schedule_message(context, "prayer", delay.total_seconds(), CHAT_ID, prayer_image_url, f"صلاة {prayer_name}")

    bot = telegram.Bot(token=TOKEN)
    bot.send_message(chat_id=CHAT_ID, text=log_message)