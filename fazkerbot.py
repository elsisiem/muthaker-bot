import os
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytz
import requests
from telegram.ext import ApplicationBuilder, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up bot and chat details
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

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
engine = sa.create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)

class BotState(Base):
    __tablename__ = 'bot_state'
    id = sa.Column(sa.Integer, primary_key=True)
    quran_page_number = sa.Column(sa.Integer, default=1)
    last_athkar_type = sa.Column(sa.String, default='night')

Base.metadata.create_all(engine)

def get_bot_state():
    with Session() as session:
        state = session.query(BotState).first()
        if not state:
            state = BotState()
            session.add(state)
            session.commit()
        return state

def update_bot_state(quran_page_number=None, last_athkar_type=None):
    with Session() as session:
        state = session.query(BotState).first()
        if quran_page_number is not None:
            state.quran_page_number = quran_page_number
        if last_athkar_type is not None:
            state.last_athkar_type = last_athkar_type
        session.commit()

def get_prayer_times():
    try:
        response = requests.get(API_URL, params=API_PARAMS)
        response.raise_for_status()
        data = response.json()
        return data['data']['timings']
    except requests.RequestException as e:
        logging.error(f"Error fetching prayer times: {str(e)}")
        return None

def get_next_occurrence(time_str, base_time=None):
    if base_time is None:
        base_time = datetime.now(CAIRO_TZ)
    time = datetime.strptime(time_str, '%H:%M').time()
    next_occurrence = base_time.replace(hour=time.hour, minute=time.minute, second=0, microsecond=0)
    if next_occurrence <= base_time:
        next_occurrence += timedelta(days=1)
    return next_occurrence

async def send_image(context, image_url, caption=""):
    try:
        await context.bot.send_photo(chat_id=CHAT_ID, photo=image_url, caption=caption)
        logging.info(f"Sent image: {image_url}")
    except Exception as e:
        logging.error(f"Error sending image {image_url}: {str(e)}")

async def send_quran_pages(context):
    state = get_bot_state()
    page_1_url = f"{QURAN_PAGES_URL}/photo_{state.quran_page_number}.jpg"
    page_2_url = f"{QURAN_PAGES_URL}/photo_{state.quran_page_number + 1}.jpg"
    try:
        await context.bot.send_media_group(
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

async def send_athkar(context, time_of_day):
    state = get_bot_state()
    athkar_image_url = f"{ATHKAR_URL}/أذكار_{'الصباح' if time_of_day == 'morning' else 'المساء'}.jpg"
    try:
        message = await context.bot.send_photo(chat_id=CHAT_ID, photo=athkar_image_url)
        logging.info(f"Sent {time_of_day} Athkar")
        
        # Delete previous Athkar message
        if state.last_athkar_type != time_of_day:
            job = context.job
            if 'last_message_id' in job.data:
                try:
                    await context.bot.delete_message(chat_id=CHAT_ID, message_id=job.data['last_message_id'])
                    logging.info(f"Deleted previous {state.last_athkar_type} Athkar message")
                except Exception as e:
                    logging.error(f"Error deleting previous Athkar message: {str(e)}")
        
        # Update job data and bot state
        context.job.data['last_message_id'] = message.message_id
        update_bot_state(last_athkar_type=time_of_day)
    except Exception as e:
        logging.error(f"Error sending {time_of_day} Athkar: {str(e)}")

def schedule_daily_tasks(context):
    scheduler = context.job_queue
    scheduler.run_repeating(reschedule_daily_tasks, interval=timedelta(days=1), first=get_next_occurrence('00:00'))

async def reschedule_daily_tasks(context):
    scheduler = context.job_queue
    scheduler.clear()
    
    prayer_times = get_prayer_times()
    if not prayer_times:
        logging.error("Failed to fetch prayer times. Using default times.")
        prayer_times = {'Fajr': '05:00', 'Asr': '15:00'}

    fajr_time = get_next_occurrence(prayer_times['Fajr'])
    asr_time = get_next_occurrence(prayer_times['Asr'])

    morning_athkar_time = fajr_time + timedelta(minutes=30)
    night_athkar_time = asr_time + timedelta(minutes=30)
    quran_time = night_athkar_time + timedelta(minutes=15)

    scheduler.run_once(lambda ctx: send_athkar(ctx, 'morning'), morning_athkar_time)
    scheduler.run_once(lambda ctx: send_athkar(ctx, 'night'), night_athkar_time)
    scheduler.run_once(send_quran_pages, quran_time)

    logging.info(f"Scheduled tasks for {datetime.now(CAIRO_TZ).date()}:")
    logging.info(f"Morning Athkar: {morning_athkar_time.strftime('%H:%M')}")
    logging.info(f"Night Athkar: {night_athkar_time.strftime('%H:%M')}")
    logging.info(f"Quran pages: {quran_time.strftime('%H:%M')}")

async def start(update, context):
    await update.message.reply_text("Bot is running. Use /schedule to manually trigger scheduling.")

async def manual_schedule(update, context):
    await reschedule_daily_tasks(context)
    await update.message.reply_text("Daily tasks have been manually scheduled.")

def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("schedule", manual_schedule))
    
    job_queue = application.job_queue
    job_queue.run_once(schedule_daily_tasks, when=1)
    
    application.run_polling()

if __name__ == '__main__':
    main()