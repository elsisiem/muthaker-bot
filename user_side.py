"""
Interactive user preferences bot for personalized Athkar reminders.
Supports Arabic/English UI, interval or daily-goal planning, and rotating/batch delivery.
"""

import os
import logging
import json
import asyncio
from datetime import datetime

import pytz
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, DateTime, select, Text, text, delete
from sqlalchemy.orm import declarative_base
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

CAIRO_TZ = pytz.timezone("Africa/Cairo")

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
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    first_name = Column(String, nullable=True)
    selected_athkar = Column(Text, nullable=True)
    frequency = Column(String, default="every_30_min")
    custom_frequency_minutes = Column(Integer, nullable=True)
    daily_goal_count = Column(Integer, nullable=True)
    delivery_mode = Column(String, default="rotating")
    language = Column(String, default="ar")
    timezone = Column(String, default="Africa/Cairo")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# CONTENT
# ============================================================================

ATHKAR_OPTIONS = [
    {
        "id": "hizb",
        "ar": "ورد الحرز",
        "en": "Hizb Wird",
        "text_ar": "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير.",
        "text_en": "There is no god but Allah alone with no partner. To Him belongs all dominion and praise.",
    },
    {
        "id": "baaqiyat",
        "ar": "الباقيات الصالحات",
        "en": "Eternal Good Deeds",
        "text_ar": "سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر.",
        "text_en": "Glory be to Allah, praise be to Allah, there is no god but Allah, and Allah is the Greatest.",
    },
    {
        "id": "hawqala",
        "ar": "الحوقلة",
        "en": "Hawqalah",
        "text_ar": "لا حول ولا قوة إلا بالله العلي العظيم.",
        "text_en": "There is no power nor might except through Allah, the Most High, the Most Great.",
    },
    {
        "id": "tasbih",
        "ar": "التسبيح",
        "en": "Tasbih",
        "text_ar": "سبحان الله وبحمده، سبحان الله العظيم.",
        "text_en": "Glory be to Allah and praise be to Him; glory be to Allah the Magnificent.",
    },
    {
        "id": "dhun_noon",
        "ar": "دعاء ذي النون",
        "en": "Dhun-Nun Supplication",
        "text_ar": "لا إله إلا أنت سبحانك إني كنت من الظالمين.",
        "text_en": "There is no god but You; glory be to You. Truly, I was among the wrongdoers.",
    },
    {
        "id": "tahlil",
        "ar": "التهليل",
        "en": "Tahlil",
        "text_ar": "أفضل الذكر: لا إله إلا الله.",
        "text_en": "The best remembrance is: There is no god but Allah.",
    },
    {
        "id": "tahmid",
        "ar": "الحمد",
        "en": "Tahmid",
        "text_ar": "أفضل الدعاء: الحمد لله.",
        "text_en": "The best supplication is: Praise be to Allah.",
    },
    {
        "id": "istighfar",
        "ar": "الاستغفار",
        "en": "Istighfar",
        "text_ar": "أستغفر الله العظيم وأتوب إليه.",
        "text_en": "I seek forgiveness from Allah the Magnificent and repent to Him.",
    },
    {
        "id": "salat",
        "ar": "الصلاة على النبي",
        "en": "Salawat on the Prophet",
        "text_ar": "اللهم صل وسلم وبارك على محمد.",
        "text_en": "O Allah, send prayers, peace, and blessings upon Muhammad.",
    },
]

INTERVAL_PRESETS = {
    "every_1_min": {"minutes": 1, "ar": "كل دقيقة", "en": "Every minute"},
    "every_5_min": {"minutes": 5, "ar": "كل 5 دقائق", "en": "Every 5 minutes"},
    "every_30_min": {"minutes": 30, "ar": "كل 30 دقيقة", "en": "Every 30 minutes"},
    "hourly": {"minutes": 60, "ar": "كل ساعة", "en": "Hourly"},
}

GOAL_PRESETS = {
    "goal_100": 100,
    "goal_200": 200,
    "goal_300": 300,
}

TEXTS = {
    "ar": {
        "start_bilingual": "مرحبًا بك في خدمة تذكيرات الأذكار.\nWelcome to Athkar Reminder Service.\n\nيرجى اختيار اللغة المفضلة / Please choose your preferred language:",
        "welcome_existing": "تم تحميل إعداداتك. يمكنك المتابعة أو التعديل.",
        "welcome_new": "ابدأ إعداداتك بالخطوات التالية.",
        "btn_ar": "العربية",
        "btn_en": "English",
        "btn_show": "عرض الإعدادات",
        "btn_edit_athkar": "تعديل الأذكار",
        "btn_edit_plan": "تعديل خطة الإرسال",
        "btn_reset": "إعادة الضبط الكامل",
        "btn_back": "رجوع",
        "btn_save": "حفظ",
        "btn_continue": "متابعة",
        "choose_athkar": "اختر الأذكار المطلوبة:",
        "btn_select_all": "تحديد الكل",
        "btn_clear_all": "إلغاء تحديد الكل",
        "choose_strategy": "اختر نوع الخطة:",
        "btn_strategy_interval": "خطة زمنية (كل X دقيقة/ساعة)",
        "btn_strategy_goal": "خطة هدف يومي (عدد مرات يوميًا)",
        "choose_interval": "اختر الفاصل الزمني:",
        "btn_custom_interval": "فاصل مخصص",
        "choose_goal": "اختر الهدف اليومي:",
        "btn_custom_goal": "هدف يومي مخصص",
        "prompt_custom_interval": "أرسل عدد الدقائق للفاصل المخصص (1 إلى 1440).",
        "prompt_custom_goal": "أرسل العدد المستهدف يوميًا (1 إلى 10000).",
        "invalid_number": "القيمة غير صحيحة. حاول مرة أخرى بالصيغة الرقمية المطلوبة.",
        "choose_mode": "اختر أسلوب الإرسال:",
        "mode_batch": "دفعة واحدة",
        "mode_rotating": "بالتناوب",
        "saved": "تم حفظ الإعدادات بنجاح.",
        "prefs_title": "الإعدادات الحالية",
        "field_lang": "اللغة",
        "field_athkar": "الأذكار",
        "field_plan": "الخطة",
        "field_mode": "أسلوب الإرسال",
        "empty_athkar": "لا توجد أذكار محددة بعد.",
        "confirm_reset": "سيتم حذف جميع إعداداتك والبدء من جديد.",
        "reset_done": "تمت إعادة الضبط الكامل. ابدأ من جديد.",
        "need_athkar": "يرجى اختيار ذكر واحد على الأقل.",
        "mode_batch_label": "دفعة واحدة",
        "mode_rotating_label": "بالتناوب",
        "lang_label_ar": "العربية",
        "lang_label_en": "English",
        "spam_warning": "تنبيه: حسب إعداداتك، متوسط الإرسال أسرع من كل 30 ثانية وقد يكون مزعجًا.",
        "save_hint": "يمكنك الحفظ الآن دون إعادة إعداد بقية الخيارات.",
    },
    "en": {
        "start_bilingual": "مرحبًا بك في خدمة تذكيرات الأذكار.\nWelcome to Athkar Reminder Service.\n\nيرجى اختيار اللغة المفضلة / Please choose your preferred language:",
        "welcome_existing": "Your settings are loaded. You can continue or edit.",
        "welcome_new": "Start your setup with the following steps.",
        "btn_ar": "Arabic",
        "btn_en": "English",
        "btn_show": "View settings",
        "btn_edit_athkar": "Edit Athkar",
        "btn_edit_plan": "Edit delivery plan",
        "btn_reset": "Reset everything",
        "btn_back": "Back",
        "btn_save": "Save",
        "btn_continue": "Continue",
        "choose_athkar": "Choose your Athkar:",
        "btn_select_all": "Select all",
        "btn_clear_all": "Clear all",
        "choose_strategy": "Choose planning type:",
        "btn_strategy_interval": "Timeframe plan (every X minutes/hours)",
        "btn_strategy_goal": "Daily target plan (N times per day)",
        "choose_interval": "Choose interval:",
        "btn_custom_interval": "Custom interval",
        "choose_goal": "Choose daily target:",
        "btn_custom_goal": "Custom daily target",
        "prompt_custom_interval": "Send interval in minutes (1 to 1440).",
        "prompt_custom_goal": "Send target count per day (1 to 10000).",
        "invalid_number": "Invalid value. Please send a numeric value in the allowed range.",
        "choose_mode": "Choose delivery mode:",
        "mode_batch": "Batch",
        "mode_rotating": "Rotating",
        "saved": "Settings saved successfully.",
        "prefs_title": "Current settings",
        "field_lang": "Language",
        "field_athkar": "Athkar",
        "field_plan": "Plan",
        "field_mode": "Delivery mode",
        "empty_athkar": "No Athkar selected yet.",
        "confirm_reset": "All your settings will be removed and setup will start over.",
        "reset_done": "Reset completed. Start again.",
        "need_athkar": "Please select at least one Athkar.",
        "mode_batch_label": "Batch",
        "mode_rotating_label": "Rotating",
        "lang_label_ar": "Arabic",
        "lang_label_en": "English",
        "spam_warning": "Warning: with your settings, average sends are faster than every 30 seconds and may feel spammy.",
        "save_hint": "You can save now without reconfiguring other options.",
    },
}

# Scheduler state
reminder_scheduler = AsyncIOScheduler(timezone=CAIRO_TZ)
reminder_lock = asyncio.Lock()
rotation_state: dict[str, int] = {}


# ============================================================================
# HELPERS
# ============================================================================

def tr(lang: str, key: str) -> str:
    safe = "en" if lang == "en" else "ar"
    return TEXTS[safe][key]


def parse_selected(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def get_athkar_option(athkar_id: str):
    for item in ATHKAR_OPTIONS:
        if item["id"] == athkar_id:
            return item
    return None


def get_user_lang_from_context(context: ContextTypes.DEFAULT_TYPE) -> str:
    return "en" if context.user_data.get("lang") == "en" else "ar"


def get_selected_names(selected_ids: list[str], lang: str) -> list[str]:
    key = "en" if lang == "en" else "ar"
    return [a[key] for a in ATHKAR_OPTIONS if a["id"] in selected_ids]


def load_draft_from_prefs(context: ContextTypes.DEFAULT_TYPE, prefs: UserPreferences | None):
    if not prefs:
        context.user_data["draft_selected"] = []
        context.user_data["draft_frequency"] = "every_30_min"
        context.user_data["draft_custom_minutes"] = None
        context.user_data["draft_goal_count"] = None
        context.user_data["draft_mode"] = "rotating"
        return

    context.user_data["draft_selected"] = parse_selected(prefs.selected_athkar)
    context.user_data["draft_frequency"] = prefs.frequency or "every_30_min"
    context.user_data["draft_custom_minutes"] = prefs.custom_frequency_minutes
    context.user_data["draft_goal_count"] = prefs.daily_goal_count
    context.user_data["draft_mode"] = prefs.delivery_mode or "rotating"


def get_plan_label(lang: str, frequency: str, custom_minutes: int | None, goal_count: int | None) -> str:
    if frequency == "custom_interval" and custom_minutes:
        return f"{custom_minutes} min" if lang == "en" else f"كل {custom_minutes} دقيقة"
    if frequency == "goal_per_day" and goal_count:
        return f"{goal_count} times/day" if lang == "en" else f"{goal_count} مرة يوميًا"
    if frequency in INTERVAL_PRESETS:
        return INTERVAL_PRESETS[frequency]["en" if lang == "en" else "ar"]
    return frequency


def compute_cycle_seconds(frequency: str, custom_minutes: int | None, goal_count: int | None) -> float:
    if frequency == "custom_interval" and custom_minutes:
        return float(custom_minutes * 60)
    if frequency == "goal_per_day" and goal_count and goal_count > 0:
        return 86400.0 / float(goal_count)
    if frequency in INTERVAL_PRESETS:
        return float(INTERVAL_PRESETS[frequency]["minutes"] * 60)
    return 300.0


def compute_spam_warning(selected_count: int, mode: str, frequency: str, custom_minutes: int | None, goal_count: int | None) -> bool:
    if selected_count <= 0:
        return False
    cycle_seconds = compute_cycle_seconds(frequency, custom_minutes, goal_count)
    per_cycle_messages = selected_count if mode == "batch" else 1
    avg_spacing = cycle_seconds / max(1, per_cycle_messages)
    return avg_spacing < 30.0


def main_menu(lang: str, has_prefs: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "btn_show"), callback_data="show_prefs")],
        [InlineKeyboardButton(tr(lang, "btn_edit_athkar"), callback_data="edit_athkar")],
        [InlineKeyboardButton(tr(lang, "btn_edit_plan"), callback_data="edit_plan")],
        [InlineKeyboardButton(tr(lang, "btn_reset"), callback_data="reset_all")],
    ]
    return InlineKeyboardMarkup(rows)


def language_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "btn_ar"), callback_data="set_lang_ar")],
        [InlineKeyboardButton(tr(lang, "btn_en"), callback_data="set_lang_en")],
    ])


def athkar_menu(lang: str, selected: list[str]) -> InlineKeyboardMarkup:
    all_selected = len(selected) == len(ATHKAR_OPTIONS)
    rows = [
        [InlineKeyboardButton(tr(lang, "btn_clear_all") if all_selected else tr(lang, "btn_select_all"), callback_data="toggle_all_athkar")]
    ]
    key = "en" if lang == "en" else "ar"
    for item in ATHKAR_OPTIONS:
        prefix = "✓ " if item["id"] in selected else "○ "
        rows.append([InlineKeyboardButton(prefix + item[key], callback_data=f"toggle_athkar_{item['id']}")])

    rows.append([InlineKeyboardButton(tr(lang, "btn_save"), callback_data="save_now")])
    rows.append([InlineKeyboardButton(tr(lang, "btn_continue"), callback_data="choose_strategy")])
    rows.append([InlineKeyboardButton(tr(lang, "btn_back"), callback_data="home")])
    return InlineKeyboardMarkup(rows)


def strategy_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "btn_strategy_interval"), callback_data="strategy_interval")],
        [InlineKeyboardButton(tr(lang, "btn_strategy_goal"), callback_data="strategy_goal")],
        [InlineKeyboardButton(tr(lang, "btn_save"), callback_data="save_now")],
        [InlineKeyboardButton(tr(lang, "btn_back"), callback_data="home")],
    ])


def interval_menu(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for code in ["every_1_min", "every_5_min", "every_30_min", "hourly"]:
        rows.append([InlineKeyboardButton(INTERVAL_PRESETS[code]["en" if lang == "en" else "ar"], callback_data=f"set_interval_{code}")])
    rows.append([InlineKeyboardButton(tr(lang, "btn_custom_interval"), callback_data="custom_interval")])
    rows.append([InlineKeyboardButton(tr(lang, "btn_save"), callback_data="save_now")])
    rows.append([InlineKeyboardButton(tr(lang, "btn_back"), callback_data="choose_strategy")])
    return InlineKeyboardMarkup(rows)


def goal_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("100", callback_data="set_goal_100")],
        [InlineKeyboardButton("200", callback_data="set_goal_200")],
        [InlineKeyboardButton("300", callback_data="set_goal_300")],
        [InlineKeyboardButton(tr(lang, "btn_custom_goal"), callback_data="custom_goal")],
        [InlineKeyboardButton(tr(lang, "btn_save"), callback_data="save_now")],
        [InlineKeyboardButton(tr(lang, "btn_back"), callback_data="choose_strategy")],
    ]
    return InlineKeyboardMarkup(rows)


def mode_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "mode_batch"), callback_data="set_mode_batch")],
        [InlineKeyboardButton(tr(lang, "mode_rotating"), callback_data="set_mode_rotating")],
        [InlineKeyboardButton(tr(lang, "btn_save"), callback_data="save_now")],
        [InlineKeyboardButton(tr(lang, "btn_back"), callback_data="choose_strategy")],
    ])


# ============================================================================
# DATABASE
# ============================================================================

async def init_db():
    logger.info("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS custom_frequency_minutes INTEGER"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS delivery_mode VARCHAR DEFAULT 'rotating'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'ar'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS daily_goal_count INTEGER"))
    logger.info("Database tables ready")


async def get_user_prefs(telegram_id: str) -> UserPreferences | None:
    async with async_session() as session:
        result = await session.execute(select(UserPreferences).where(UserPreferences.telegram_id == telegram_id))
        return result.scalars().first()


async def save_user_prefs(
    telegram_id: str,
    first_name: str,
    selected_athkar: list[str],
    frequency: str,
    language: str,
    delivery_mode: str,
    custom_frequency_minutes: int | None,
    daily_goal_count: int | None,
):
    async with async_session() as session:
        result = await session.execute(select(UserPreferences).where(UserPreferences.telegram_id == telegram_id))
        user_prefs = result.scalars().first()

        if user_prefs:
            user_prefs.selected_athkar = json.dumps(selected_athkar)
            user_prefs.frequency = frequency
            user_prefs.language = language
            user_prefs.delivery_mode = delivery_mode
            user_prefs.custom_frequency_minutes = custom_frequency_minutes
            user_prefs.daily_goal_count = daily_goal_count
            user_prefs.updated_at = datetime.utcnow()
        else:
            user_prefs = UserPreferences(
                telegram_id=telegram_id,
                first_name=first_name,
                selected_athkar=json.dumps(selected_athkar),
                frequency=frequency,
                language=language,
                delivery_mode=delivery_mode,
                custom_frequency_minutes=custom_frequency_minutes,
                daily_goal_count=daily_goal_count,
            )
            session.add(user_prefs)

        await session.commit()

    if reminder_scheduler.running:
        await rebuild_user_reminder_schedule()


async def reset_user_prefs(telegram_id: str):
    async with async_session() as session:
        await session.execute(delete(UserPreferences).where(UserPreferences.telegram_id == telegram_id))
        await session.commit()

    rotation_state.pop(telegram_id, None)
    if reminder_scheduler.running:
        await rebuild_user_reminder_schedule()


# ============================================================================
# REMINDER ENGINE
# ============================================================================

async def send_user_reminder(telegram_id: str):
    user_prefs = await get_user_prefs(telegram_id)
    if not user_prefs or not user_prefs.is_active:
        return

    selected_ids = parse_selected(user_prefs.selected_athkar)
    if not selected_ids:
        return

    lang = "en" if user_prefs.language == "en" else "ar"
    mode = user_prefs.delivery_mode or "rotating"

    async def send_one(athkar_id: str):
        item = get_athkar_option(athkar_id)
        if not item:
            return
        text_key = "text_en" if lang == "en" else "text_ar"
        await application.bot.send_message(chat_id=int(telegram_id), text=item[text_key])

    try:
        if mode == "batch":
            for athkar_id in selected_ids:
                await send_one(athkar_id)
        else:
            idx = rotation_state.get(telegram_id, 0) % len(selected_ids)
            await send_one(selected_ids[idx])
            rotation_state[telegram_id] = (idx + 1) % len(selected_ids)
    except Exception as e:
        logger.error("Failed sending reminder to user %s: %s", telegram_id, e)


def clear_user_jobs():
    for job in reminder_scheduler.get_jobs():
        if job.id.startswith("user_reminder_"):
            reminder_scheduler.remove_job(job.id)


def add_user_jobs(user_prefs: UserPreferences):
    telegram_id = str(user_prefs.telegram_id)
    frequency = user_prefs.frequency or "every_30_min"

    interval_seconds = None
    if frequency == "custom_interval" and user_prefs.custom_frequency_minutes:
        interval_seconds = user_prefs.custom_frequency_minutes * 60
    elif frequency == "goal_per_day" and user_prefs.daily_goal_count:
        interval_seconds = max(1, int(round(86400 / max(1, user_prefs.daily_goal_count))))
    elif frequency in INTERVAL_PRESETS:
        interval_seconds = INTERVAL_PRESETS[frequency]["minutes"] * 60

    if not interval_seconds:
        interval_seconds = 300

    reminder_scheduler.add_job(
        send_user_reminder,
        trigger=IntervalTrigger(seconds=interval_seconds, timezone=CAIRO_TZ),
        args=[telegram_id],
        id=f"user_reminder_{telegram_id}",
        replace_existing=True,
        misfire_grace_time=60,
    )


async def rebuild_user_reminder_schedule():
    async with reminder_lock:
        clear_user_jobs()
        async with async_session() as session:
            result = await session.execute(
                select(UserPreferences).where(
                    UserPreferences.is_active == True,
                    UserPreferences.selected_athkar.is_not(None),
                )
            )
            users = result.scalars().all()

        for user in users:
            if parse_selected(user.selected_athkar):
                add_user_jobs(user)

        total = len([j for j in reminder_scheduler.get_jobs() if j.id.startswith("user_reminder_")])
        logger.info("User reminder scheduler refreshed: %s jobs", total)


async def start_user_reminder_scheduler():
    if not reminder_scheduler.running:
        reminder_scheduler.start()

    reminder_scheduler.add_job(
        rebuild_user_reminder_schedule,
        trigger=CronTrigger(minute="*/15", timezone=CAIRO_TZ),
        id="user_reminder_refresh",
        replace_existing=True,
        misfire_grace_time=120,
    )

    await rebuild_user_reminder_schedule()


async def stop_user_reminder_scheduler():
    if reminder_scheduler.running:
        reminder_scheduler.shutdown(wait=False)


# ============================================================================
# UI ACTIONS
# ============================================================================

async def show_start_screen(target, context: ContextTypes.DEFAULT_TYPE, lang: str):
    text_value = tr(lang, "start_bilingual")
    keyboard = language_menu(lang)
    if hasattr(target, "edit_message_text"):
        await target.edit_message_text(text=text_value, reply_markup=keyboard)
    else:
        await context.bot.send_message(chat_id=target.id, text=text_value, reply_markup=keyboard)


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = str(user.id)
    lang = get_user_lang_from_context(context)

    prefs = await get_user_prefs(user_id)
    load_draft_from_prefs(context, prefs)
    text_value = tr(lang, "welcome_existing") if prefs else tr(lang, "welcome_new")
    kb = main_menu(lang, has_prefs=bool(prefs))

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text_value, reply_markup=kb)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text_value, reply_markup=kb)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["lang"] = "ar"
    if update.callback_query:
        await update.callback_query.answer()
        await show_start_screen(update.callback_query, context, "ar")
    else:
        await show_start_screen(update.effective_chat, context, "ar")


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = "en" if query.data.endswith("_en") else "ar"
    context.user_data["lang"] = lang

    user_id = str(query.from_user.id)
    prefs = await get_user_prefs(user_id)
    if prefs:
        async with async_session() as session:
            result = await session.execute(select(UserPreferences).where(UserPreferences.telegram_id == user_id))
            row = result.scalars().first()
            if row:
                row.language = lang
                row.updated_at = datetime.utcnow()
                await session.commit()

    await show_home(update, context)


async def edit_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    prefs = await get_user_prefs(user_id)
    if "draft_selected" not in context.user_data:
        load_draft_from_prefs(context, prefs)
    lang = get_user_lang_from_context(context)

    await query.edit_message_text(
        text=f"{tr(lang, 'choose_athkar')}\n\n{tr(lang, 'save_hint')}",
        reply_markup=athkar_menu(lang, context.user_data.get("draft_selected", [])),
    )


async def toggle_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    athkar_id = query.data.replace("toggle_athkar_", "")

    selected = context.user_data.setdefault("draft_selected", [])
    if athkar_id in selected:
        selected.remove(athkar_id)
    else:
        selected.append(athkar_id)

    lang = get_user_lang_from_context(context)
    await query.edit_message_text(
        text=f"{tr(lang, 'choose_athkar')}\n\n{tr(lang, 'save_hint')}",
        reply_markup=athkar_menu(lang, selected),
    )


async def toggle_all_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected = context.user_data.setdefault("draft_selected", [])
    all_ids = [a["id"] for a in ATHKAR_OPTIONS]
    context.user_data["draft_selected"] = [] if len(selected) == len(all_ids) else all_ids

    lang = get_user_lang_from_context(context)
    await query.edit_message_text(
        text=f"{tr(lang, 'choose_athkar')}\n\n{tr(lang, 'save_hint')}",
        reply_markup=athkar_menu(lang, context.user_data["draft_selected"]),
    )


async def choose_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang_from_context(context)

    selected = context.user_data.get("draft_selected", [])
    if not selected:
        await query.answer(tr(lang, "need_athkar"), show_alert=True)
        return

    await query.edit_message_text(text=tr(lang, "choose_strategy"), reply_markup=strategy_menu(lang))


async def choose_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang_from_context(context)
    await query.edit_message_text(text=tr(lang, "choose_interval"), reply_markup=interval_menu(lang))


async def choose_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_user_lang_from_context(context)
    await query.edit_message_text(text=tr(lang, "choose_goal"), reply_markup=goal_menu(lang))


async def set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    code = query.data.replace("set_interval_", "")
    context.user_data["draft_frequency"] = code
    context.user_data["draft_custom_minutes"] = None
    context.user_data["draft_goal_count"] = None

    lang = get_user_lang_from_context(context)
    await query.edit_message_text(text=tr(lang, "choose_mode"), reply_markup=mode_menu(lang))


async def set_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    code = query.data.replace("set_goal_", "")
    count = GOAL_PRESETS.get(f"goal_{code}")
    if not count:
        return

    context.user_data["draft_frequency"] = "goal_per_day"
    context.user_data["draft_goal_count"] = count
    context.user_data["draft_custom_minutes"] = None

    lang = get_user_lang_from_context(context)
    await query.edit_message_text(text=tr(lang, "choose_mode"), reply_markup=mode_menu(lang))


async def ask_custom_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_custom_kind"] = "interval"
    lang = get_user_lang_from_context(context)
    await query.edit_message_text(text=tr(lang, "prompt_custom_interval"))


async def ask_custom_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_custom_kind"] = "goal"
    lang = get_user_lang_from_context(context)
    await query.edit_message_text(text=tr(lang, "prompt_custom_goal"))


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kind = context.user_data.get("awaiting_custom_kind")
    if not kind:
        return

    lang = get_user_lang_from_context(context)
    raw = (update.message.text or "").strip()
    if not raw.isdigit():
        await update.message.reply_text(tr(lang, "invalid_number"))
        return

    num = int(raw)
    if kind == "interval":
        if num < 1 or num > 1440:
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        context.user_data["draft_frequency"] = "custom_interval"
        context.user_data["draft_custom_minutes"] = num
        context.user_data["draft_goal_count"] = None
    else:
        if num < 1 or num > 10000:
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        context.user_data["draft_frequency"] = "goal_per_day"
        context.user_data["draft_goal_count"] = num
        context.user_data["draft_custom_minutes"] = None

    context.user_data["awaiting_custom_kind"] = None
    await update.message.reply_text(tr(lang, "choose_mode"), reply_markup=mode_menu(lang))


async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["draft_mode"] = "batch" if query.data.endswith("_batch") else "rotating"

    lang = get_user_lang_from_context(context)
    warn = compute_spam_warning(
        selected_count=len(context.user_data.get("draft_selected", [])),
        mode=context.user_data.get("draft_mode", "rotating"),
        frequency=context.user_data.get("draft_frequency", "every_30_min"),
        custom_minutes=context.user_data.get("draft_custom_minutes"),
        goal_count=context.user_data.get("draft_goal_count"),
    )

    text_value = tr(lang, "save_hint")
    if warn:
        text_value = f"{tr(lang, 'spam_warning')}\n\n{text_value}"

    await query.edit_message_text(text=text_value, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "btn_save"), callback_data="save_now")],
        [InlineKeyboardButton(tr(lang, "btn_back"), callback_data="choose_strategy")],
    ]))


async def save_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = str(user.id)
    lang = get_user_lang_from_context(context)

    prefs = await get_user_prefs(user_id)
    if "draft_selected" not in context.user_data:
        load_draft_from_prefs(context, prefs)

    selected = context.user_data.get("draft_selected", [])
    if not selected:
        await query.answer(tr(lang, "need_athkar"), show_alert=True)
        return

    frequency = context.user_data.get("draft_frequency") or (prefs.frequency if prefs else "every_30_min")
    custom_minutes = context.user_data.get("draft_custom_minutes")
    goal_count = context.user_data.get("draft_goal_count")
    mode = context.user_data.get("draft_mode") or (prefs.delivery_mode if prefs else "rotating")

    if frequency != "custom_interval":
        custom_minutes = None
    if frequency != "goal_per_day":
        goal_count = None

    await save_user_prefs(
        telegram_id=user_id,
        first_name=user.first_name,
        selected_athkar=selected,
        frequency=frequency,
        language=lang,
        delivery_mode=mode,
        custom_frequency_minutes=custom_minutes,
        daily_goal_count=goal_count,
    )

    warn = compute_spam_warning(len(selected), mode, frequency, custom_minutes, goal_count)
    summary = build_prefs_summary(lang, selected, frequency, custom_minutes, goal_count, mode, warn)
    await query.edit_message_text(text=summary, reply_markup=main_menu(lang, has_prefs=True))


async def show_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    prefs = await get_user_prefs(user_id)
    lang = get_user_lang_from_context(context)

    if not prefs:
        await query.edit_message_text(text=tr(lang, "empty_athkar"), reply_markup=main_menu(lang, has_prefs=False))
        return

    selected = parse_selected(prefs.selected_athkar)
    summary = build_prefs_summary(
        lang=lang,
        selected=selected,
        frequency=prefs.frequency or "every_30_min",
        custom_minutes=prefs.custom_frequency_minutes,
        goal_count=prefs.daily_goal_count,
        mode=prefs.delivery_mode or "rotating",
        warn=compute_spam_warning(len(selected), prefs.delivery_mode or "rotating", prefs.frequency or "every_30_min", prefs.custom_frequency_minutes, prefs.daily_goal_count),
    )
    await query.edit_message_text(text=summary, reply_markup=main_menu(lang, has_prefs=True))


def build_prefs_summary(lang: str, selected: list[str], frequency: str, custom_minutes: int | None, goal_count: int | None, mode: str, warn: bool) -> str:
    names = get_selected_names(selected, lang)
    mode_label = tr(lang, "mode_batch_label") if mode == "batch" else tr(lang, "mode_rotating_label")
    plan_label = get_plan_label(lang, frequency, custom_minutes, goal_count)
    lang_label = tr(lang, "lang_label_en") if lang == "en" else tr(lang, "lang_label_ar")

    text_value = (
        f"{tr(lang, 'prefs_title')}\n\n"
        f"{tr(lang, 'field_lang')}: {lang_label}\n\n"
        f"{tr(lang, 'field_athkar')}:\n"
        f"{chr(10).join(['- ' + n for n in names])}\n\n"
        f"{tr(lang, 'field_plan')}: {plan_label}\n"
        f"{tr(lang, 'field_mode')}: {mode_label}"
    )
    if warn:
        text_value += f"\n\n{tr(lang, 'spam_warning')}"
    return text_value


async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = get_user_lang_from_context(context)

    await reset_user_prefs(user_id)
    context.user_data.clear()
    context.user_data["lang"] = "ar"

    await query.edit_message_text(text=f"{tr(lang, 'confirm_reset')}\n\n{tr(lang, 'reset_done')}")
    await show_start_screen(query, context, "ar")


# ============================================================================
# WEB SERVER
# ============================================================================

async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response()


async def handle_root(request):
    return web.Response(text="User side bot is running")


# ============================================================================
# BOT INITIALIZATION
# ============================================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

application = Application.builder().token(TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(set_language, pattern="^set_lang_(ar|en)$"))
application.add_handler(CallbackQueryHandler(show_home, pattern="^home$"))
application.add_handler(CallbackQueryHandler(show_prefs, pattern="^show_prefs$"))
application.add_handler(CallbackQueryHandler(edit_athkar, pattern="^edit_athkar$"))
application.add_handler(CallbackQueryHandler(toggle_all_athkar, pattern="^toggle_all_athkar$"))
application.add_handler(CallbackQueryHandler(toggle_athkar, pattern="^toggle_athkar_"))
application.add_handler(CallbackQueryHandler(choose_strategy, pattern="^choose_strategy$|^edit_plan$"))
application.add_handler(CallbackQueryHandler(choose_interval, pattern="^strategy_interval$"))
application.add_handler(CallbackQueryHandler(choose_goal, pattern="^strategy_goal$"))
application.add_handler(CallbackQueryHandler(set_interval, pattern="^set_interval_"))
application.add_handler(CallbackQueryHandler(set_goal, pattern="^set_goal_"))
application.add_handler(CallbackQueryHandler(ask_custom_interval, pattern="^custom_interval$"))
application.add_handler(CallbackQueryHandler(ask_custom_goal, pattern="^custom_goal$"))
application.add_handler(CallbackQueryHandler(set_mode, pattern="^set_mode_(batch|rotating)$"))
application.add_handler(CallbackQueryHandler(save_now, pattern="^save_now$"))
application.add_handler(CallbackQueryHandler(reset_all, pattern="^reset_all$"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update: %s", context.error, exc_info=context.error)


application.add_error_handler(error_handler)

web_app = web.Application()
web_app.router.add_get("/", handle_root)
web_app.router.add_post("/webhook", handle_webhook)

logger.info("User side bot initialized")
