"""
This module implements the interactive configuration for the bot "مذكر".
Users can configure Athkar reminders, Quran Wird settings, Sleep-Time supplications,
and city/timezone for prayer-based scheduling. User data is stored in a PostgreSQL
database ("postgresql-cylindrical-57129") using SQLAlchemy.
This module works alongside fazkerbot.py.
"""

import os
import logging
import asyncio
from datetime import datetime
import json
import aiohttp

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, text

from aiohttp import web

from user_bot.language import language_choice
from user_bot.athkar import athkar_config_entry, athkar_receive, athkar_freq_choice, athkar_freq_receive, ATHKAR_LIST_AR, ATHKAR_LIST_EN
from user_bot.quran import quran_config_entry, quran_config_choice, quran_config_receive
from user_bot.sleep import sleep_config_entry, sleep_config_receive
from user_bot.city import city_config_entry, city_config_receive

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DATABASE_URL - Heroku automatically sets this when PostgreSQL addon is attached
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Convert postgres:// to postgresql+asyncpg:// for SQLAlchemy async
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    logger.info("Using DATABASE_URL from environment (converted for asyncpg)")
elif DATABASE_URL:
    logger.info("Using DATABASE_URL from environment")
else:
    # Fallback to direct connection string (your provided credentials)
    DATABASE_URL = "postgresql+asyncpg://u3cmevgl2g6c6j:paf6377466881a2403b02f14624b98bf68879ed773b2ccf111d397fe536a381b9@c9pv5s2sq0i76o.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d1f1puvchrt773"
    logger.warning("Using fallback database connection string")

engine = create_async_engine(DATABASE_URL, echo=True)
Base = declarative_base()
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Define a user preferences model.
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    city = Column(String)
    country = Column(String)
    timezone = Column(String)
    language = Column(String, default="ar")  # Add language field
    athkar_preferences = Column(String)  # JSON string representing selected athkar and frequency mode
    quran_settings = Column(String)       # JSON string for Quran settings (mode, start, quantity)

# Conversation states
LANGUAGE, MAIN_MENU, ATHKAR, ATHKAR_FREQ, QURAN_CHOICE, QURAN_DETAILS, SLEEP_TIME, CITY_INFO = range(8)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the configuration conversation."""
    logger.info(f"Start command received from user {update.effective_user.id}")
    try:
        user_id = str(update.effective_user.id)
        # Ensure the user exists in database (create or fetch)
        async with async_session() as session:
            result = await session.execute(
                text("SELECT id FROM users WHERE telegram_id = :tid"), {"tid": user_id}
            )
            user = result.first()
            if not user:
                new_user = User(telegram_id=user_id)
                session.add(new_user)
                await session.commit()
                logger.info(f"Created new user: {user_id}")
            else:
                logger.info(f"Existing user: {user_id}")
                
        # Present language options
        keyboard = [
            [InlineKeyboardButton("العربية", callback_data="lang_ar")],
            [InlineKeyboardButton("English", callback_data="lang_en")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "اختر اللغة / Choose language:", 
            reply_markup=reply_markup
        )
        logger.info("Sent language selection message")
        return LANGUAGE
    except Exception as e:
        logger.exception("Error in start command")
        await update.message.reply_text("An error occurred. Please try again with /start")
        return ConversationHandler.END

# --- Quran Wird Configuration Flow ---
async def quran_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Quran Wird configuration."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Fixed Pages per Day", callback_data="quran_pages")],
        [InlineKeyboardButton("Specific Juz’ (1-30)", callback_data="quran_juz")],
        [InlineKeyboardButton("Specific Surah", callback_data="quran_surah")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Choose your Quran recitation mode:", reply_markup=reply_markup)
    return QURAN_CHOICE

async def quran_config_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the Quran Wird choice and ask for details."""
    query = update.callback_query
    await query.answer()
    choice = query.data  # "quran_pages", "quran_juz" or "quran_surah"
    context.user_data["quran_mode"] = choice
    if choice == "quran_pages":
        await query.edit_message_text("Enter the number of pages you want to recite per day (e.g., 2):")
    elif choice == "quran_juz":
        await query.edit_message_text("Enter the Juz’ number (1-30):")
    else:
        await query.edit_message_text("Enter the Surah name or number:")
    return QURAN_DETAILS

async def quran_config_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive Quran Wird configuration details and save to DB."""
    detail = update.message.text.strip()
    context.user_data["quran_detail"] = detail
    import json
    quran_settings = {
        "mode": context.user_data.get("quran_mode"),
        "detail": detail,
        "last_recited": None
    }
    user_id = str(update.effective_user.id)
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET quran_settings = :settings WHERE telegram_id = :tid"),
            {"settings": json.dumps(quran_settings), "tid": user_id}
        )
        await session.commit()
    await update.message.reply_text("Quran Wird settings saved successfully.")
    return ConversationHandler.END

# --- Sleep-Time Supplications Configuration Flow ---
async def sleep_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry for sleep-time supplications: ask user for typical sleep time."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please enter your typical sleep time in HH:MM (24-hour format):")
    return SLEEP_TIME

async def sleep_config_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive sleep time and update user configuration."""
    sleep_time = update.message.text.strip()
    try:
        datetime.strptime(sleep_time, "%H:%M")
    except Exception:
        await update.message.reply_text("Invalid format. Please enter time as HH:MM (e.g., 23:30).")
        return SLEEP_TIME
    user_id = str(update.effective_user.id)
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET athkar_preferences = COALESCE(athkar_preferences, '{}') || :sleep_time::text WHERE telegram_id = :tid"),
            {"sleep_time": f'{{"sleep_time": "{sleep_time}"}}', "tid": user_id}
        )
        await session.commit()
    await update.message.reply_text("Sleep-time supplications configuration saved.")
    return ConversationHandler.END

# --- City/Timezone Configuration Flow ---
async def city_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry for City/Timezone configuration: ask user for city and country."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send your city and country in the format:\nCity, Country\n(e.g., Cairo, Egypt)")
    return CITY_INFO

async def city_config_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive city info, determine timezone using prayer API, and save to DB."""
    text = update.message.text.strip()
    if "," not in text:
        await update.message.reply_text("Invalid format. Please use: City, Country")
        return CITY_INFO
    city, country = [t.strip() for t in text.split(",", 1)]
    import aiohttp
    API_URL = "https://api.aladhan.com/v1/timingsByCity"
    params = {'city': city, 'country': country, 'method': 3}
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=params) as response:
            data = await response.json()
            timezone = data.get("data", {}).get("meta", {}).get("timezone", "Africa/Cairo")
    user_id = str(update.effective_user.id)
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET city = :city, country = :country, timezone = :tz WHERE telegram_id = :tid"),
            {"city": city, "country": country, "tz": timezone, "tid": user_id}
        )
        await session.commit()
    await update.message.reply_text(f"Configuration saved. Your timezone is set to {timezone}.")
    return ConversationHandler.END

async def get_user_language(user_id: str) -> str:
    """Get user's language from database."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT language FROM users WHERE telegram_id = :tid"), {"tid": user_id}
        )
        user = result.first()
        return user.language if user and user.language else "ar"

# --- Main Conversation Handler Setup ---
def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANGUAGE: [CallbackQueryHandler(language_choice, pattern="^lang_")],
            MAIN_MENU: [
                CallbackQueryHandler(athkar_config_entry, pattern="^config_athkar$"),
                CallbackQueryHandler(quran_config_entry, pattern="^config_quran$"),
                CallbackQueryHandler(sleep_config_entry, pattern="^config_sleep$"),
                CallbackQueryHandler(city_config_entry, pattern="^config_city$"),
            ],
            ATHKAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, athkar_receive)],
            ATHKAR_FREQ: [
                CallbackQueryHandler(athkar_freq_choice, pattern="^freq_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, athkar_freq_receive)
            ],
            QURAN_CHOICE: [CallbackQueryHandler(quran_config_choice, pattern="^quran_")],
            QURAN_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, quran_config_receive)],
            SLEEP_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, sleep_config_receive)],
            CITY_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, city_config_receive)],
        },
        fallbacks=[CommandHandler("cancel", lambda update, context: update.message.reply_text("Configuration cancelled."))]
    )

# Create conversation handler but don't add it yet
conversation_handler = get_conversation_handler()

# Instead of having async with at module level, create an init function
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Ensure the language column exists
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'ar'"))

# Add async initialization function
async def init_application():
    """Initialize the application and database"""
    logger.info("Initializing user_side application...")
    try:
        await application.initialize()
        await init_db()
        
        # Add command handlers first
        application.add_handler(CommandHandler("start", start))
        
        # Then add conversation and callback handlers
        application.add_handler(conversation_handler)
        application.add_handler(CallbackQueryHandler(
            language_choice,
            pattern="^lang_"
        ))
        
        # Config handlers are now in the conversation
        
        logger.info("All handlers registered successfully")
    except Exception as e:
        logger.exception("Error in init_application")
        raise

# Define the webhook route
async def webhook_handler(request):
    update_data = await request.json()
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)
    return web.Response(text="OK")

# Initialize the application for webhook updates
application = Application.builder().token(os.environ['TELEGRAM_BOT_TOKEN']).build()

# Add webhook route to the web app
web_app = web.Application()
web_app.router.add_post("/webhook", webhook_handler)

# Add startup handler to initialize the Telegram application
async def startup_handler(app):
    await init_application()

web_app.on_startup.append(startup_handler)