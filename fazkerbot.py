import os
import asyncio
import logging
from datetime import datetime, timedelta
import random

import pytz
from telegram import Bot, InputMediaPhoto
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp
import psycopg2
from psycopg2.extras import DictCursor


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Constants
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
DATABASE_URL = os.environ['DATABASE_URL']
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"
MISC_URL = f"{GITHUB_RAW_URL}/%D9%85%D9%86%D9%88%D8%B9"
CAIRO_TZ = pytz.timezone('Africa/Cairo')
API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {
    'city': 'Cairo',
    'country': 'Egypt',
    'method': 3  # Muslim World League
}

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

class DatabaseManager:
    def __init__(self, database_url):
        self.database_url = database_url

    def get_connection(self):
        return psycopg2.connect(self.database_url, sslmode='require')

    def execute_query(self, query, params=None):
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query, params)
                conn.commit()
                if cur.description:
                    return cur.fetchall()

    def init_db(self):
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

    def get_quran_page_number(self):
        result = self.execute_query("SELECT value FROM bot_state WHERE key = 'quran_page_number'")
        return int(result[0]['value']) if result else 206

    def save_quran_page_number(self, page_number):
        self.execute_query(
            "INSERT INTO bot_state (key, value) VALUES ('quran_page_number', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = %s",
            (str(page_number), str(page_number))
        )

    def get_message_ids(self):
        result = self.execute_query("SELECT value FROM bot_state WHERE key = 'message_ids'")
        return eval(result[0]['value']) if result else {"morning": [], "night": []}

    def save_message_ids(self, message_ids):
        self.execute_query(
            "INSERT INTO bot_state (key, value) VALUES ('message_ids', %s) "
            "ON CONFLICT (key) DO UPDATE SET value = %s",
            (str(message_ids), str(message_ids))
        )

db_manager = DatabaseManager(DATABASE_URL)
db_manager.init_db()

async def get_prayer_times():
    max_retries = 3
    retry_delay = 60  # 1 minute
    for attempt in range(max_retries):
        try:
            logging.info(f"Attempting to fetch prayer times (Attempt {attempt + 1})")
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, params=API_PARAMS) as response:
                    response.raise_for_status()
                    data = await response.json()
                    timings = data['data']['timings']
                    logging.info(f"Fetched prayer times: {timings}")
                    return timings
        except aiohttp.ClientError as e:
            logging.error(f"Error fetching prayer times (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
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

async def send_image_from_url(context, image_url, caption=""):
    try:
        await context.bot.send_photo(chat_id=CHAT_ID, photo=image_url, caption=caption)
        logging.info(f"Successfully sent image: {image_url}")
    except Exception as e:
        logging.error(f"Error sending image {image_url}: {str(e)}")

async def send_quran_pages(context):
    quran_page_number = db_manager.get_quran_page_number()
    page_1_url = f"{QURAN_PAGES_URL}/photo_{quran_page_number}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{quran_page_number + 1}.jpg"
    try:
        await context.bot.send_media_group(
            chat_id=CHAT_ID,
            media=[
                InputMediaPhoto(page_1_url),
                InputMediaPhoto(page_2_url)
            ],
            caption=f'ورد اليوم - الصفحات {quran_page_number} و {quran_page_number + 1}'
        )
        logging.info(f"Successfully sent Quran pages {quran_page_number} and {quran_page_number + 1}")
        quran_page_number += 2
        if quran_page_number > 604:
            quran_page_number = 1
        db_manager.save_quran_page_number(quran_page_number)
    except Exception as e:
        logging.error(f"Error sending Quran pages: {str(e)}")

async def send_athkar(context, time_of_day):
    message_ids = db_manager.get_message_ids()
    athkar_image_url = f"{ATHKAR_URL}/أذكار_{'الصباح' if time_of_day == 'morning' else 'المساء'}.jpg"
    try:
        message = await context.bot.send_photo(chat_id=CHAT_ID, photo=athkar_image_url)
        logging.info(f"Successfully sent {time_of_day} Athkar")
        
        message_ids[time_of_day].append(message.message_id)
        if len(message_ids[time_of_day]) > 1:
            for msg_id in message_ids[time_of_day][:-1]:
                try:
                    await context.bot.delete_message(chat_id=CHAT_ID, message_id=msg_id)
                    logging.info(f"Deleted previous {time_of_day} Athkar message ID: {msg_id}")
                except Exception as e:
                    logging.error(f"Error deleting message {msg_id}: {str(e)}")
            message_ids[time_of_day] = message_ids[time_of_day][-1:]
        db_manager.save_message_ids(message_ids)
    except Exception as e:
        logging.error(f"Error sending {time_of_day} Athkar: {str(e)}")

async def send_random_verse(context):
    verse = random.choice(VERSES)
    try:
        await context.bot.send_message(chat_id=CHAT_ID, text=verse)
        logging.info("Successfully sent a random verse.")
    except Exception as e:
        logging.error(f"Error sending random verse: {str(e)}")

async def schedule_tasks():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_random_verse, 'cron', hour=12, minute=0)
    
    prayer_times = await get_prayer_times()

    if prayer_times:
        next_fajr = get_next_occurrence(prayer_times['Fajr'])
        next_asr = get_next_occurrence(prayer_times['Asr'])
        
        # Schedule morning Athkar
        scheduler.add_job(send_athkar, 'date', run_date=next_fajr + timedelta(minutes=30), args=('morning',))
        
        # Schedule night Athkar
        scheduler.add_job(send_athkar, 'date', run_date=next_asr + timedelta(minutes=30), args=('night',))
        
        # Schedule daily Quran pages 15 minutes after night Athkar
        scheduler.add_job(send_quran_pages, 'date', run_date=next_asr + timedelta(minutes=45))
    
    scheduler.start()

async def main():
    bot = Bot(token=TOKEN)
    await schedule_tasks()

if __name__ == '__main__':
    asyncio.run(main())
