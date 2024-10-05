import os
import logging
from datetime import datetime, timedelta
import pytz
import requests
from telegram import Bot
from apscheduler.schedulers.blocking import BlockingScheduler
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up bot and chat details
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
bot = Bot(token=TOKEN)

# GitHub raw content URLs
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
ATHKAR_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D8%A3%D8%B0%D9%83%D8%A7%D8%B1"

# Cairo timezone
CAIRO_TZ = pytz.timezone('Africa/Cairo')

# Prayer times API setup
API_URL = "https://api.aladhan.com/v1/timingsByCity"
API_PARAMS = {'city': 'Cairo', 'country': 'Egypt', 'method': 3}

# Database setup
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = sa.create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)

class BotState(Base):
    __tablename__ = 'bot_state'
    id = sa.Column(sa.Integer, primary_key=True)
    quran_page_number = sa.Column(sa.Integer, default=1)
    last_athkar_type = sa.Column(sa.String, default='night')

def initialize_database():
    try:
        Base.metadata.create_all(engine)
        logging.info("Database initialized successfully")
    except OperationalError as e:
        logging.error(f"Failed to initialize database: {str(e)}")
        return False
    return True

def get_bot_state():
    try:
        with Session() as session:
            state = session.query(BotState).first()
            if not state:
                state = BotState()
                session.add(state)
                session.commit()
            return state
    except OperationalError as e:
        logging.error(f"Database error when getting bot state: {str(e)}")
        return BotState(quran_page_number=1, last_athkar_type='night')

def update_bot_state(quran_page_number=None, last_athkar_type=None):
    try:
        with Session() as session:
            state = session.query(BotState).first()
            if not state:
                state = BotState()
                session.add(state)
            if quran_page_number is not None:
                state.quran_page_number = quran_page_number
            if last_athkar_type is not None:
                state.last_athkar_type = last_athkar_type
            session.commit()
    except OperationalError as e:
        logging.error(f"Database error when updating bot state: {str(e)}")

def get_prayer_times():
    try:
        response = requests.get(API_URL, params=API_PARAMS)
        response.raise_for_status()
        data = response.json()
        return data['data']['timings']
    except requests.RequestException as e:
        logging.error(f"Error fetching prayer times: {str(e)}")
        return None

def send_image(image_url, caption=""):
    try:
        bot.send_photo(chat_id=CHAT_ID, photo=image_url, caption=caption)
        logging.info(f"Sent image: {image_url}")
    except Exception as e:
        logging.error(f"Error sending image {image_url}: {str(e)}")

def send_quran_pages():
    state = get_bot_state()
    page_1_url = f"{QURAN_PAGES_URL}/photo_{state.quran_page_number}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{state.quran_page_number + 1}.jpg"
    try:
        bot.send_media_group(
            chat_id=CHAT_ID,
            media=[
                {"type": "photo", "media": page_1_url},
                {"type": "photo", "media": page_2_url}
            ],
            caption=f'ورد اليوم - الصفحات {state.quran_page_number} و {state.quran_page_number + 1}'
        )
        logging.info(f"Sent Quran pages {state.quran_page_number} and {state.quran_page_number + 1}")
        new_page_number = state.quran_page_number + 2
        if new_page_number > 604:
            new_page_number = 1
        update_bot_state(quran_page_number=new_page_number)
    except Exception as e:
        logging.error(f"Error sending Quran pages: {str(e)}")

def send_athkar(time_of_day):
    state = get_bot_state()
    athkar_image_url = f"{ATHKAR_URL}/أذكار_{'الصباح' if time_of_day == 'morning' else 'المساء'}.jpg"
    try:
        send_image(athkar_image_url)
        logging.info(f"Sent {time_of_day} Athkar")
        update_bot_state(last_athkar_type=time_of_day)
    except Exception as e:
        logging.error(f"Error sending {time_of_day} Athkar: {str(e)}")

def schedule_daily_tasks():
    scheduler = BlockingScheduler(timezone=CAIRO_TZ)
    
    def schedule_tasks():
        prayer_times = get_prayer_times()
        if not prayer_times:
            logging.error("Failed to fetch prayer times. Using default times.")
            prayer_times = {'Fajr': '05:00', 'Asr': '15:00'}

        fajr_time = datetime.strptime(prayer_times['Fajr'], '%H:%M').time()
        asr_time = datetime.strptime(prayer_times['Asr'], '%H:%M').time()

        morning_athkar_time = (datetime.combine(datetime.now(CAIRO_TZ).date(), fajr_time) + timedelta(minutes=30)).time()
        night_athkar_time = (datetime.combine(datetime.now(CAIRO_TZ).date(), asr_time) + timedelta(minutes=30)).time()
        quran_time = (datetime.combine(datetime.now(CAIRO_TZ).date(), night_athkar_time) + timedelta(minutes=15)).time()

        scheduler.add_job(send_athkar, 'cron', args=['morning'], hour=morning_athkar_time.hour, minute=morning_athkar_time.minute)
        scheduler.add_job(send_athkar, 'cron', args=['night'], hour=night_athkar_time.hour, minute=night_athkar_time.minute)
        scheduler.add_job(send_quran_pages, 'cron', hour=quran_time.hour, minute=quran_time.minute)

        logging.info(f"Scheduled tasks for {datetime.now(CAIRO_TZ).date()}:")
        logging.info(f"Morning Athkar: {morning_athkar_time.strftime('%H:%M')}")
        logging.info(f"Night Athkar: {night_athkar_time.strftime('%H:%M')}")
        logging.info(f"Quran pages: {quran_time.strftime('%H:%M')}")

    scheduler.add_job(schedule_tasks, 'cron', hour=0, minute=0)  # Run daily at midnight
    scheduler.add_job(schedule_tasks, 'date')  # Run once immediately on startup

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass

def main():
    if not initialize_database():
        logging.error("Failed to initialize database. Exiting.")
        return

    logging.info("Starting the bot...")
    schedule_daily_tasks()

if __name__ == '__main__':
    main()