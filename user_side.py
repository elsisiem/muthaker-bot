"""
Interactive user preferences bot for personalized Athkar reminders.
Users choose Athkar content, frequency, language, and delivery mode.
"""

import os
import logging
import json
from datetime import datetime

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
from sqlalchemy import Column, Integer, String, Boolean, DateTime, select, Text, text
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
    """User preferences model for Athkar reminders."""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    first_name = Column(String, nullable=True)
    selected_athkar = Column(Text, nullable=True)  # JSON: ["hizb", "baaqiyat", ...]
    frequency = Column(String, default="2x_daily")
    custom_frequency_minutes = Column(Integer, nullable=True)
    delivery_mode = Column(String, default="rotating")  # rotating | batch
    language = Column(String, default="ar")  # ar | en
    timezone = Column(String, default="Africa/Cairo")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ============================================================================
# CONTENT DEFINITIONS
# ============================================================================

ATHKAR_OPTIONS = [
    {
        "id": "hizb",
        "ar": "ورد الحرز",
        "en": "Hizb Wird",
        "text_ar": "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد.",
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

FREQUENCY_OPTIONS = {
    "every_1_min": {"minutes": 1, "ar": "كل دقيقة", "en": "Every minute"},
    "every_5_min": {"minutes": 5, "ar": "كل 5 دقائق", "en": "Every 5 minutes"},
    "every_30_min": {"minutes": 30, "ar": "كل 30 دقيقة", "en": "Every 30 minutes"},
    "hourly": {"minutes": 60, "ar": "كل ساعة", "en": "Hourly"},
    "1x_daily": {"times": ["09:00"], "ar": "مرة يوميًا", "en": "Once daily"},
    "2x_daily": {"times": ["09:00", "18:00"], "ar": "مرتان يوميًا", "en": "Twice daily"},
    "3x_daily": {"times": ["09:00", "13:00", "18:00"], "ar": "ثلاث مرات يوميًا", "en": "Three times daily"},
}

TEXTS = {
    "ar": {
        "welcome_new": "مرحبًا {name}.\n\nأهلًا بك في خدمة إعداد تذكيرات الأذكار.\nابدأ باختيار اللغة.",
        "welcome_existing": "مرحبًا {name}.\n\nإعداداتك محفوظة. اختر الإجراء المطلوب.",
        "btn_lang": "اختيار اللغة",
        "btn_edit_athkar": "تعديل الأذكار",
        "btn_edit_freq": "تعديل التكرار",
        "btn_show": "عرض الإعدادات",
        "btn_start_setup": "بدء الإعداد",
        "choose_lang": "اختر اللغة المفضلة:",
        "lang_saved": "تم حفظ اللغة.",
        "choose_athkar": "اختر الأذكار المطلوبة:\nيمكن اختيار أكثر من عنصر.",
        "btn_select_all": "تحديد الكل",
        "btn_clear_all": "إلغاء تحديد الكل",
        "btn_continue": "متابعة إلى التكرار",
        "btn_back": "رجوع",
        "need_athkar": "يرجى اختيار ذكر واحد على الأقل.",
        "choose_freq": "اختر وتيرة التذكير:",
        "btn_custom_freq": "تكرار مخصص",
        "custom_prompt": "أرسل عدد الدقائق للتكرار المخصص (من 1 إلى 1440). مثال: 7",
        "custom_invalid": "القيمة غير صحيحة. أرسل رقمًا من 1 إلى 1440.",
        "choose_mode": "اختر أسلوب الإرسال:\n1) دفعة واحدة: إرسال جميع الأذكار في كل دورة.\n2) بالتناوب: إرسال ذكر مختلف في كل دورة.",
        "mode_batch": "دفعة واحدة",
        "mode_rotating": "بالتناوب",
        "saved": "تم حفظ إعداداتك بنجاح.",
        "prefs_title": "الإعدادات الحالية",
        "field_lang": "اللغة",
        "field_athkar": "الأذكار",
        "field_freq": "التكرار",
        "field_mode": "أسلوب الإرسال",
        "empty_athkar": "لا توجد أذكار محددة حتى الآن.",
        "lang_ar": "العربية",
        "lang_en": "الإنجليزية",
        "mode_batch_label": "دفعة واحدة",
        "mode_rotating_label": "بالتناوب",
        "btn_change_lang": "تغيير اللغة",
    },
    "en": {
        "welcome_new": "Welcome {name}.\n\nThis service helps you configure Athkar reminders.\nStart by choosing your language.",
        "welcome_existing": "Welcome {name}.\n\nYour settings are saved. Choose an action.",
        "btn_lang": "Choose language",
        "btn_edit_athkar": "Edit Athkar",
        "btn_edit_freq": "Edit frequency",
        "btn_show": "View settings",
        "btn_start_setup": "Start setup",
        "choose_lang": "Choose your preferred language:",
        "lang_saved": "Language saved.",
        "choose_athkar": "Select the Athkar you want:\nYou can select multiple items.",
        "btn_select_all": "Select all",
        "btn_clear_all": "Clear all",
        "btn_continue": "Continue to frequency",
        "btn_back": "Back",
        "need_athkar": "Please select at least one Athkar.",
        "choose_freq": "Choose reminder frequency:",
        "btn_custom_freq": "Custom interval",
        "custom_prompt": "Send the custom interval in minutes (1 to 1440). Example: 7",
        "custom_invalid": "Invalid value. Send a number from 1 to 1440.",
        "choose_mode": "Choose delivery mode:\n1) Batch: send all selected Athkar each cycle.\n2) Rotating: send one different Athkar per cycle.",
        "mode_batch": "Batch",
        "mode_rotating": "Rotating",
        "saved": "Your settings have been saved.",
        "prefs_title": "Current settings",
        "field_lang": "Language",
        "field_athkar": "Athkar",
        "field_freq": "Frequency",
        "field_mode": "Delivery mode",
        "empty_athkar": "No Athkar selected yet.",
        "lang_ar": "Arabic",
        "lang_en": "English",
        "mode_batch_label": "Batch",
        "mode_rotating_label": "Rotating",
        "btn_change_lang": "Change language",
    },
}


# ============================================================================
# HELPERS
# ============================================================================

def tr(lang: str, key: str, **kwargs) -> str:
    safe_lang = "en" if lang == "en" else "ar"
    value = TEXTS[safe_lang][key]
    if kwargs:
        return value.format(**kwargs)
    return value


def get_lang_from_prefs(user_prefs: UserPreferences | None) -> str:
    if user_prefs and user_prefs.language in ("ar", "en"):
        return user_prefs.language
    return "ar"


async def get_user_language(user_id: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    lang = context.user_data.get("lang")
    if lang in ("ar", "en"):
        return lang

    user_prefs = await get_user_prefs(user_id)
    lang = get_lang_from_prefs(user_prefs)
    context.user_data["lang"] = lang
    return lang


def get_selected_athkar_names(selected_ids: list[str], lang: str) -> list[str]:
    key = "en" if lang == "en" else "ar"
    return [a[key] for a in ATHKAR_OPTIONS if a["id"] in selected_ids]


def format_frequency_label(frequency: str, custom_minutes: int | None, lang: str) -> str:
    if frequency == "custom_interval" and custom_minutes:
        if lang == "en":
            return f"Every {custom_minutes} minute(s)"
        return f"كل {custom_minutes} دقيقة"

    option = FREQUENCY_OPTIONS.get(frequency)
    if not option:
        return frequency

    label = option["en"] if lang == "en" else option["ar"]
    if "times" in option:
        return f"{label} ({', '.join(option['times'])})"
    return label


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

async def init_db():
    """Initialize database tables and add new columns if missing."""
    logger.info("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Lightweight in-place schema updates for existing deployments.
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS custom_frequency_minutes INTEGER"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS delivery_mode VARCHAR DEFAULT 'rotating'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'ar'"))

    logger.info("Database tables ready")


async def get_user_prefs(telegram_id: str) -> UserPreferences | None:
    """Get user preferences from database."""
    async with async_session() as session:
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.telegram_id == str(telegram_id))
        )
        return result.scalars().first()


async def save_user_prefs(
    telegram_id: str,
    first_name: str,
    selected_athkar: list[str],
    frequency: str,
    language: str,
    delivery_mode: str,
    custom_frequency_minutes: int | None,
):
    """Save or update user preferences."""
    async with async_session() as session:
        user = await session.execute(
            select(UserPreferences).where(UserPreferences.telegram_id == str(telegram_id))
        )
        user_prefs = user.scalars().first()

        if user_prefs:
            user_prefs.selected_athkar = json.dumps(selected_athkar)
            user_prefs.frequency = frequency
            user_prefs.language = language
            user_prefs.delivery_mode = delivery_mode
            user_prefs.custom_frequency_minutes = custom_frequency_minutes
            user_prefs.updated_at = datetime.utcnow()
        else:
            user_prefs = UserPreferences(
                telegram_id=str(telegram_id),
                first_name=first_name,
                selected_athkar=json.dumps(selected_athkar),
                frequency=frequency,
                language=language,
                delivery_mode=delivery_mode,
                custom_frequency_minutes=custom_frequency_minutes,
            )
            session.add(user_prefs)

        await session.commit()
        logger.info(
            "Saved preferences for user %s: athkar=%s frequency=%s lang=%s mode=%s custom=%s",
            telegram_id,
            len(selected_athkar),
            frequency,
            language,
            delivery_mode,
            custom_frequency_minutes,
        )


# ============================================================================
# UI BUILDERS
# ============================================================================

def build_main_menu(lang: str, has_prefs: bool) -> InlineKeyboardMarkup:
    if has_prefs:
        buttons = [
            [InlineKeyboardButton(tr(lang, "btn_show"), callback_data="show_prefs")],
            [InlineKeyboardButton(tr(lang, "btn_edit_athkar"), callback_data="edit_athkar")],
            [InlineKeyboardButton(tr(lang, "btn_edit_freq"), callback_data="edit_frequency")],
            [InlineKeyboardButton(tr(lang, "btn_change_lang"), callback_data="lang_menu")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(tr(lang, "btn_lang"), callback_data="lang_menu")],
            [InlineKeyboardButton(tr(lang, "btn_start_setup"), callback_data="select_athkar")],
        ]
    return InlineKeyboardMarkup(buttons)


def build_language_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "lang_ar"), callback_data="set_lang_ar")],
        [InlineKeyboardButton(tr(lang, "lang_en"), callback_data="set_lang_en")],
        [InlineKeyboardButton(tr(lang, "btn_back"), callback_data="start")],
    ])


def build_athkar_menu(lang: str, selected_ids: list[str]) -> InlineKeyboardMarkup:
    key = "en" if lang == "en" else "ar"
    all_selected = len(selected_ids) == len(ATHKAR_OPTIONS)

    buttons = []
    buttons.append([
        InlineKeyboardButton(
            tr(lang, "btn_clear_all") if all_selected else tr(lang, "btn_select_all"),
            callback_data="toggle_all_athkar",
        )
    ])

    for athkar in ATHKAR_OPTIONS:
        selected = "[x] " if athkar["id"] in selected_ids else "[ ] "
        buttons.append([InlineKeyboardButton(f"{selected}{athkar[key]}", callback_data=f"toggle_athkar_{athkar['id']}")])

    buttons.append([InlineKeyboardButton(tr(lang, "btn_continue"), callback_data="choose_frequency")])
    buttons.append([InlineKeyboardButton(tr(lang, "btn_back"), callback_data="start")])
    return InlineKeyboardMarkup(buttons)


def build_frequency_menu(lang: str) -> InlineKeyboardMarkup:
    ordered_ids = [
        "every_1_min",
        "every_5_min",
        "every_30_min",
        "hourly",
        "1x_daily",
        "2x_daily",
        "3x_daily",
    ]

    buttons = []
    for freq_id in ordered_ids:
        option = FREQUENCY_OPTIONS[freq_id]
        label = option["en"] if lang == "en" else option["ar"]
        if "times" in option:
            label = f"{label} ({', '.join(option['times'])})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"set_freq_{freq_id}")])

    buttons.append([InlineKeyboardButton(tr(lang, "btn_custom_freq"), callback_data="custom_frequency")])
    buttons.append([InlineKeyboardButton(tr(lang, "btn_back"), callback_data="select_athkar")])
    return InlineKeyboardMarkup(buttons)


def build_delivery_mode_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "mode_batch"), callback_data="set_mode_batch")],
        [InlineKeyboardButton(tr(lang, "mode_rotating"), callback_data="set_mode_rotating")],
        [InlineKeyboardButton(tr(lang, "btn_back"), callback_data="choose_frequency")],
    ])


# ============================================================================
# TELEGRAM HANDLERS
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command and landing menu."""
    user = update.effective_user
    user_id = str(user.id)

    user_prefs = await get_user_prefs(user_id)
    lang = await get_user_language(user_id, context)

    logger.info("/start command from user %s (%s)", user_id, user.first_name)

    text_value = tr(lang, "welcome_existing", name=user.first_name) if user_prefs else tr(lang, "welcome_new", name=user.first_name)
    keyboard = build_main_menu(lang, has_prefs=bool(user_prefs))

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text_value, reply_markup=keyboard)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text_value, reply_markup=keyboard)


async def show_language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang = await get_user_language(user_id, context)
    await query.edit_message_text(text=tr(lang, "choose_lang"), reply_markup=build_language_menu(lang))


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    chosen = "en" if query.data.endswith("_en") else "ar"
    context.user_data["lang"] = chosen

    user_prefs = await get_user_prefs(user_id)
    if user_prefs:
        async with async_session() as session:
            result = await session.execute(select(UserPreferences).where(UserPreferences.telegram_id == user_id))
            prefs = result.scalars().first()
            if prefs:
                prefs.language = chosen
                prefs.updated_at = datetime.utcnow()
                await session.commit()

    await query.edit_message_text(
        text=tr(chosen, "lang_saved"),
        reply_markup=build_main_menu(chosen, has_prefs=bool(user_prefs)),
    )


async def select_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Athkar selection menu."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang = await get_user_language(user_id, context)

    if "selected_athkar" not in context.user_data:
        user_prefs = await get_user_prefs(user_id)
        if user_prefs and user_prefs.selected_athkar:
            context.user_data["selected_athkar"] = json.loads(user_prefs.selected_athkar)
        else:
            context.user_data["selected_athkar"] = []

    selected = context.user_data["selected_athkar"]
    await query.edit_message_text(
        text=tr(lang, "choose_athkar"),
        reply_markup=build_athkar_menu(lang, selected),
    )


async def toggle_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle one Athkar item."""
    query = update.callback_query
    await query.answer()

    athkar_id = query.data.replace("toggle_athkar_", "")
    user_id = str(query.from_user.id)
    lang = await get_user_language(user_id, context)

    selected = context.user_data.setdefault("selected_athkar", [])
    if athkar_id in selected:
        selected.remove(athkar_id)
    else:
        selected.append(athkar_id)

    await query.edit_message_text(
        text=tr(lang, "choose_athkar"),
        reply_markup=build_athkar_menu(lang, selected),
    )


async def toggle_all_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle between select-all and clear-all."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang = await get_user_language(user_id, context)

    selected = context.user_data.setdefault("selected_athkar", [])
    all_ids = [a["id"] for a in ATHKAR_OPTIONS]

    if len(selected) == len(all_ids):
        context.user_data["selected_athkar"] = []
    else:
        context.user_data["selected_athkar"] = all_ids

    await query.edit_message_text(
        text=tr(lang, "choose_athkar"),
        reply_markup=build_athkar_menu(lang, context.user_data["selected_athkar"]),
    )


async def choose_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show frequency selection menu."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang = await get_user_language(user_id, context)

    selected = context.user_data.get("selected_athkar", [])
    if not selected:
        await query.answer(tr(lang, "need_athkar"), show_alert=True)
        return

    await query.edit_message_text(
        text=tr(lang, "choose_freq"),
        reply_markup=build_frequency_menu(lang),
    )


async def set_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store selected predefined frequency and move to delivery mode selection."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang = await get_user_language(user_id, context)

    selected = context.user_data.get("selected_athkar", [])
    if not selected:
        await query.answer(tr(lang, "need_athkar"), show_alert=True)
        return

    frequency = query.data.replace("set_freq_", "")
    context.user_data["frequency"] = frequency
    context.user_data["custom_frequency_minutes"] = None

    await query.edit_message_text(
        text=tr(lang, "choose_mode"),
        reply_markup=build_delivery_mode_menu(lang),
    )


async def ask_custom_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt user for custom interval in minutes."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    lang = await get_user_language(user_id, context)

    context.user_data["awaiting_custom_frequency"] = True
    await query.edit_message_text(
        text=tr(lang, "custom_prompt"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(tr(lang, "btn_back"), callback_data="choose_frequency")]]),
    )


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom frequency input text when requested."""
    user = update.effective_user
    user_id = str(user.id)
    lang = await get_user_language(user_id, context)

    if not context.user_data.get("awaiting_custom_frequency"):
        return

    raw_text = (update.message.text or "").strip()
    if not raw_text.isdigit():
        await update.message.reply_text(tr(lang, "custom_invalid"))
        return

    minutes = int(raw_text)
    if minutes < 1 or minutes > 1440:
        await update.message.reply_text(tr(lang, "custom_invalid"))
        return

    context.user_data["awaiting_custom_frequency"] = False
    context.user_data["frequency"] = "custom_interval"
    context.user_data["custom_frequency_minutes"] = minutes

    await update.message.reply_text(
        tr(lang, "choose_mode"),
        reply_markup=build_delivery_mode_menu(lang),
    )


async def set_delivery_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finalize and save preferences."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = str(user.id)
    lang = await get_user_language(user_id, context)

    selected = context.user_data.get("selected_athkar", [])
    if not selected:
        await query.answer(tr(lang, "need_athkar"), show_alert=True)
        return

    frequency = context.user_data.get("frequency")
    if not frequency:
        await query.answer(tr(lang, "choose_freq"), show_alert=True)
        return

    delivery_mode = "batch" if query.data.endswith("_batch") else "rotating"
    custom_minutes = context.user_data.get("custom_frequency_minutes")

    await save_user_prefs(
        telegram_id=user_id,
        first_name=user.first_name,
        selected_athkar=selected,
        frequency=frequency,
        language=lang,
        delivery_mode=delivery_mode,
        custom_frequency_minutes=custom_minutes,
    )

    selected_names = get_selected_athkar_names(selected, lang)
    frequency_label = format_frequency_label(frequency, custom_minutes, lang)
    mode_label = tr(lang, "mode_batch_label") if delivery_mode == "batch" else tr(lang, "mode_rotating_label")

    summary = (
        f"{tr(lang, 'saved')}\n\n"
        f"{tr(lang, 'field_lang')}: {tr(lang, 'lang_en') if lang == 'en' else tr(lang, 'lang_ar')}\n"
        f"{tr(lang, 'field_athkar')}:\n"
        f"{chr(10).join(['- ' + name for name in selected_names])}\n\n"
        f"{tr(lang, 'field_freq')}: {frequency_label}\n"
        f"{tr(lang, 'field_mode')}: {mode_label}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "btn_show"), callback_data="show_prefs")],
        [InlineKeyboardButton(tr(lang, "btn_edit_athkar"), callback_data="edit_athkar")],
        [InlineKeyboardButton(tr(lang, "btn_edit_freq"), callback_data="edit_frequency")],
    ])

    await query.edit_message_text(text=summary, reply_markup=keyboard)


async def show_prefs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current preferences."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    user_prefs = await get_user_prefs(user_id)
    lang = await get_user_language(user_id, context)

    if not user_prefs or not user_prefs.selected_athkar:
        text_value = tr(lang, "empty_athkar")
        buttons = [[InlineKeyboardButton(tr(lang, "btn_start_setup"), callback_data="select_athkar")]]
        await query.edit_message_text(text=text_value, reply_markup=InlineKeyboardMarkup(buttons))
        return

    selected_ids = json.loads(user_prefs.selected_athkar)
    selected_names = get_selected_athkar_names(selected_ids, user_prefs.language or lang)
    freq_label = format_frequency_label(user_prefs.frequency, user_prefs.custom_frequency_minutes, user_prefs.language or lang)
    mode_label = tr(user_prefs.language or lang, "mode_batch_label") if user_prefs.delivery_mode == "batch" else tr(user_prefs.language or lang, "mode_rotating_label")
    lang_label = tr(user_prefs.language or lang, "lang_en") if (user_prefs.language or lang) == "en" else tr(user_prefs.language or lang, "lang_ar")

    text_value = (
        f"{tr(user_prefs.language or lang, 'prefs_title')}\n\n"
        f"{tr(user_prefs.language or lang, 'field_lang')}: {lang_label}\n\n"
        f"{tr(user_prefs.language or lang, 'field_athkar')}:\n"
        f"{chr(10).join(['- ' + name for name in selected_names])}\n\n"
        f"{tr(user_prefs.language or lang, 'field_freq')}: {freq_label}\n"
        f"{tr(user_prefs.language or lang, 'field_mode')}: {mode_label}"
    )

    buttons = [
        [InlineKeyboardButton(tr(user_prefs.language or lang, "btn_edit_athkar"), callback_data="edit_athkar")],
        [InlineKeyboardButton(tr(user_prefs.language or lang, "btn_edit_freq"), callback_data="edit_frequency")],
        [InlineKeyboardButton(tr(user_prefs.language or lang, "btn_change_lang"), callback_data="lang_menu")],
    ]
    await query.edit_message_text(text=text_value, reply_markup=InlineKeyboardMarkup(buttons))


async def edit_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit Athkar selections for existing user."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    user_prefs = await get_user_prefs(user_id)

    if user_prefs and user_prefs.selected_athkar:
        context.user_data["selected_athkar"] = json.loads(user_prefs.selected_athkar)
    else:
        context.user_data["selected_athkar"] = []

    await select_athkar(update, context)


async def edit_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edit frequency and delivery mode for existing user."""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    user_prefs = await get_user_prefs(user_id)
    lang = await get_user_language(user_id, context)

    if not user_prefs or not user_prefs.selected_athkar:
        await query.answer(tr(lang, "need_athkar"), show_alert=True)
        return

    context.user_data["selected_athkar"] = json.loads(user_prefs.selected_athkar)
    context.user_data["frequency"] = user_prefs.frequency
    context.user_data["custom_frequency_minutes"] = user_prefs.custom_frequency_minutes

    await choose_frequency(update, context)


# ============================================================================
# WEB SERVER SETUP
# ============================================================================

async def handle_webhook(request):
    """Handle Telegram webhook requests."""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response()


async def handle_root(request):
    """Health check endpoint."""
    return web.Response(text="User side bot is running")


# ============================================================================
# BOT INITIALIZATION
# ============================================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

application = Application.builder().token(TOKEN).build()

# Add handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(show_language_menu, pattern="^lang_menu$"))
application.add_handler(CallbackQueryHandler(set_language, pattern="^set_lang_(ar|en)$"))
application.add_handler(CallbackQueryHandler(select_athkar, pattern="^select_athkar$"))
application.add_handler(CallbackQueryHandler(toggle_all_athkar, pattern="^toggle_all_athkar$"))
application.add_handler(CallbackQueryHandler(toggle_athkar, pattern="^toggle_athkar_"))
application.add_handler(CallbackQueryHandler(choose_frequency, pattern="^choose_frequency$"))
application.add_handler(CallbackQueryHandler(set_frequency, pattern="^set_freq_"))
application.add_handler(CallbackQueryHandler(ask_custom_frequency, pattern="^custom_frequency$"))
application.add_handler(CallbackQueryHandler(set_delivery_mode, pattern="^set_mode_(batch|rotating)$"))
application.add_handler(CallbackQueryHandler(edit_athkar, pattern="^edit_athkar$"))
application.add_handler(CallbackQueryHandler(edit_frequency, pattern="^edit_frequency$"))
application.add_handler(CallbackQueryHandler(show_prefs, pattern="^show_prefs$"))
application.add_handler(CallbackQueryHandler(start, pattern="^start$"))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors from update handlers."""
    logger.error("Exception while handling an update: %s", context.error, exc_info=context.error)


application.add_error_handler(error_handler)

# Web app for webhook
web_app = web.Application()
web_app.router.add_get("/", handle_root)
web_app.router.add_post("/webhook", handle_webhook)

logger.info("User side bot initialized")
