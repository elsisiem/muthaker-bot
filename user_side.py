"""
Interactive user preferences bot for Muthaker.
Users select Athkar reminders, frequency, and timezone.
Sends personalized reminders via DM based on their preferences.
"""

import os
import logging
import asyncio
import json
from datetime import datetime, timedelta
import pytz

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, User as TgUser
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
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, DateTime, select
from sqlalchemy.orm import declarative_base
from aiohttp import web

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)

# ============================================================================
# DATABASE SETUP
# ============================================================================

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class UserPreferences(Base):
    """User preferences model"""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    first_name = Column(String, nullable=True)
    selected_athkar = Column(String, nullable=True)  # JSON: ["Hizb", "Tasbih", ...]
    frequency = Column(String, default="2x_daily")  # "1x_daily", "2x_daily", "3x_daily", "custom:{n}"
    timezone = Column(String, default="Africa/Cairo")
    language = Column(String, default="ar")  # "ar" or "en"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ============================================================================
# ATHKAR DEFINITIONS
# ============================================================================

ATHKAR_OPTIONS = [
    {
        "id": "hizb",
        "ar": "منبة الحرز",
        "en": "Al-Hizb",
        "text_ar": "لا اله إلا اللّٰه وحده لا شريك له ، له الملك وله الحمد",
        "emoji": "🛡️"
    },
    {
        "id": "baaqiyat",
        "ar": "الباقيات الصالحات",
        "en": "Eternal Good Works",
        "text_ar": "سبحان اللّٰه الحمد لله لا إله إلا اللّٰه اللّٰه أكبر",
        "emoji": "✨"
    },
    {
        "id": "hawqala",
        "ar": "الحوقلة",
        "en": "Hawqalah",
        "text_ar": "لا حول ولا قوة إلا بالله العلي العظيم",
        "emoji": "🤲"
    },
    {
        "id": "tasbih",
        "ar": "التسبيح",
        "en": "Tasbih",
        "text_ar": "سبحان اللّٰه وبحمده سبحان اللّٰه العظيم",
        "emoji": "📿"
    },
    {
        "id": "dhun_noon",
        "ar": "دعاء ذي النون",
        "en": "Dua Dhun-Noon",
        "text_ar": "لا إله إلا انت سبحانك إني كنت من الظالمين",
        "emoji": "🙏"
    },
    {
        "id": "tahleel",
        "ar": "التهليل",
        "en": "Tahleel",
        "text_ar": "لا إله إلا اللّٰه",
        "emoji": "💫"
    },
    {
        "id": "hamd",
        "ar": "الحمد",
        "en": "Praise",
        "text_ar": "الحمد لله رب العالمين",
        "emoji": "🌟"
    },
    {
        "id": "istighfar",
        "ar": "الاستغفار",
        "en": "Istighfar",
        "text_ar": "استغفر اللّٰه العظيم وأتوب إليه",
        "emoji": "💚"
    },
    {
        "id": "salah",
        "ar": "الصلاة على النبي",
        "en": "Salah upon Prophet",
        "text_ar": "اللهم صل وسلم وبارك على محمد وعلى آل محمد",
        "emoji": "💎"
    },
]

FREQUENCY_OPTIONS = [
    {"id": "1x_daily", "ar": "مرة واحدة يومياً", "en": "Once daily (morning)", "times": ["06:00"]},
    {"id": "2x_daily", "ar": "مرتان يومياً", "en": "Twice daily (morning + evening)", "times": ["06:00", "19:00"]},
    {"id": "3x_daily", "ar": "ثلاث مرات يومياً", "en": "Three times daily", "times": ["06:00", "13:00", "19:00"]},
    {"id": "custom", "ar": "مخصص (أدخل عدد المرات)", "en": "Custom (enter number of times)", "custom": True},
]

# Conversation states
(
    SELECT_ATHKAR,
    CONFIRM_ATHKAR,
    SELECT_FREQUENCY,
    SELECT_CUSTOM_FREQUENCY,
    TIMEZONE_SELECT,
    LANG_SELECT,
) = range(6)

# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

async def get_user(telegram_id: str) -> UserPreferences:
    """Get user from database"""
    async with async_session() as session:
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.telegram_id == telegram_id)
        )
        return result.scalars().first()

async def create_or_update_user(telegram_id: str, first_name: str = None, **kwargs):
    """Create or update user in database"""
    async with async_session() as session:
        user = await session.execute(
            select(UserPreferences).where(UserPreferences.telegram_id == telegram_id)
        )
        user = user.scalars().first()

        if not user:
            user = UserPreferences(telegram_id=telegram_id, first_name=first_name)
            session.add(user)

        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)

        await session.commit()
        return user

async def init_db():
    """Initialize database"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ============================================================================
# BOT HANDLERS
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start command - show welcome message"""
    user = update.effective_user
    telegram_id = str(user.id)

    # Create user in DB if not exists
    await create_or_update_user(telegram_id, user.first_name)

    logger.info(f"Start command from user {telegram_id}")

    # Welcome message
    welcome_text = """
🌙 أهلا وسهلا بك في منصة مذكر! 🌙
Ahlan wa sahlan in Muthaker Platform!

اختر اللغة من فضلك:
Please select your language:
    """

    keyboard = [
        [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
    ]

    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
    return LANG_SELECT

async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection"""
    query = update.callback_query
    await query.answer()

    telegram_id = str(update.effective_user.id)
    lang = "ar" if query.data == "lang_ar" else "en"

    # Save language
    await create_or_update_user(telegram_id, language=lang)
    context.user_data["language"] = lang

    # Show main menu
    if lang == "ar":
        menu_text = "اختر ماذا تريد أن تفعل:\n\n🎯 اختر الأذكار التي تريد تذكيرات بها"
        buttons = [
            [InlineKeyboardButton("✨ اختر الأذكار", callback_data="select_athkar")],
        ]
    else:
        menu_text = "Choose what you want to do:\n\n🎯 Select Athkar reminders"
        buttons = [
            [InlineKeyboardButton("✨ Select Athkar", callback_data="select_athkar")],
        ]

    await query.edit_message_text(menu_text, reply_markup=InlineKeyboardMarkup(buttons))
    return SELECT_ATHKAR

async def start_athkar_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start Athkar selection - show all options"""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "ar")
    telegram_id = str(update.effective_user.id)

    # Get existing selection
    user = await get_user(telegram_id)
    existing = []
    if user and user.selected_athkar:
        existing = json.loads(user.selected_athkar)

    # Build selection UI
    if lang == "ar":
        header = "🌟 اختر الأذكار التي تريد تذكيرات بها:\n\n"
        header += "👇 اضغط على الأذكار لاختيارها (يمكنك اختيار أكثر من واحد)\n\n"
        select_all_btn = "✅ اختر الكل"
        confirm_btn = "💾 تأكيد"
    else:
        header = "🌟 Select the Athkar you want reminders for:\n\n"
        header += "👇 Tap the Athkar to select them (you can select multiple)\n\n"
        select_all_btn = "✅ Select All"
        confirm_btn = "💾 Confirm"

    buttons = []

    # Add Athkar buttons
    for athkar in ATHKAR_OPTIONS:
        is_selected = athkar["id"] in existing
        emoji = "✅ " if is_selected else "👉 "
        label = athkar["ar"] if lang == "ar" else athkar["en"]
        buttons.append([InlineKeyboardButton(f"{emoji}{label}", callback_data=f"athkar_{athkar['id']}")])

    # Add select all button
    buttons.append([InlineKeyboardButton(select_all_btn, callback_data="athkar_all")])

    # Add confirm button
    buttons.append([InlineKeyboardButton(confirm_btn, callback_data="confirm_athkar")])

    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(buttons))

    # Initialize selection in context
    if "selected_athkar" not in context.user_data:
        context.user_data["selected_athkar"] = existing

    return SELECT_ATHKAR

async def toggle_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle Athkar selection"""
    query = update.callback_query
    await query.answer()

    data = query.data
    lang = context.user_data.get("language", "ar")

    selected = context.user_data.get("selected_athkar", [])

    if data == "athkar_all":
        # Select all
        selected = [athkar["id"] for athkar in ATHKAR_OPTIONS]
    else:
        # Toggle individual athkar
        athkar_id = data.replace("athkar_", "")
        if athkar_id in selected:
            selected.remove(athkar_id)
        else:
            selected.append(athkar_id)

    context.user_data["selected_athkar"] = selected

    # Rebuild UI with updated selections
    header = "🌟 اختر الأذكار:\n\n" if lang == "ar" else "🌟 Select the Athkar:\n\n"
    header += f"{'✨ تم اختيار: ' if lang == 'ar' else '✨ Selected: '}{len(selected)}\n\n"

    buttons = []

    for athkar in ATHKAR_OPTIONS:
        is_selected = athkar["id"] in selected
        emoji = "✅ " if is_selected else "👉 "
        label = athkar["ar"] if lang == "ar" else athkar["en"]
        buttons.append([InlineKeyboardButton(f"{emoji}{label}", callback_data=f"athkar_{athkar['id']}")])

    select_all_btn = "✅ اختر الكل" if lang == "ar" else "✅ Select All"
    confirm_btn = "💾 تأكيد" if lang == "ar" else "💾 Confirm"

    buttons.append([InlineKeyboardButton(select_all_btn, callback_data="athkar_all")])
    buttons.append([InlineKeyboardButton(confirm_btn, callback_data="confirm_athkar")])

    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(buttons))

    return SELECT_ATHKAR

async def confirm_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm Athkar selection and move to frequency"""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "ar")
    selected = context.user_data.get("selected_athkar", [])

    if not selected:
        error_msg = "⚠️ الرجاء اختيار أذكار واحدة على الأقل" if lang == "ar" else "⚠️ Please select at least one Athkar"
        await query.answer(error_msg, show_alert=True)
        return SELECT_ATHKAR

    # Show frequency selection
    if lang == "ar":
        header = "🔔 اختر تكرار التذكيرات:\n\n"
    else:
        header = "🔔 Select reminder frequency:\n\n"

    buttons = []
    for freq in FREQUENCY_OPTIONS:
        label = freq["ar"] if lang == "ar" else freq["en"]
        buttons.append([InlineKeyboardButton(label, callback_data=f"freq_{freq['id']}")])

    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(buttons))
    return SELECT_FREQUENCY

async def frequency_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle frequency selection"""
    query = update.callback_query
    await query.answer()

    lang = context.user_data.get("language", "ar")
    freq_id = query.data.replace("freq_", "")

    # If custom frequency, ask for number
    if freq_id == "custom":
        msg = "كم مرة تريد أن تتلقى التذكيرات يومياً؟" if lang == "ar" else "How many times per day do you want reminders?"
        await query.edit_message_text(msg)
        return SELECT_CUSTOM_FREQUENCY

    context.user_data["frequency"] = freq_id

    # Save preferences to database
    telegram_id = str(update.effective_user.id)
    selected_athkar = json.dumps(context.user_data.get("selected_athkar", []))

    await create_or_update_user(
        telegram_id,
        selected_athkar=selected_athkar,
        frequency=freq_id
    )

    # Show confirmation
    if lang == "ar":
        final_msg = "✅ تم حفظ تفضيلاتك بنجاح!\n\n🌙 ستتلقى تذكيرات الأذكار حسب اختيارك."
    else:
        final_msg = "✅ Your preferences have been saved!\n\n🌙 You'll receive Athkar reminders based on your selection."

    await query.edit_message_text(final_msg)
    return ConversationHandler.END

async def custom_frequency_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom frequency input"""
    try:
        num = int(update.message.text.strip())
        if num < 1 or num > 24:
            raise ValueError
    except ValueError:
        lang = context.user_data.get("language", "ar")
        msg = "الرجاء إدخال رقم صحيح بين 1 و 24" if lang == "ar" else "Please enter a valid number between 1 and 24"
        await update.message.reply_text(msg)
        return SELECT_CUSTOM_FREQUENCY

    lang = context.user_data.get("language", "ar")
    freq_id = f"custom_{num}"
    context.user_data["frequency"] = freq_id

    # Save to database
    telegram_id = str(update.effective_user.id)
    selected_athkar = json.dumps(context.user_data.get("selected_athkar", []))

    await create_or_update_user(
        telegram_id,
        selected_athkar=selected_athkar,
        frequency=freq_id
    )

    if lang == "ar":
        final_msg = f"✅ تم حفظ تفضيلاتك!\n\nستتلقى {num} تذكيرات يومية من الأذكار المختارة."
    else:
        final_msg = f"✅ Your preferences have been saved!\n\nYou'll receive {num} daily reminders."

    await update.message.reply_text(final_msg)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation"""
    await update.message.reply_text("تم إلغاء العملية" if context.user_data.get("language") == "ar" else "Cancelled")
    return ConversationHandler.END

# ============================================================================
# WEBHOOK HANDLER
# ============================================================================

async def webhook_handler(request):
    """Handle Telegram webhook updates"""
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, application.bot)
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
    return web.Response(text="OK")

# ============================================================================
# APPLICATION SETUP
# ============================================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

application = Application.builder().token(TOKEN).build()

# Conversation handler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        LANG_SELECT: [CallbackQueryHandler(language_selected, pattern="^lang_")],
        SELECT_ATHKAR: [
            CallbackQueryHandler(start_athkar_selection, pattern="^select_athkar$"),
            CallbackQueryHandler(toggle_athkar, pattern="^athkar_"),
            CallbackQueryHandler(confirm_athkar, pattern="^confirm_athkar$"),
        ],
        SELECT_FREQUENCY: [
            CallbackQueryHandler(frequency_selected, pattern="^freq_"),
        ],
        SELECT_CUSTOM_FREQUENCY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, custom_frequency_received),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

application.add_handler(conv_handler)

# Web app for webhook
web_app = web.Application()
web_app.router.add_post("/webhook", webhook_handler)

async def startup(app):
    """Initialize on startup"""
    logger.info("Initializing user_side bot...")
    await init_db()
    await application.initialize()
    logger.info("✅ User side bot initialized")

async def shutdown(app):
    """Cleanup on shutdown"""
    await application.shutdown()

web_app.on_startup.append(startup)
web_app.on_cleanup.append(shutdown)

# Export for use in main.py
__all__ = ["web_app", "application", "startup", "shutdown", "init_db"]
