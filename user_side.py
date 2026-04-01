"""
Interactive user preferences bot for personalized Athkar reminders.
Users select which Athkar they want and how often to receive them.
Sends personalized DM reminders based on their preferences.
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
    ContextTypes,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, DateTime, select, Text
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
    """User preferences model for Athkar reminders"""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    first_name = Column(String, nullable=True)
    selected_athkar = Column(Text, nullable=True)  # JSON: ["hizb", "baaqiyat", ...]
    frequency = Column(String, default="2x_daily")  # "1x_daily", "2x_daily", "3x_daily", or "custom:HH:MM,HH:MM"
    timezone = Column(String, default="Africa/Cairo")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ============================================================================
# ATHKAR DEFINITIONS
# ============================================================================

ATHKAR_OPTIONS = [
    {
        "id": "hizb",
        "ar": "🛡️ منبة الحرز",
        "en": "Al-Hizb",
        "text_ar": "لا اله إلا اللّٰه وحده لا شريك له ، له الملك وله الحمد",
    },
    {
        "id": "baaqiyat",
        "ar": "✨ الباقيات الصالحات",
        "en": "Eternal Good Works",
        "text_ar": "سبحان اللّٰه الحمد لله لا إله إلا اللّٰه اللّٰه أكبر",
    },
    {
        "id": "hawqala",
        "ar": "🤲 الحوقلة",
        "en": "Hawqalah",
        "text_ar": "لا حول ولا قوة إلا بالله العلي العظيم",
    },
    {
        "id": "tasbih",
        "ar": "📿 التسبيح",
        "en": "Tasbih",
        "text_ar": "سبحان اللّٰه وبحمده سبحان اللّٰه العظيم",
    },
    {
        "id": "dhun_noon",
        "ar": "🌙 دعاء ذي النون",
        "en": "Dua of Dhun-Nun",
        "text_ar": "لا إله إلا انت سبحانك إني كنت من الظالمين",
    },
    {
        "id": "tahlil",
        "ar": "📣 التهليل",
        "en": "Tahlil",
        "text_ar": "قال النبي : أفضل الذكر لا إله إلا اللّٰه",
    },
    {
        "id": "tahmid",
        "ar": "🙏 الحمد",
        "en": "Tahmid",
        "text_ar": "أفضل الدعاء الحمد لله",
    },
    {
        "id": "istighfar",
        "ar": "🔄 الاستغفار",
        "en": "Istighfar",
        "text_ar": "استغفر اللّٰه العظيم وأتوب إليه",
    },
    {
        "id": "salat",
        "ar": "💌 الصلاة على النبي",
        "en": "Salat on the Prophet",
        "text_ar": "اللهم صل وسلم وبارك على محمد",
    },
]

FREQUENCY_OPTIONS = {
    "1x_daily": {"ar": "مرة واحدة يومياً", "en": "Once daily", "times": ["09:00"]},
    "2x_daily": {"ar": "مرتين يومياً", "en": "Twice daily", "times": ["09:00", "18:00"]},
    "3x_daily": {"ar": "ثلاث مرات يومياً", "en": "Three times daily", "times": ["09:00", "13:00", "18:00"]},
}

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

async def init_db():
    """Initialize database tables"""
    logger.info("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables ready")

async def get_user_prefs(telegram_id: str) -> UserPreferences | None:
    """Get user preferences from database"""
    async with async_session() as session:
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.telegram_id == str(telegram_id))
        )
        return result.scalars().first()

async def save_user_prefs(telegram_id: str, first_name: str, selected_athkar: list, frequency: str):
    """Save or update user preferences"""
    async with async_session() as session:
        user = await session.execute(
            select(UserPreferences).where(UserPreferences.telegram_id == str(telegram_id))
        )
        user_prefs = user.scalars().first()

        if user_prefs:
            user_prefs.selected_athkar = json.dumps(selected_athkar)
            user_prefs.frequency = frequency
            user_prefs.updated_at = datetime.utcnow()
        else:
            user_prefs = UserPreferences(
                telegram_id=str(telegram_id),
                first_name=first_name,
                selected_athkar=json.dumps(selected_athkar),
                frequency=frequency,
            )
            session.add(user_prefs)

        await session.commit()
        logger.info(f"✅ Saved preferences for user {telegram_id}: {len(selected_athkar)} athkar selected, frequency: {frequency}")

# ============================================================================
# TELEGRAM HANDLERS
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show welcome message and Athkar selection"""
    user = update.effective_user
    telegram_id = str(user.id)

    logger.info(f"👤 User {telegram_id} ({user.first_name}) started the bot")

    # Check if user already has preferences
    user_prefs = await get_user_prefs(telegram_id)

    if user_prefs:
        welcome_text = f"👋 أهلاً وسهلاً {user.first_name}!\n\nأنت مسجل بالفعل. اختر أحد الخيارات:"
        buttons = [
            [InlineKeyboardButton("🔄 تعديل اختيارات الأذكار", callback_data="edit_athkar")],
            [InlineKeyboardButton("⏰ تغيير التكرار", callback_data="edit_frequency")],
            [InlineKeyboardButton("📋 عرض اختيارتي", callback_data="show_prefs")],
        ]
    else:
        welcome_text = f"""
👋 أهلاً وسهلاً {user.first_name}!

أنا بوت ذاكر الأذكار. سأساعدك على اختيار الأذكار التي تفضلها والمرات التي تريد تلقي التذكيرات فيها.

انقر أدناه للبدء:
"""
        buttons = [
            [InlineKeyboardButton("🎯 اختيار الأذكار", callback_data="select_athkar")],
        ]

    keyboard = InlineKeyboardMarkup(buttons)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, reply_markup=keyboard)

async def select_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Athkar selection menu"""
    query = update.callback_query
    await query.answer()

    text = "🎯 اختر الأذكار التي تريد تلقي التذكيرات عنها:\n\n(يمكنك اختيار أكثر من واحد)"

    buttons = []
    for athkar in ATHKAR_OPTIONS:
        buttons.append([InlineKeyboardButton(athkar["ar"], callback_data=f"toggle_athkar_{athkar['id']}")])

    buttons.append([InlineKeyboardButton("✅ تم - اختيار التكرار", callback_data="choose_frequency")])
    buttons.append([InlineKeyboardButton("« رجوع", callback_data="start")])

    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text=text, reply_markup=keyboard)

async def toggle_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle Athkar selection"""
    query = update.callback_query
    await query.answer()

    athkar_id = query.data.replace("toggle_athkar_", "")
    user_id = str(query.from_user.id)

    # Get current selections from context or database
    if "selected_athkar" not in context.user_data:
        user_prefs = await get_user_prefs(user_id)
        if user_prefs and user_prefs.selected_athkar:
            context.user_data["selected_athkar"] = json.loads(user_prefs.selected_athkar)
        else:
            context.user_data["selected_athkar"] = []

    # Toggle the athkar
    if athkar_id in context.user_data["selected_athkar"]:
        context.user_data["selected_athkar"].remove(athkar_id)
    else:
        context.user_data["selected_athkar"].append(athkar_id)

    # Rebuild the menu with selections marked
    text = "🎯 اختر الأذكار التي تريد تلقي التذكيرات عنها:\n\n"

    buttons = []
    for athkar in ATHKAR_OPTIONS:
        is_selected = athkar["id"] in context.user_data["selected_athkar"]
        prefix = "✅ " if is_selected else "☐ "
        buttons.append([InlineKeyboardButton(f"{prefix}{athkar['ar']}", callback_data=f"toggle_athkar_{athkar['id']}")])

    buttons.append([InlineKeyboardButton("✅ تم - اختيار التكرار", callback_data="choose_frequency")])
    buttons.append([InlineKeyboardButton("« رجوع", callback_data="start")])

    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text=text, reply_markup=keyboard)

async def choose_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show frequency selection menu"""
    query = update.callback_query

    if "selected_athkar" not in context.user_data or not context.user_data["selected_athkar"]:
        await query.answer("❌ يرجى اختيار أذكار أولاً", show_alert=True)
        return

    await query.answer()

    text = "⏰ اختر كم مرة تريد تلقي التذكيرات:\n\n"

    buttons = []
    for freq_id, freq_data in FREQUENCY_OPTIONS.items():
        times = ", ".join(freq_data["times"])
        button_text = f"{freq_data['ar']} ({times})"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"set_freq_{freq_id}")])

    buttons.append([InlineKeyboardButton("« رجوع", callback_data="select_athkar")])

    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text=text, reply_markup=keyboard)

async def set_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the frequency and save preferences"""
    query = update.callback_query
    await query.answer()

    frequency = query.data.replace("set_freq_", "")
    user = query.from_user
    user_id = str(user.id)

    selected_athkar = context.user_data.get("selected_athkar", [])

    if not selected_athkar:
        await query.answer("❌ يرجى اختيار أذكار أولاً", show_alert=True)
        return

    # Save to database
    await save_user_prefs(user_id, user.first_name, selected_athkar, frequency)

    # Show confirmation
    athkar_names = [a["ar"] for a in ATHKAR_OPTIONS if a["id"] in selected_athkar]
    freq_data = FREQUENCY_OPTIONS[frequency]

    confirmation_text = f"""
✅ تم حفظ اختياراتك!

📋 الأذكار المختارة:
{chr(10).join(['• ' + name for name in athkar_names])}

⏰ التكرار: {freq_data['ar']}
🕐 الأوقات: {', '.join(freq_data['times'])}

سيتم إرسال التذكيرات إلى هنا مباشرة.
"""

    buttons = [
        [InlineKeyboardButton("📋 عرض اختيارتي", callback_data="show_prefs")],
        [InlineKeyboardButton("🔄 تعديل الاختيارات", callback_data="edit_athkar")],
    ]
    keyboard = InlineKeyboardMarkup(buttons)

    await query.edit_message_text(text=confirmation_text, reply_markup=keyboard)
    logger.info(f"✅ User {user_id} saved preferences")

async def edit_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit Athkar selections for existing user"""
    query = update.callback_query
    await query.answer()

    # Load current preferences
    user_id = str(query.from_user.id)
    user_prefs = await get_user_prefs(user_id)

    if user_prefs and user_prefs.selected_athkar:
        context.user_data["selected_athkar"] = json.loads(user_prefs.selected_athkar)
    else:
        context.user_data["selected_athkar"] = []

    await select_athkar(update, context)

async def show_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's current preferences"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    user_prefs = await get_user_prefs(user_id)

    if not user_prefs or not user_prefs.selected_athkar:
        text = "لم تقم بتحديد أي أذكار حتى الآن."
        buttons = [[InlineKeyboardButton("🎯 اختيار الأذكار", callback_data="select_athkar")]]
    else:
        selected_ids = json.loads(user_prefs.selected_athkar)
        athkar_names = [a["ar"] for a in ATHKAR_OPTIONS if a["id"] in selected_ids]
        freq_data = FREQUENCY_OPTIONS.get(user_prefs.frequency, FREQUENCY_OPTIONS["2x_daily"])

        text = f"""
📋 اختياراتك الحالية:

الأذكار:
{chr(10).join(['• ' + name for name in athkar_names])}

التكرار: {freq_data['ar']}
الأوقات: {', '.join(freq_data['times'])}
"""

        buttons = [
            [InlineKeyboardButton("🔄 تعديل الأذكار", callback_data="edit_athkar")],
            [InlineKeyboardButton("⏰ تغيير التكرار", callback_data="edit_frequency")],
        ]

    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text=text, reply_markup=keyboard)

async def edit_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit frequency for existing user"""
    query = update.callback_query

    user_id = str(query.from_user.id)
    user_prefs = await get_user_prefs(user_id)

    if not user_prefs or not user_prefs.selected_athkar:
        await query.answer("❌ يرجى اختيار أذكار أولاً", show_alert=True)
        return

    context.user_data["selected_athkar"] = json.loads(user_prefs.selected_athkar)
    await choose_frequency(update, context)

# ============================================================================
# WEB SERVER SETUP
# ============================================================================

async def handle_webhook(request):
    """Handle Telegram webhook requests"""
    data = await request.json()
    await application.process_update(data)
    return web.Response()

async def handle_root(request):
    """Health check endpoint"""
    return web.Response(text="User side bot is running ✅")

# ============================================================================
# BOT INITIALIZATION
# ============================================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

application = Application.builder().token(TOKEN).build()

# Add handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(select_athkar, pattern="^select_athkar$"))
application.add_handler(CallbackQueryHandler(toggle_athkar, pattern="^toggle_athkar_"))
application.add_handler(CallbackQueryHandler(choose_frequency, pattern="^choose_frequency$"))
application.add_handler(CallbackQueryHandler(set_frequency, pattern="^set_freq_"))
application.add_handler(CallbackQueryHandler(edit_athkar, pattern="^edit_athkar$"))
application.add_handler(CallbackQueryHandler(edit_frequency, pattern="^edit_frequency$"))
application.add_handler(CallbackQueryHandler(show_prefs, pattern="^show_prefs$"))
application.add_handler(CallbackQueryHandler(start, pattern="^start$"))

# Web app for webhook
web_app = web.Application()
web_app.router.add_get("/", handle_root)
web_app.router.add_post("/webhook", handle_webhook)

logger.info("✅ User side bot initialized")
