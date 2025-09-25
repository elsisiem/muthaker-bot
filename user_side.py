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

from aiohttp import web

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from user_bot.language import language_choice
from user_bot.athkar import athkar_config_entry, athkar_receive, athkar_freq_choice, athkar_freq_receive
from user_bot.quran import quran_config_entry, quran_config_choice, quran_config_receive
from user_bot.sleep import sleep_config_entry, sleep_config_receive
from user_bot.city import city_config_entry, city_config_receive

from db import (
    engine,
    Base,
    async_session,
    User,
    LANGUAGE, MAIN_MENU, ATHKAR, ATHKAR_FREQ, QURAN_CHOICE, QURAN_DETAILS, SLEEP_TIME, CITY_INFO,
    get_user_language,
    init_db
)

from sqlalchemy import text
from fazkerbot import scheduler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the scheduler (imported from fazkerbot)

# Predefined Athkar list imported from athkar.py

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

async def send_athkar_reminder(user_id: str, athkar_text: str):
    """Send Athkar reminder to user."""
    try:
        lang = await get_user_language(user_id)
        msg = f"تذكير بالذكر: {athkar_text}" if lang == "ar" else f"Athkar reminder: {athkar_text}"
        await application.bot.send_message(chat_id=user_id, text=msg)
        logger.info(f"Sent Athkar reminder to {user_id}")
    except Exception as e:
        logger.exception(f"Error sending Athkar reminder to {user_id}")

async def schedule_user_athkar():
    """Schedule Athkar reminders for all users."""
    try:
        async with async_session() as session:
            result = await session.execute(text("SELECT telegram_id, athkar_preferences FROM users WHERE athkar_preferences IS NOT NULL"))
            users = result.fetchall()
        for user in users:
            user_id = user[0]
            prefs = json.loads(user[1])
            selected = prefs.get("selected", [])
            mode = prefs.get("mode")
            value = prefs.get("value")
            if not selected:
                continue
            if mode == "freq_interval":
                # Send the first athkar every value minutes
                scheduler.add_job(send_athkar_reminder, 'interval', minutes=value, args=[user_id, selected[0]], id=f"athkar_{user_id}", replace_existing=True)
    except Exception as e:
        logger.exception("Error in schedule_user_athkar")

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
async def init_application():
    """Initialize the application and database"""
    logger.info("Initializing user_side application...")
    try:
        await application.initialize()
        await init_db()
        await schedule_user_athkar()

        # Start scheduler
        scheduler.start()
        logger.info("User reminder scheduler started")

        # Schedule user Athkar reminders
        await schedule_user_athkar()

        # Add command handlers first
        application.add_handler(CommandHandler("start", start))
        
        # Then add conversation and callback handlers
        application.add_handler(conversation_handler)
        
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