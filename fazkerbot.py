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
CAIRO_TZ = pytz.timezone('Africa/Cairo')
API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}

# Verses to send randomly
VERSES = [
    "سبحانَ اللهِ والحمدُ للهِ ولا إلهَ إلا اللهُ واللهُ أكبرُ.",
    "لا حول ولا قوة إلا بالله.",
    "من استغفر للمؤمنين والمؤمنات كتب الله له بكل مؤمن حسنة.",
    "من قال: لا إله إلا الله وحده لا شريك له.",
    "﴿ فَمَنْ يَعْمَلْ مِثْقَالَ ذَرَّةٍ خَيْرًا يَرَهُ ﴾",
    "﴿ فَأَمَّا مَنْ ثَقُلَتْ مَوَازِينُهُ * فَهُوَ فِي عِيشَةٍ رَاضِيَةٍ ﴾",
    "نارٌ حامية."
]

class DatabaseManager:
    def __init__(self, database_url):
        self.database_url = database_url

    def get_connection(self):
        return psycopg2.connect(self.database_url, sslmode='require')

    def init_db(self):
        query = """
        CREATE TABLE IF NOT EXISTS bot_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
        self.execute_query(query)

    def execute_query(self, query, params=None):
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query, params)
                conn.commit()
                if cur.description:
                    return cur.fetchall()

db_manager = DatabaseManager(DATABASE_URL)
db_manager.init_db()

async def get_prayer_times():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=API_PARAMS) as response:
            if response.status == 200:
                data = await response.json()
                return data['data']['timings']
    return None

def get_next_occurrence(time_str, base_time=None):
    if base_time is None:
        base_time = datetime.now(CAIRO_TZ)
    time = datetime.strptime(time_str, '%H:%M').time()
    next_occurrence = base_time.replace(hour=time.hour, minute=time.minute, second=0, microsecond=0)
    if next_occurrence <= base_time:
        next_occurrence += timedelta(days=1)
    return next_occurrence

async def send_random_verse(bot):
    verse = random.choice(VERSES)
    await bot.send_message(chat_id=CHAT_ID, text=f"«{verse}»")
    logging.info(f"Sent random verse: {verse}")

async def send_daily_log(bot, timings):
    now = datetime.now(CAIRO_TZ)
    log_message = f"Today's prayer times (Cairo): {timings}\nCurrent time: {now.strftime('%Y-%m-%d %H:%M:%S')}\nNext random verse in 2 minutes."
    await bot.send_message(chat_id=CHAT_ID, text=log_message)
    logging.info("Daily log sent.")

async def schedule_daily_tasks(bot, scheduler):
    scheduler.remove_all_jobs()
    timings = await get_prayer_times()

    if timings:
        now = datetime.now(CAIRO_TZ)
        await send_daily_log(bot, timings)
        
        morning_athkar_time = get_next_occurrence(timings['Fajr'], now) + timedelta(minutes=30)
        scheduler.add_job(send_random_verse, 'interval', minutes=2, args=[bot])

async def main():
    bot = Bot(token=TOKEN)
    scheduler = AsyncIOScheduler()
    scheduler.start()
    await schedule_daily_tasks(bot, scheduler)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
