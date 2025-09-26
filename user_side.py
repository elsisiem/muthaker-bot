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
LANGUAGE, ATHKAR, ATHKAR_FREQ, QURAN_CHOICE, QURAN_DETAILS, SLEEP_TIME, CITY_INFO = range(7)

# Predefined Athkar list
ATHKAR_LIST_AR = [
    "تهليل (La ilaha illa Allah)",
    "تسبيح (SubhanAllah)",
    "تحميد (Alhamdulillah)",
    "تكبير (Allahu Akbar)",
    "حوقلة (La hawla wa la quwwata illa billah)",
    "الصلاة على النبي (Salawat)",
    "دعاء ذي النون (La ilaha illa anta subhanaka inni kuntu min al-zalimin)",
    "سبحان الله وبحمده، سبحان الله العظيم",
]

ATHKAR_LIST_EN = [
    "Tahleel (La ilaha illa Allah)",
    "Tasbeeh (SubhanAllah)",
    "Tahmeed (Alhamdulillah)",
    "Takbeer (Allahu Akbar)",
    "Hawqala (La hawla wa la quwwata illa billah)",
    "Salawat (Prayers upon the Prophet)",
    "Dua of Dhun-Noon (La ilaha illa anta subhanaka inni kuntu min al-zalimin)",
    "Subhan Allah wa bihamdihi, subhan Allah al-adheem",
]

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

async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection."""
    query = update.callback_query
    await query.answer()
    choice = query.data  # "lang_ar" or "lang_en"
    lang = "ar" if choice == "lang_ar" else "en"
    user_id = str(update.effective_user.id)
    
    # Save language to database
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET language = :lang WHERE telegram_id = :tid"),
            {"lang": lang, "tid": user_id}
        )
        await session.commit()
    
    if lang == "ar":
        message = "مرحبا بك في مذكر! اختر خيار التكوين:"
    else:
        message = "Welcome to Muthaker! Choose a configuration option:"
    
    # Present configuration options
    keyboard = [
        [InlineKeyboardButton("تكوين تذكير الأذكار" if lang == "ar" else "Configure Athkar Reminders", callback_data="config_athkar")],
        [InlineKeyboardButton("تكوين ورد القرآن" if lang == "ar" else "Configure Quran Wird", callback_data="config_quran")],
        [InlineKeyboardButton("تعيين أدعية وقت النوم" if lang == "ar" else "Set Sleep-Time Supplications", callback_data="config_sleep")],
        [InlineKeyboardButton("تعيين المدينة/المنطقة الزمنية" if lang == "ar" else "Set City/Timezone", callback_data="config_city")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=message, reply_markup=reply_markup)
    return ConversationHandler.END

# --- Athkar Configuration Flow ---
async def athkar_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Athkar configuration."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    lang = await get_user_language(user_id)
    athkar_list = ATHKAR_LIST_AR if lang == "ar" else ATHKAR_LIST_EN
    context.user_data["athkar_list"] = athkar_list
    if lang == "ar":
        text = "اختر الأذكار التي تريد التذكير بها:\n" + "\n".join(f"{i+1}: {item}" for i, item in enumerate(athkar_list))
        text += "\n\nيرجى الرد بأرقام الاختيارات مفصولة بفواصل (مثال: 1,3,5)."
    else:
        text = "Select the Athkar you want reminders for:\n" + "\n".join(f"{i+1}: {item}" for i, item in enumerate(athkar_list))
        text += "\n\nPlease reply with the numbers of the selections separated by commas (e.g. 1,3,5)."
    await query.edit_message_text(text=text)
    return ATHKAR

async def athkar_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive user's Athkar selections."""
    athkar_list = context.user_data.get("athkar_list", ATHKAR_LIST_AR)
    selections = update.message.text.split(",")
    try:
        indices = [int(s.strip()) for s in selections if s.strip().isdigit() and 1 <= int(s.strip()) <= len(athkar_list)]
    except Exception:
        lang = await get_user_language(str(update.effective_user.id))
        error_msg = "إدخال غير صحيح. يرجى إدخال أرقام مفصولة بفواصل." if lang == "ar" else "Invalid input. Please enter numbers separated by commas."
        await update.message.reply_text(error_msg)
        return ATHKAR
    chosen = [athkar_list[i-1] for i in indices]
    context.user_data["athkar"] = chosen
    lang = await get_user_language(str(update.effective_user.id))
    if lang == "ar":
        keyboard = [
            [InlineKeyboardButton("عدد ثابت يوميًا", callback_data="freq_fixed")],
            [InlineKeyboardButton("فترة زمنية (مثل كل ساعتين)", callback_data="freq_interval")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("اختر وضع التكرار لتذكيرات الأذكار:", reply_markup=reply_markup)
    else:
        keyboard = [
            [InlineKeyboardButton("Fixed Number per Day", callback_data="freq_fixed")],
            [InlineKeyboardButton("Time Interval (e.g. every 2 hours)", callback_data="freq_interval")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose the frequency mode for Athkar reminders:", reply_markup=reply_markup)
    return ATHKAR_FREQ

async def athkar_freq_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process frequency choice for Athkar reminders."""
    query = update.callback_query
    await query.answer()
    mode = query.data  # "freq_fixed" or "freq_interval"
    context.user_data["athkar_freq_mode"] = mode
    lang = await get_user_language(str(update.effective_user.id))
    if mode == "freq_fixed":
        msg = "أدخل العدد الثابت من التذكيرات يوميًا (مثال: 10):" if lang == "ar" else "Enter the fixed number of reminders per day (e.g., 10):"
    else:
        msg = "أدخل الفترة الزمنية بالساعات (مثال: 2):" if lang == "ar" else "Enter the time interval in hours (e.g., 2):"
    await query.edit_message_text(msg)
    return ATHKAR_FREQ

async def athkar_freq_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the frequency value for Athkar reminders."""
    try:
        value = int(update.message.text.strip())
    except Exception:
        lang = await get_user_language(str(update.effective_user.id))
        error_msg = "يرجى إدخال رقم صحيح." if lang == "ar" else "Please enter a valid number."
        await update.message.reply_text(error_msg)
        return ATHKAR_FREQ
    context.user_data["athkar_freq_value"] = value
    import json
    athkar_prefs = {
        "selected": context.user_data.get("athkar", []),
        "mode": context.user_data.get("athkar_freq_mode"),
        "value": value
    }
    user_id = str(update.effective_user.id)
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET athkar_preferences = :prefs WHERE telegram_id = :tid"),
            {"prefs": json.dumps(athkar_prefs), "tid": user_id}
        )
        await session.commit()
    lang = await get_user_language(user_id)
    success_msg = "تم حفظ تفضيلات الأذكار بنجاح." if lang == "ar" else "Athkar preferences saved successfully."
    await update.message.reply_text(success_msg)
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
        application.add_handler(CallbackQueryHandler(
            athkar_config_entry,
            pattern="^config_athkar$"
        ))
        application.add_handler(CallbackQueryHandler(
            quran_config_entry,
            pattern="^config_quran$"
        ))
        application.add_handler(CallbackQueryHandler(
            sleep_config_entry,
            pattern="^config_sleep$"
        ))
        application.add_handler(CallbackQueryHandler(
            city_config_entry,
            pattern="^config_city$"
        ))
        
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