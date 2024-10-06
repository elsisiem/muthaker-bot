import os
import sys
import telegram
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import requests
import json
import logging
import random
from collections import deque
import pytz
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base()

# Database Models
class QuranPage(Base):
    __tablename__ = 'quran_pages'
    id = Column(Integer, primary_key=True)
    page_number = Column(Integer, default=1)

class MessageID(Base):
    __tablename__ = 'message_ids'
    id = Column(Integer, primary_key=True)
    time_of_day = Column(String, nullable=False)  # 'morning' or 'night'
    message_id = Column(Integer, nullable=False)

# Create the tables
Base.metadata.create_all(engine)

# Telegram bot setup
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
bot = telegram.Bot(token=TOKEN)

# GitHub raw content URLs for your image folders
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"

# Timezone setup for Cairo
CAIRO_TZ = pytz.timezone('Africa/Cairo')

# Prayer times API setup
API_URL = "https://api.aladhan.com/v1/timingsByCity"
params = {
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


# Get current Quran page from the database
def get_quran_page():
    quran_page = session.query(QuranPage).first()
    if not quran_page:
        quran_page = QuranPage(page_number=1)
        session.add(quran_page)
        session.commit()
    return quran_page.page_number

# Update Quran page number in the database
def update_quran_page(page_number):
    quran_page = session.query(QuranPage).first()
    if quran_page:
        quran_page.page_number = page_number
        session.commit()

# Save message ID in the database
def save_message_id(time_of_day, message_id):
    message = MessageID(time_of_day=time_of_day, message_id=message_id)
    session.add(message)
    session.commit()

# Get prayer times from API
def get_prayer_times():
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        return data['data']['timings']
    except requests.RequestException as e:
        logging.error(f"Error fetching prayer times: {e}")
        return None

# Get next occurrence of a time
def get_next_occurrence(time_str):
    now = datetime.now(CAIRO_TZ)
    time = datetime.strptime(time_str, '%H:%M').time()
    occurrence = now.replace(hour=time.hour, minute=time.minute, second=0, microsecond=0)
    if occurrence <= now:
        occurrence += timedelta(days=1)
    return occurrence

# Send Quran pages
async def send_quran_pages():
    page_number = get_quran_page()
    page_1_url = f"{QURAN_PAGES_URL}/photo_{page_number}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{page_number + 1}.jpg"
    
    try:
        await bot.send_media_group(
            chat_id=CHAT_ID,
            media=[
                telegram.InputMediaPhoto(page_1_url),
                telegram.InputMediaPhoto(page_2_url)
            ],
            caption=f'ورد اليوم - الصفحات {page_number} و {page_number + 1}'
        )
        logging.info(f"Sent Quran pages {page_number} and {page_number + 1}")
        new_page_number = page_number + 2
        if new_page_number > 604:
            new_page_number = 1
        update_quran_page(new_page_number)
    except Exception as e:
        logging.error(f"Error sending Quran pages: {e}")

# Send Athkar
async def send_athkar(time_of_day):
    athkar_image_url = f"{ATHKAR_URL}/أذكار_{'الصباح' if time_of_day == 'morning' else 'المساء'}.jpg"
    try:
        message = await bot.send_photo(chat_id=CHAT_ID, photo=athkar_image_url)
        save_message_id(time_of_day, message.message_id)
        logging.info(f"Sent {time_of_day} Athkar")
    except Exception as e:
        logging.error(f"Error sending {time_of_day} Athkar: {e}")

# Send random verse
async def send_random_verse():
    verse = random.choice(VERSES)
    try:
        await bot.send_message(chat_id=CHAT_ID, text=verse)
        logging.info("Sent random verse")
    except Exception as e:
        logging.error(f"Error sending random verse: {e}")

# Scheduler setup
scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)

def schedule_tasks():
    timings = get_prayer_times()
    if not timings:
        return

    fajr_time = get_next_occurrence(timings['Fajr'])
    asr_time = get_next_occurrence(timings['Asr'])

    # Morning Athkar (30 mins after Fajr)
    scheduler.add_job(send_athkar, 'date', run_date=fajr_time + timedelta(minutes=30), args=['morning'])

    # Night Athkar (30 mins after Asr)
    scheduler.add_job(send_athkar, 'date', run_date=asr_time + timedelta(minutes=30), args=['night'])

    # Quran pages (45 mins after Asr)
    scheduler.add_job(send_quran_pages, 'date', run_date=asr_time + timedelta(minutes=45))

    # Random verse during the day
    verse_time = datetime.now(CAIRO_TZ).replace(hour=10, minute=0) + timedelta(minutes=random.randint(0, 720))
    scheduler.add_job(send_random_verse, 'date', run_date=verse_time)

async def main():
    schedule_tasks()
    scheduler.start()
    logging.info("Scheduler started")
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
        sys.exit(0)
