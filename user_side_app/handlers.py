import json
import logging
import random
import re
from pathlib import Path
from datetime import datetime, timedelta
from uuid import uuid4

import aiohttp
import pytz
from telegram import ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from .db import (
    add_or_update_target,
    create_community_post,
    get_target,
    get_user_prefs,
    list_community_posts,
    list_active_users,
    list_targets,
    remove_target,
    remove_community_post,
    reset_user_preferences,
    update_target_settings,
    update_user_settings,
    upsert_user_prefs,
)
from .i18n import normalize_lang, tr
from .keyboards import (
    athkar_select_menu,
    advanced_goal_menu,
    community_connect_menu,
    community_menu,
    community_posts_menu,
    custom_athkar_prompt_menu,
    delivery_menu,
    goal_menu,
    goal_scope_menu,
    home_menu,
    interval_menu,
    language_menu,
    locality_setup_menu,
    location_request_keyboard,
    personal_menu,
    post_prayer_anchor_menu,
    post_schedule_menu,
    quiet_hours_menu,
    remove_target_menu,
    reset_confirmation_menu,
    schedule_menu,
    setup_complete_menu,
    target_picker_menu,
    target_request_keyboard,
)
from .scheduler import (
    reminder_scheduler,
    rebuild_all_jobs,
    set_application,
    get_application,
)
from .community_dispatcher import fetch_prayer_times
from services.timezone_service import detect_timezone_from_location

logger = logging.getLogger(__name__)
UI_BUILD = "user-side-v203"
CAIRO_TZ = pytz.timezone("Africa/Cairo")
QUIET_HOUR_PRESETS = {"normal": (23, 6), "early": (21, 5), "night_owl": (1, 9), "none": (0, 0)}

ATHKAR_OPTIONS = [
    {"id": "hizb", "ar": "الحرز", "en": "Protection", "text_ar": "حسبي الله لا إله إلا هو، عليه توكلت وهو رب العرش العظيم.", "text_en": "Allah is sufficient for me; there is no god but Him."},
    {"id": "hamd", "ar": "الحمد", "en": "Praise", "text_ar": "الحمد لله رب العالمين.", "text_en": "Praise be to Allah, Lord of the worlds."},
    {"id": "hawqala", "ar": "الحوقلة", "en": "Hawqala", "text_ar": "لا حول ولا قوة إلا بالله.", "text_en": "There is no power nor strength except through Allah."},
    {"id": "tahlil", "ar": "التهليل", "en": "Tahlil", "text_ar": "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير.", "text_en": "There is no god but Allah alone, with no partner."},
    {"id": "istighfar", "ar": "الاستغفار", "en": "Istighfar", "text_ar": "أستغفر الله العظيم وأتوب إليه.", "text_en": "I seek forgiveness from Allah and repent to Him."},
    {"id": "salat", "ar": "الصلاة على النبي", "en": "Salawat", "text_ar": "اللهم صل وسلم وبارك على محمد.", "text_en": "O Allah, send prayers and peace upon Muhammad."},
    {"id": "tasbih", "ar": "التسبيح", "en": "Tasbih", "text_ar": "سبحان الله وبحمده، سبحان الله العظيم.", "text_en": "Glory be to Allah and praise be to Him; glory be to Allah the Most Great."},
    {"id": "baaqiyat", "ar": "الباقيات الصالحات", "en": "Lasting good deeds", "text_ar": "سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر.", "text_en": "Glory be to Allah, praise be to Allah, there is no god but Allah, and Allah is the Greatest."},
    {"id": "yunus", "ar": "دعاء ذي النون", "en": "Dua of Dhu al-Nun", "text_ar": "لا إله إلا أنت سبحانك إني كنت من الظالمين.", "text_en": "There is no god but You. Glory be to You; I was among the wrongdoers."},
]

rotation_state: dict[str, int] = {}
quiet_timing_cache: dict[tuple[str, str], dict | None] = {}


def get_lang(context: ContextTypes.DEFAULT_TYPE, fallback: str = "ar") -> str:
    return normalize_lang(context.user_data.get("lang"), fallback)


def parse_selected(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def parse_custom_athkar(raw: str | None) -> list[dict[str, str]]:
    """Read user-created Athkar while keeping untrusted persisted data safe."""
    if not raw:
        return []
    try:
        entries = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(entries, list):
        return []
    valid: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        athkar_id, name, text = entry.get("id"), entry.get("name"), entry.get("text")
        if (
            isinstance(athkar_id, str) and athkar_id.startswith("custom_")
            and isinstance(name, str) and name.strip()
            and isinstance(text, str) and text.strip()
        ):
            valid.append({"id": athkar_id, "name": name.strip()[:80], "text": text.strip()[:3500]})
    return valid


def all_athkar_options(prefs=None) -> list[dict[str, str]]:
    """Merge the built-in collection with this user's own saved Athkar."""
    options = list(ATHKAR_OPTIONS)
    for item in parse_custom_athkar(getattr(prefs, "custom_athkar", None)):
        options.append({
            "id": item["id"], "ar": item["name"], "en": item["name"],
            "text_ar": item["text"], "text_en": item["text"],
        })
    return options


def normalize_digits(value: str) -> str:
    """Accept Arabic-Indic and Eastern Arabic-Indic digits in numeric settings."""
    return value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))


def parse_quiet_periods(raw: str | None) -> list[tuple[int, int]]:
    """Read validated custom quiet intervals expressed as minutes after midnight."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    periods: list[tuple[int, int]] = []
    if not isinstance(value, list):
        return periods
    for period in value:
        if (
            isinstance(period, list)
            and len(period) == 2
            and all(isinstance(item, int) and 0 <= item < 1440 for item in period)
        ):
            periods.append((period[0], period[1]))
    return periods


def quiet_hours_label(prefs, lang: str) -> str:
    if not prefs or not prefs.quiet_hours_preset:
        return tr(lang, "quiet_none")
    label = tr(lang, f"quiet_{prefs.quiet_hours_preset}")
    if prefs.quiet_hours_preset != "custom":
        return label
    periods = parse_quiet_periods(getattr(prefs, "quiet_periods", None))
    if not periods:
        periods = [
            (
                (prefs.quiet_start_hour or 0) * 60 + (prefs.quiet_start_minute or 0),
                (prefs.quiet_end_hour or 0) * 60 + (prefs.quiet_end_minute or 0),
            )
        ]
    formatted = "، ".join(
        f"{start // 60:02d}:{start % 60:02d}–{end // 60:02d}:{end % 60:02d}"
        for start, end in periods
    )
    return f"{label} ({formatted})"


def selected_names(selected_ids: list[str], lang: str, prefs=None) -> list[str]:
    key = "ar" if lang == "ar" else "en"
    return [x[key] for x in all_athkar_options(prefs) if x["id"] in selected_ids]


def frequency_label(prefs, lang: str) -> str:
    return {
        "every_5_min": tr(lang, "interval_5"),
        "every_30_min": tr(lang, "interval_30"),
        "hourly": tr(lang, "interval_60"),
        "goal_per_day": tr(lang, "daily_goal_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
        "goal_per_athkar": tr(lang, "daily_goal_each_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
        "custom_interval": tr(lang, "custom_interval_summary").replace("{minutes}", str(prefs.custom_frequency_minutes or 30)),
    }.get(prefs.frequency if prefs else "every_30_min", tr(lang, "interval_30"))


def setup_schedule_context(prefs, lang: str, prompt: str) -> str:
    selected = parse_selected(prefs.selected_athkar if prefs else None)
    names = "، ".join(selected_names(selected, lang, prefs)) or tr(lang, "empty_athkar")
    choice = tr(lang, "setup_choice_athkar").replace("{value}", names)
    return f"☑️ {tr(lang, 'setup_progress_1')}\n• {choice}\n\n{prompt}"


def setup_schedule_prompt(prefs, lang: str) -> str:
    return setup_schedule_context(prefs, lang, tr(lang, "setup_step_schedule"))


def setup_delivery_context(prefs, lang: str, prompt: str) -> str:
    schedule_choice = tr(lang, "setup_choice_schedule").replace("{value}", frequency_label(prefs, lang))
    return (
        f"{setup_schedule_context(prefs, lang, '').rstrip()}\n\n"
        f"☑️ {tr(lang, 'setup_progress_2')}\n• {schedule_choice}\n\n"
        f"{prompt}"
    )


def setup_delivery_prompt(prefs, lang: str) -> str:
    return setup_delivery_context(prefs, lang, tr(lang, "setup_step_delivery"))


def setup_quiet_context(prefs, lang: str, prompt: str) -> str:
    delivery = delivery_label(prefs, lang)
    delivery_choice = tr(lang, "setup_choice_delivery").replace("{value}", delivery)
    return (
        f"{setup_delivery_context(prefs, lang, '').rstrip()}\n\n"
        f"☑️ {tr(lang, 'setup_progress_3')}\n• {delivery_choice}\n\n"
        f"{prompt}"
    )


def setup_quiet_prompt(prefs, lang: str) -> str:
    return setup_quiet_context(prefs, lang, tr(lang, "setup_step_quiet"))


def find_athkar(athkar_id: str, prefs=None):
    for item in all_athkar_options(prefs):
        if item["id"] == athkar_id:
            return item
    return None


def is_daily_goal(prefs) -> bool:
    return bool(prefs and prefs.frequency in {"goal_per_day", "goal_per_athkar"})


def delivery_label(prefs, lang: str) -> str:
    mode = getattr(prefs, "delivery_mode", "sequential") or "sequential"
    if mode == "batch":
        return tr(lang, "delivery_batch")
    if mode == "random":
        return tr(lang, "delivery_random")
    if mode == "complete":
        return tr(lang, "delivery_complete")
    return tr(lang, "delivery_sequential")


def frequency_to_seconds(frequency: str, custom_minutes: int | None) -> int:
    if frequency == "every_5_min":
        return 300
    if frequency == "hourly":
        return 3600
    if frequency == "goal_per_day":
        return 300
    if frequency == "custom_interval" and custom_minutes:
        return max(60, custom_minutes * 60)
    return 1800


async def send_or_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text_value: str,
    reply_markup,
    *,
    parse_mode: str | None = None,
):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=text_value, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as exc:
            if "Message is not modified" not in str(exc):
                raise
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text_value,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name
    prefs = await get_user_prefs(user_id)
    lang = normalize_lang(prefs.language if prefs else None, "ar")
    context.user_data["lang"] = lang
    prefs = await upsert_user_prefs(user_id, first_name, language=lang)

    if not prefs.onboarding_complete:
        context.user_data["onboarding"] = True
        await send_or_edit(update, context, tr(lang, "onboarding_language_title"), language_menu(lang, show_back=False))
        return

    await send_or_edit(update, context, tr(lang, "welcome"), home_menu(lang), parse_mode=ParseMode.MARKDOWN)


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(
        text=tr(lang, "welcome"),
        reply_markup=home_menu(lang),
        parse_mode=ParseMode.MARKDOWN,
    )


async def close_to_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close a completed setup screen without leaving stale bot messages behind."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    try:
        await query.delete_message()
    except BadRequest:
        pass


async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask before irreversibly clearing personal Athkar and timing choices."""
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(
        text=tr(lang, "reset_confirmation"),
        reply_markup=reset_confirmation_menu(lang),
    )


async def execute_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.from_user:
        return
    await reset_user_preferences(str(query.from_user.id))
    await rebuild_user_schedule(context)
    context.user_data.clear()
    context.user_data["lang"] = "ar"
    context.user_data["onboarding"] = True
    await query.edit_message_text(
        text=tr("ar", "onboarding_language_title"),
        reply_markup=language_menu("ar", show_back=False),
    )


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    chat_type = update.effective_chat.type if update.effective_chat else "unknown"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{UI_BUILD}\nchat_type={chat_type}\nmodule=user_side_app.handlers",
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.from_user:
        return

    lang = normalize_lang(query.data.replace("lang_", ""), "ar")
    context.user_data["lang"] = lang
    await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, language=lang)
    if context.user_data.get("onboarding"):
        context.user_data.pop("onboarding", None)
        await update_user_settings(str(query.from_user.id), onboarding_complete=True)
        await query.edit_message_text(text=tr(lang, "welcome"), reply_markup=home_menu(lang), parse_mode=ParseMode.MARKDOWN)
        return
    await query.edit_message_text(text=tr(lang, "welcome"), reply_markup=home_menu(lang), parse_mode=ParseMode.MARKDOWN)


async def present_timezone_setup(query, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """Reuse the current setup message; only the temporary location prompt is separate."""
    context.user_data["awaiting_timezone_setup"] = True
    context.user_data["timezone_main_message_id"] = query.message.message_id
    await query.edit_message_text(
        text=f"{tr(lang, 'timezone_title')}\n\n{tr(lang, 'prayer_prompt_help')}\n\n{tr(lang, 'prayer_prompt_privacy')}",
        reply_markup=locality_setup_menu(
            lang,
            context.user_data.get(
                "timezone_back_callback",
                "cfg_personal_setup" if context.user_data.get("resume_after_timezone") else "home",
            ),
        ),
    )
    location_prompt = await context.bot.send_message(
        chat_id=query.from_user.id,
        text=tr(lang, "share_location_now"),
        reply_markup=location_request_keyboard(lang),
    )
    context.user_data["timezone_location_prompt_id"] = location_prompt.message_id


async def resolve_timezone_from_coords(latitude: float, longitude: float):
    # This local lookup is immediate and avoids leaving the user waiting on a web API.
    timezone_name = detect_timezone_from_location(latitude, longitude)
    if timezone_name:
        return timezone_name

    open_meteo_url = "https://api.open-meteo.com/v1/forecast"
    open_meteo_params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m",
        "forecast_days": 1,
        "timezone": "auto",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(open_meteo_url, params=open_meteo_params, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    timezone_name = data.get("timezone")
                    if timezone_name:
                        return timezone_name
    except Exception:
        logger.exception("Open-Meteo timezone lookup failed")

    aladhan_url = "https://api.aladhan.com/v1/timings"
    aladhan_params = {"latitude": latitude, "longitude": longitude, "method": 3}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(aladhan_url, params=aladhan_params, timeout=15) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("data", {}).get("meta", {}).get("timezone")
    except Exception:
        logger.exception("Aladhan timezone lookup failed")
        return None


async def resolve_city_label_from_coords(latitude: float, longitude: float):
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": latitude, "lon": longitude, "format": "jsonv2"}
    headers = {"User-Agent": "muthaker-bot/1.0"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                address = data.get("address", {})
                return address.get("city") or address.get("town") or address.get("village") or address.get("state")
    except Exception:
        logger.exception("Reverse geocoding failed")
        return None


async def open_language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(text=tr(lang, "lang_menu"), reply_markup=language_menu(lang))


async def choose_personal_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if query.from_user:
        await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, mode="personal")
    context.user_data["active_mode"] = "personal"
    await query.edit_message_text(text=tr(lang, "personal_menu"), reply_markup=personal_menu(lang))


async def begin_personal_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the compact, ordered configuration journey."""
    query = update.callback_query
    await query.answer()
    for key in (
        "awaiting_custom_athkar_name", "awaiting_custom_athkar_text",
        "custom_athkar_name", "custom_athkar_prompt_id",
    ):
        context.user_data.pop(key, None)
    context.user_data["setup_flow"] = True
    await open_personal_athkar(update, context)


async def open_personal_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)
    prefs = await get_user_prefs(user_id)
    if "draft_selected" not in context.user_data:
        context.user_data["draft_selected"] = parse_selected(prefs.selected_athkar if prefs else None)
    await render_athkar_selection(query, context, lang)


async def render_athkar_selection(query, context: ContextTypes.DEFAULT_TYPE, lang: str):
    context.user_data["athkar_menu_message_id"] = query.message.message_id
    context.user_data["athkar_menu_chat_id"] = query.message.chat_id
    await render_athkar_selection_card(
        context,
        query.message.chat_id,
        query.message.message_id,
        str(query.from_user.id),
        lang,
    )


async def render_athkar_selection_card(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    user_id: str,
    lang: str,
):
    """Render the persistent setup card after a toggle or a custom addition."""
    selected = context.user_data.get("draft_selected", [])
    key = "en" if lang == "en" else "ar"
    prefs = await get_user_prefs(user_id)
    items = [(x["id"], x[key], x["id"] in selected) for x in all_athkar_options(prefs)]
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=tr(lang, "athkar_menu_title"),
            reply_markup=athkar_select_menu(lang, items),
        )
    except BadRequest as exc:
        if "Message is not modified" not in str(exc):
            raise


async def toggle_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    athkar_id = query.data.replace("athkar_toggle_", "")
    selected = context.user_data.setdefault("draft_selected", [])
    if athkar_id in selected:
        selected.remove(athkar_id)
    else:
        selected.append(athkar_id)

    await render_athkar_selection(query, context, lang)


async def select_all_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prefs = await get_user_prefs(str(query.from_user.id))
    context.user_data["draft_selected"] = [x["id"] for x in all_athkar_options(prefs)]
    await render_athkar_selection(query, context, get_lang(context))


async def begin_custom_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect a user-defined Athkar name and its message text in two clear steps."""
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    context.user_data["awaiting_custom_athkar_name"] = True
    context.user_data["athkar_menu_message_id"] = query.message.message_id
    context.user_data["athkar_menu_chat_id"] = query.message.chat_id
    await query.edit_message_text(
        text=tr(lang, "custom_athkar_name_prompt"),
        reply_markup=custom_athkar_prompt_menu(lang),
    )


async def clear_all_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["draft_selected"] = []
    await render_athkar_selection(query, context, get_lang(context))


async def save_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)
    selected = context.user_data.get("draft_selected", [])
    if not selected:
        prefs = await get_user_prefs(user_id)
        key = "en" if lang == "en" else "ar"
        items = [(x["id"], x[key], False) for x in all_athkar_options(prefs)]
        await query.edit_message_text(text=tr(lang, "need_athkar"), reply_markup=athkar_select_menu(lang, items))
        return
    await update_user_settings(user_id, selected_athkar=json.dumps(selected))
    prefs = await get_user_prefs(user_id)
    await rebuild_user_schedule(context)
    if context.user_data.get("setup_flow"):
        await query.edit_message_text(text=setup_schedule_prompt(prefs, lang), reply_markup=schedule_menu(lang))
        return
    await query.edit_message_text(text=tr(lang, "athkar_saved"), reply_markup=personal_menu(lang))


async def open_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    prefs = await get_user_prefs(str(query.from_user.id))
    text_value = setup_schedule_prompt(prefs, lang) if context.user_data.get("setup_flow") else tr(lang, "strategy_menu_title")
    await query.edit_message_text(text=text_value, reply_markup=schedule_menu(lang))


async def set_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)
    prefs = await get_user_prefs(user_id)

    if query.data == "schedule_strategy_interval":
        text_value = (
            setup_schedule_context(prefs, lang, tr(lang, "schedule_menu_title"))
            if context.user_data.get("setup_flow") else tr(lang, "schedule_menu_title")
        )
        await query.edit_message_text(text=text_value, reply_markup=interval_menu(lang))
        return

    if query.data == "schedule_strategy_goal":
        text_value = (
            setup_schedule_context(prefs, lang, tr(lang, "goal_menu_title"))
            if context.user_data.get("setup_flow") else tr(lang, "goal_menu_title")
        )
        await query.edit_message_text(text=text_value, reply_markup=goal_scope_menu(lang))
        return

    if query.data == "schedule_custom":
        context.user_data["awaiting_custom_interval"] = True
        text_value = (
            setup_schedule_context(prefs, lang, tr(lang, "prompt_custom_interval"))
            if context.user_data.get("setup_flow") else tr(lang, "prompt_custom_interval")
        )
        await query.edit_message_text(text=text_value, reply_markup=interval_menu(lang))
        return

    mapping = {
        "schedule_every_5": "every_5_min",
        "schedule_every_30": "every_30_min",
        "schedule_hourly": "hourly",
    }
    frequency = mapping.get(query.data, "every_30_min")
    await update_user_settings(user_id, frequency=frequency, custom_frequency_minutes=None, daily_goal_count=None)
    await rebuild_user_schedule(context)
    await continue_after_schedule(query, context, lang)


async def choose_goal_scope(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    scope = query.data.removeprefix("goal_scope_")
    prefs = await get_user_prefs(str(query.from_user.id))
    if scope == "total":
        text_value = (
            setup_schedule_context(prefs, lang, tr(lang, "goal_scope_total_title"))
            if context.user_data.get("setup_flow") else tr(lang, "goal_scope_total_title")
        )
        await query.edit_message_text(text=text_value, reply_markup=goal_menu(lang, "total"))
        return
    if scope == "each":
        text_value = (
            setup_schedule_context(prefs, lang, tr(lang, "goal_scope_each_title"))
            if context.user_data.get("setup_flow") else tr(lang, "goal_scope_each_title")
        )
        await query.edit_message_text(text=text_value, reply_markup=goal_menu(lang, "each"))
        return
    if scope == "advanced":
        selected = parse_selected(prefs.selected_athkar if prefs else None)
        if not selected:
            await query.edit_message_text(text=tr(lang, "need_athkar"), reply_markup=athkar_select_menu(lang, []))
            return
        context.user_data["advanced_goal_ids"] = selected
        context.user_data["advanced_goal_values"] = {}
        context.user_data["advanced_goal_index"] = 0
        await render_advanced_goal(query, context, lang)


async def render_advanced_goal(query, context: ContextTypes.DEFAULT_TYPE, lang: str):
    selected = context.user_data.get("advanced_goal_ids", [])
    index = context.user_data.get("advanced_goal_index", 0)
    if index >= len(selected):
        values = context.user_data.get("advanced_goal_values", {})
        await finish_goal_setup(query, context, lang, "advanced", values)
        return
    prefs = await get_user_prefs(str(query.from_user.id))
    athkar = find_athkar(selected[index], prefs)
    name = athkar["ar" if lang == "ar" else "en"] if athkar else selected[index]
    prompt = tr(lang, "advanced_goal_title").replace("{name}", name).replace("{position}", str(index + 1)).replace("{total}", str(len(selected)))
    text_value = setup_schedule_context(prefs, lang, prompt) if context.user_data.get("setup_flow") else prompt
    await query.edit_message_text(text=text_value, reply_markup=advanced_goal_menu(lang))


async def set_goal_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    raw = query.data.removeprefix("goal_")
    scope, value = raw.split("_", 1)
    if value == "custom":
        context.user_data["awaiting_custom_goal_scope"] = scope
        prefs = await get_user_prefs(str(query.from_user.id))
        text_value = (
            setup_schedule_context(prefs, lang, tr(lang, "prompt_custom_goal"))
            if context.user_data.get("setup_flow") else tr(lang, "prompt_custom_goal")
        )
        await query.edit_message_text(text=text_value, reply_markup=goal_menu(lang, scope))
        return
    await finish_goal_setup(query, context, lang, scope, int(value))


async def set_advanced_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    raw = query.data.removeprefix("goal_adv_")
    lang = get_lang(context)
    if raw == "custom":
        context.user_data["awaiting_advanced_goal"] = True
        prefs = await get_user_prefs(str(query.from_user.id))
        text_value = (
            setup_schedule_context(prefs, lang, tr(lang, "prompt_custom_goal"))
            if context.user_data.get("setup_flow") else tr(lang, "prompt_custom_goal")
        )
        await query.edit_message_text(text=text_value, reply_markup=advanced_goal_menu(lang))
        return
    await apply_advanced_goal_value(query, context, lang, int(raw))


async def apply_advanced_goal_value(query, context: ContextTypes.DEFAULT_TYPE, lang: str, value: int):
    selected = context.user_data.get("advanced_goal_ids", [])
    index = context.user_data.get("advanced_goal_index", 0)
    if index >= len(selected):
        return
    context.user_data.setdefault("advanced_goal_values", {})[selected[index]] = value
    context.user_data["advanced_goal_index"] = index + 1
    await render_advanced_goal(query, context, lang)


async def finish_goal_setup(query, context: ContextTypes.DEFAULT_TYPE, lang: str, scope: str, value):
    user_id = str(query.from_user.id)
    selected = context.user_data.get("draft_selected")
    if selected is None:
        prefs = await get_user_prefs(user_id)
        selected = parse_selected(prefs.selected_athkar if prefs else None)
    if scope == "total":
        await update_user_settings(
            user_id, frequency="goal_per_day", daily_goal_count=int(value), daily_goal_per_athkar="{}",
            custom_frequency_minutes=None,
        )
    else:
        per_athkar = value if isinstance(value, dict) else {athkar_id: int(value) for athkar_id in selected}
        await update_user_settings(
            user_id, frequency="goal_per_athkar", daily_goal_count=sum(per_athkar.values()),
            daily_goal_per_athkar=json.dumps(per_athkar), custom_frequency_minutes=None,
        )
    for key in ("advanced_goal_ids", "advanced_goal_values", "advanced_goal_index"):
        context.user_data.pop(key, None)
    await rebuild_user_schedule(context)
    await continue_after_schedule(query, context, lang)


async def continue_after_schedule(query, context: ContextTypes.DEFAULT_TYPE, lang: str):
    if context.user_data.get("setup_flow"):
        prefs = await get_user_prefs(str(query.from_user.id))
        await query.edit_message_text(
            text=setup_delivery_prompt(prefs, lang),
            reply_markup=delivery_menu(lang, is_daily_goal(prefs)),
        )
    else:
        await query.edit_message_text(text=tr(lang, "saved"), reply_markup=personal_menu(lang))


async def open_delivery_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    prefs = await get_user_prefs(str(query.from_user.id))
    text_value = setup_delivery_prompt(prefs, lang) if context.user_data.get("setup_flow") else tr(lang, "delivery_menu_title")
    await query.edit_message_text(text=text_value, reply_markup=delivery_menu(lang, is_daily_goal(prefs)))


async def open_quiet_hours_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    prefs = await get_user_prefs(str(query.from_user.id))
    text_value = setup_quiet_prompt(prefs, lang) if context.user_data.get("setup_flow") else tr(lang, "quiet_hours_title")
    await query.edit_message_text(text=text_value, reply_markup=quiet_hours_menu(lang))


async def set_quiet_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset = query.data.removeprefix("quiet_")
    if preset == "custom":
        context.user_data["awaiting_custom_quiet_hours"] = True
        lang = get_lang(context)
        prefs = await get_user_prefs(str(query.from_user.id))
        text_value = (
            setup_quiet_context(prefs, lang, tr(lang, "quiet_custom_prompt"))
            if context.user_data.get("setup_flow") else tr(lang, "quiet_custom_prompt")
        )
        await query.edit_message_text(text=text_value, reply_markup=quiet_hours_menu(lang))
        return
    dynamic = {
        "fajr_isha": (0, 0), "sleep_10_fajr": (22, 5),
        "sleep_11_fajr": (23, 5), "sleep_12_fajr": (0, 5), "sleep_1_fajr": (1, 5),
    }
    if preset not in QUIET_HOUR_PRESETS and preset not in dynamic:
        return
    prefs = await get_user_prefs(str(query.from_user.id))
    if preset in dynamic and not (prefs and prefs.prayer_city):
        # Reuse the privacy-preserving location flow.  Sharing is the easy
        # route; entering a city remains available in the keyboard field.
        context.user_data["timezone_pending_quiet_preset"] = preset
        context.user_data["resume_after_timezone"] = "personal_quiet"
        context.user_data["timezone_back_callback"] = "cfg_personal_delivery"
        await present_timezone_setup(query, context, get_lang(context))
        return
    start, end = dynamic.get(preset, QUIET_HOUR_PRESETS.get(preset, (23, 6)))
    await update_user_settings(str(query.from_user.id), quiet_hours_preset=preset, quiet_start_hour=start, quiet_end_hour=end, quiet_start_minute=0, quiet_end_minute=0)
    await rebuild_user_schedule(context)
    lang = get_lang(context)
    if context.user_data.pop("setup_flow", False):
        prefs = await get_user_prefs(str(query.from_user.id))
        text_value = setup_summary_text(prefs, lang)
        await query.edit_message_text(text=text_value, reply_markup=setup_complete_menu(lang))
    else:
        await query.edit_message_text(text=tr(lang, "saved"), reply_markup=personal_menu(lang))


def setup_summary_text(prefs, lang: str) -> str:
    selected = parse_selected(prefs.selected_athkar if prefs else None)
    names = "، ".join(selected_names(selected, lang, prefs)) or tr(lang, "empty_athkar")
    schedule = frequency_label(prefs, lang)
    quiet = quiet_hours_label(prefs, lang)
    return (
        f"🎉 {tr(lang, 'setup_ready_title')}\n"
        f"{tr(lang, 'setup_ready_intro')}\n\n"
        f"📿 {tr(lang, 'field_athkar')}: {names}\n"
        f"⏳ {tr(lang, 'field_schedule')}: {schedule}\n"
        f"📨 {tr(lang, 'field_delivery')}: {delivery_label(prefs, lang)}\n"
        f"🌙 {tr(lang, 'cfg_quiet_hours')}: {quiet}"
    )


async def setup_summary_with_locality(prefs, lang: str) -> str:
    """Confirm local timing and the prayer anchors in the original setup card."""
    timezone_name = prefs.timezone or "Africa/Cairo"
    confirmation = f"☑️ {tr(lang, 'setup_timezone_selected').replace('{timezone}', timezone_name)}"
    if prefs.prayer_city:
        try:
            now = datetime.now(pytz.timezone(timezone_name))
            timings = await fetch_prayer_times_by_city(prefs.prayer_city, now.date())
        except Exception:
            logger.exception("Could not fetch setup prayer-time confirmation")
            timings = None
        if timings and timings.get("Fajr") and timings.get("Isha"):
            line = tr(lang, "setup_prayer_times")
            line = line.replace("{city}", prefs.prayer_city).replace("{fajr}", timings["Fajr"]).replace("{isha}", timings["Isha"])
            confirmation += f"\n🕌 {line}"
    return f"{confirmation}\n\n{setup_summary_text(prefs, lang)}"


async def begin_timezone_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await present_timezone_setup(query, context, lang)


async def set_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)
    mode = {
        "delivery_batch": "batch",
        "delivery_random": "random",
        "delivery_complete": "complete",
        "delivery_sequential": "sequential",
        # Compatibility for an older open Telegram card.
        "delivery_rotating": "sequential",
    }.get(query.data, "sequential")
    await update_user_settings(user_id, delivery_mode=mode)
    await rebuild_user_schedule(context)
    if context.user_data.get("setup_flow"):
        prefs = await get_user_prefs(user_id)
        await query.edit_message_text(text=setup_quiet_prompt(prefs, lang), reply_markup=quiet_hours_menu(lang))
    else:
        await query.edit_message_text(text=tr(lang, "saved"), reply_markup=personal_menu(lang))


async def show_personal_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    prefs = await get_user_prefs(str(query.from_user.id))
    selected = parse_selected(prefs.selected_athkar if prefs else None)
    names = selected_names(selected, lang, prefs)

    frequency_label = {
        "every_5_min": tr(lang, "interval_5"),
        "every_30_min": tr(lang, "interval_30"),
        "hourly": tr(lang, "interval_60"),
        "custom_interval": f"{prefs.custom_frequency_minutes or 30} min",
        "goal_per_day": f"{prefs.daily_goal_count or 100} / day",
        "goal_per_athkar": tr(lang, "daily_goal_each_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
    }.get((prefs.frequency if prefs else "every_30_min"), tr(lang, "interval_30"))

    delivery_label_value = delivery_label(prefs, lang)
    prayer_label = tr(lang, "prayer_on") if prefs and prefs.prayer_athkar_enabled else tr(lang, "prayer_off")
    city = prefs.prayer_city if prefs and prefs.prayer_city else "-"
    timezone_name = prefs.timezone if prefs and prefs.timezone else "Africa/Cairo"
    athkar_lines = "\n".join([f"- {n}" for n in names]) if names else tr(lang, "empty_athkar")

    text_value = (
        f"{tr(lang, 'settings_title')}\n\n"
        f"{tr(lang, 'field_athkar')}:\n{athkar_lines}\n\n"
        f"{tr(lang, 'field_schedule')}: {frequency_label}\n"
        f"{tr(lang, 'field_delivery')}: {delivery_label_value}\n"
        f"{tr(lang, 'field_prayer')}: {prayer_label}\n"
        f"{tr(lang, 'cfg_quiet_hours')}: {quiet_hours_label(prefs, lang)}\n"
        f"{tr(lang, 'field_city')}: {city}\n"
        f"{tr(lang, 'field_timezone')}: {timezone_name}"
    )
    await query.edit_message_text(text=text_value, reply_markup=personal_menu(lang))


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Expose the same settings view through Telegram's command menu."""
    if not update.effective_user or not update.message:
        return
    prefs = await get_user_prefs(str(update.effective_user.id))
    lang = normalize_lang(prefs.language if prefs else None, "ar")
    context.user_data["lang"] = lang
    selected = parse_selected(prefs.selected_athkar if prefs else None)
    names = selected_names(selected, lang, prefs)
    frequency_label = {
        "every_5_min": tr(lang, "interval_5"), "every_30_min": tr(lang, "interval_30"),
        "hourly": tr(lang, "interval_60"),
        "custom_interval": tr(lang, "custom_interval_summary").replace("{minutes}", str(prefs.custom_frequency_minutes or 30)),
        "goal_per_day": tr(lang, "daily_goal_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
        "goal_per_athkar": tr(lang, "daily_goal_each_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
    }.get(prefs.frequency if prefs else "every_30_min", tr(lang, "interval_30"))
    text_value = (
        f"{tr(lang, 'settings_title')}\n\n"
        f"{tr(lang, 'field_athkar')}: {', '.join(names) or tr(lang, 'empty_athkar')}\n"
        f"{tr(lang, 'field_schedule')}: {frequency_label}\n"
        f"{tr(lang, 'cfg_quiet_hours')}: {quiet_hours_label(prefs, lang)}"
    )
    await update.message.reply_text(text_value, reply_markup=personal_menu(lang))


async def edit_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the personal-settings hub from Telegram's native command menu."""
    if not update.effective_user or not update.message:
        return
    prefs = await get_user_prefs(str(update.effective_user.id))
    lang = normalize_lang(prefs.language if prefs else None, "ar")
    context.user_data["lang"] = lang
    context.user_data["active_mode"] = "personal"
    await upsert_user_prefs(str(update.effective_user.id), update.effective_user.first_name, mode="personal")
    await update.message.reply_text(tr(lang, "personal_menu"), reply_markup=personal_menu(lang))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Give users a concise, practical route back into the bot."""
    if not update.effective_user or not update.message:
        return
    prefs = await get_user_prefs(str(update.effective_user.id))
    lang = normalize_lang(prefs.language if prefs else None, "ar")
    context.user_data["lang"] = lang
    await update.message.reply_text(tr(lang, "help_text"), reply_markup=home_menu(lang))


async def toggle_prayer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)
    prefs = await get_user_prefs(user_id)

    if prefs and prefs.prayer_athkar_enabled:
        await update_user_settings(user_id, prayer_athkar_enabled=False)
        await rebuild_user_schedule(context)
        await query.edit_message_text(text=tr(lang, "prayer_disabled_done"), reply_markup=personal_menu(lang))
        return

    # A previously resolved city can enable the feature immediately.
    if prefs and prefs.timezone and prefs.prayer_city:
        await update_user_settings(user_id, prayer_athkar_enabled=True, timezone_confirmed=True)
        await rebuild_user_schedule(context)
        await query.edit_message_text(
            text=morning_evening_ready_text(lang, prefs.prayer_city, prefs.timezone),
            reply_markup=personal_menu(lang),
        )
        return

    # Otherwise one location share (or a typed city) resolves both local time
    # and the city needed for the morning/evening schedule.
    context.user_data["awaiting_prayer_setup"] = True
    context.user_data["timezone_main_message_id"] = query.message.message_id
    await query.edit_message_text(
        text=f"{tr(lang, 'cfg_prayer')}\n\n{tr(lang, 'prayer_prompt_help')}\n\n{tr(lang, 'prayer_prompt_privacy')}\n\n{tr(lang, 'prayer_prompt_city')}",
        reply_markup=locality_setup_menu(lang, "mode_personal"),
    )
    location_prompt = await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"{tr(lang, 'cfg_prayer')}\n\n{tr(lang, 'prayer_prompt_help')}",
        reply_markup=location_request_keyboard(lang),
    )
    context.user_data["timezone_location_prompt_id"] = location_prompt.message_id


def morning_evening_ready_text(lang: str, city: str, timezone_name: str) -> str:
    return (
        f"{tr(lang, 'prayer_enabled_done')}\n"
        f"☑️ {tr(lang, 'setup_timezone_selected').replace('{timezone}', timezone_name)}\n"
        f"📍 {tr(lang, 'prayer_city_saved').replace('{city}', city)}\n\n"
        f"{tr(lang, 'morning_evening_schedule')}"
    )


async def complete_morning_evening_setup(update: Update, context: ContextTypes.DEFAULT_TYPE, *, city: str, timezone_name: str):
    """Persist one resolved city and activate both morning and evening sends."""
    lang = get_lang(context)
    user_id = str(update.effective_user.id)
    await update_user_settings(
        user_id,
        prayer_athkar_enabled=True,
        prayer_city=city,
        timezone=timezone_name,
        timezone_confirmed=True,
    )
    await rebuild_user_schedule(context)
    context.user_data.pop("awaiting_prayer_setup", None)
    text_value = morning_evening_ready_text(lang, city, timezone_name)
    main_message_id = context.user_data.pop("timezone_main_message_id", None)
    prompt_message_id = context.user_data.pop("timezone_location_prompt_id", None)
    try:
        await update.message.delete()
        if prompt_message_id:
            await context.bot.delete_message(update.effective_chat.id, prompt_message_id)
        keyboard_reset = await context.bot.send_message(
            chat_id=update.effective_chat.id, text=".", reply_markup=ReplyKeyboardRemove(),
        )
        await keyboard_reset.delete()
    except Exception:
        logger.debug("Could not remove temporary morning/evening setup messages", exc_info=True)
    if main_message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=main_message_id,
                text=text_value, reply_markup=personal_menu(lang),
            )
            return
        except BadRequest:
            logger.debug("Could not update morning/evening setup message", exc_info=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text_value, reply_markup=personal_menu(lang))


async def city_to_coords(city: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city, "format": "jsonv2", "limit": 1}
    headers = {"User-Agent": "muthaker-bot/1.0"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                return None, None, None
            data = await resp.json()
            if not data:
                return None, None, None
            top = data[0]
            return float(top["lat"]), float(top["lon"]), top.get("display_name", city)


async def begin_community_location_setup(query, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """Ask for a one-time location share, keeping a typed city as the fallback."""
    context.user_data["awaiting_target_location"] = True
    context.user_data["target_location_main_message_id"] = query.message.message_id
    await query.edit_message_text(text=tr(lang, "community_location_prompt"), reply_markup=community_connect_menu(lang))
    prompt = await context.bot.send_message(
        chat_id=query.from_user.id,
        text=tr(lang, "community_location_prompt"),
        reply_markup=location_request_keyboard(lang),
    )
    context.user_data["target_location_prompt_id"] = prompt.message_id


async def complete_community_location(update: Update, context: ContextTypes.DEFAULT_TYPE, *, latitude: float, longitude: float, city: str | None, timezone_name: str):
    """Persist only derived city/timezone and reopen the configured target."""
    lang = get_lang(context)
    user_id = str(update.effective_user.id)
    target = await get_target(user_id, context.user_data.get("selected_target_id", ""))
    if not target:
        return
    if not city:
        context.user_data.pop("awaiting_target_location", None)
        context.user_data["awaiting_target_city"] = True
        await update.message.reply_text(tr(lang, "community_city_prompt"), reply_markup=ReplyKeyboardRemove())
        return
    target = await update_target_settings(
        user_id, target.chat_id, city=city, timezone=timezone_name,
    )
    context.user_data.pop("awaiting_target_location", None)
    context.user_data.pop("awaiting_target_city", None)
    timings = await fetch_prayer_times(city, datetime.now(pytz.timezone(timezone_name)).date(), target.prayer_method or 3, latitude, longitude)
    saved = tr(lang, "community_city_saved").replace("{target}", target.chat_title or target.chat_id).replace("{city}", city).replace("{timezone}", timezone_name)
    text_value = f"{saved}\n\n{format_community_prayer_times(lang, target, timings)}" if timings else f"{saved}\n\n{tr(lang, 'community_prayer_failed')}"

    main_message_id = context.user_data.pop("target_location_main_message_id", None)
    prompt_message_id = context.user_data.pop("target_location_prompt_id", None)
    try:
        await update.message.delete()
        if prompt_message_id:
            await context.bot.delete_message(update.effective_chat.id, prompt_message_id)
        keyboard_reset = await context.bot.send_message(chat_id=update.effective_chat.id, text=".", reply_markup=ReplyKeyboardRemove())
        await keyboard_reset.delete()
    except Exception:
        logger.debug("Could not remove temporary community location messages", exc_info=True)
    if main_message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id, message_id=main_message_id,
                text=text_value, reply_markup=community_menu(lang, target),
            )
            return
        except BadRequest:
            logger.debug("Could not update community location message", exc_info=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text_value, reply_markup=community_menu(lang, target))


async def handle_location_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.location or not update.effective_user:
        return
    if not (
        context.user_data.get("awaiting_prayer_setup")
        or context.user_data.get("awaiting_timezone_setup")
        or context.user_data.get("awaiting_target_location")
    ):
        return

    lang = get_lang(context)
    user_id = str(update.effective_user.id)
    latitude = update.message.location.latitude
    longitude = update.message.location.longitude

    timezone_name = await resolve_timezone_from_coords(latitude, longitude)

    if not timezone_name:
        await update.message.reply_text(tr(lang, "prayer_location_failed"), reply_markup=ReplyKeyboardRemove())
        return

    if context.user_data.get("awaiting_target_location"):
        city = await resolve_city_label_from_coords(latitude, longitude)
        await complete_community_location(
            update, context, latitude=latitude, longitude=longitude,
            city=city, timezone_name=timezone_name,
        )
        return

    if context.user_data.get("awaiting_prayer_setup"):
        city = await resolve_city_label_from_coords(latitude, longitude)
        if not city:
            await update.message.reply_text(tr(lang, "prayer_city_failed"))
            return
        await complete_morning_evening_setup(
            update, context, city=city, timezone_name=timezone_name,
        )
        return

    prayer_setup = context.user_data.pop("awaiting_prayer_setup", False)
    context.user_data.pop("awaiting_timezone_setup", None)
    onboarding = context.user_data.pop("onboarding", False)
    resume_after_timezone = context.user_data.pop("resume_after_timezone", None)
    context.user_data.pop("timezone_back_callback", None)
    # Coordinates are deliberately not persisted.  A city label lets Fajr-based
    # schedules work, while avoiding storage of the shared location itself.
    city = await resolve_city_label_from_coords(latitude, longitude)
    await update_user_settings(
        user_id,
        timezone=timezone_name,
        timezone_confirmed=True,
        prayer_city=city,
        onboarding_complete=True if onboarding else None,
    )
    if resume_after_timezone == "personal_quiet":
        preset = context.user_data.pop("timezone_pending_quiet_preset", None)
        if preset:
            start, end = {
                "fajr_isha": (0, 0), "sleep_10_fajr": (22, 5),
                "sleep_11_fajr": (23, 5), "sleep_12_fajr": (0, 5), "sleep_1_fajr": (1, 5),
            }[preset]
            await update_user_settings(
                user_id, quiet_hours_preset=preset, quiet_start_hour=start,
                quiet_end_hour=end, quiet_start_minute=0, quiet_end_minute=0,
            )
    await rebuild_user_schedule(context)
    if resume_after_timezone == "personal_setup":
        context.user_data["setup_flow"] = True
        prefs = await get_user_prefs(user_id)
        context.user_data["draft_selected"] = parse_selected(prefs.selected_athkar if prefs else None)
        selected = context.user_data["draft_selected"]
        key = "en" if lang == "en" else "ar"
        items = [(x["id"], x[key], x["id"] in selected) for x in all_athkar_options(prefs)]
        text_value = f"{tr(lang, 'timezone_success').replace('{timezone}', timezone_name)}\n\n{tr(lang, 'setup_step_athkar')}"
        reply_markup = athkar_select_menu(lang, items)
    elif resume_after_timezone == "personal_schedule":
        context.user_data["setup_flow"] = True
        prefs = await get_user_prefs(user_id)
        text_value = f"☑️ {tr(lang, 'setup_timezone_selected').replace('{timezone}', timezone_name)}\n\n{setup_schedule_prompt(prefs, lang)}"
        reply_markup = schedule_menu(lang)
    elif resume_after_timezone == "personal_quiet":
        prefs = await get_user_prefs(user_id)
        context.user_data.pop("setup_flow", None)
        text_value = await setup_summary_with_locality(prefs, lang)
        reply_markup = setup_complete_menu(lang)
    elif prayer_setup:
        context.user_data["awaiting_prayer_setup"] = True
        text_value = f"{tr(lang, 'prayer_timezone_detected').replace('{timezone}', timezone_name)}\n\n{tr(lang, 'prayer_prompt_city')}"
        reply_markup = personal_menu(lang)
    else:
        text_value = f"{tr(lang, 'timezone_success').replace('{timezone}', timezone_name)}\n\n{tr(lang, 'choose_mode')}"
        reply_markup = home_menu(lang)

    main_message_id = context.user_data.pop("timezone_main_message_id", None)
    prompt_message_id = context.user_data.pop("timezone_location_prompt_id", None)
    try:
        await update.message.delete()
        if prompt_message_id:
            await context.bot.delete_message(update.effective_chat.id, prompt_message_id)
        # Remove the one-time location keyboard without leaving a visible helper message.
        keyboard_reset = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=".",
            reply_markup=ReplyKeyboardRemove(),
        )
        await keyboard_reset.delete()
    except Exception:
        logger.debug("Could not delete timezone setup messages", exc_info=True)

    if main_message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=main_message_id,
                text=text_value,
                reply_markup=reply_markup,
            )
            return
        except BadRequest:
            logger.warning("Could not update timezone setup message", exc_info=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text_value, reply_markup=reply_markup)


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    lang = get_lang(context)
    user_id = str(update.effective_user.id)
    text_value = (update.message.text or "").strip()
    numeric_value = normalize_digits(text_value)

    if context.user_data.get("awaiting_custom_athkar_name"):
        if not text_value or len(text_value) > 80:
            await update.message.reply_text(tr(lang, "custom_athkar_name_invalid"))
            return
        context.user_data.pop("awaiting_custom_athkar_name", None)
        context.user_data["custom_athkar_name"] = text_value
        context.user_data["awaiting_custom_athkar_text"] = True
        prompt = await update.message.reply_text(
            tr(lang, "custom_athkar_text_prompt"),
            reply_markup=custom_athkar_prompt_menu(lang),
        )
        context.user_data["custom_athkar_prompt_id"] = prompt.message_id
        return

    if context.user_data.get("awaiting_custom_athkar_text"):
        if not text_value or len(text_value) > 3500:
            await update.message.reply_text(tr(lang, "custom_athkar_text_invalid"))
            return
        name = context.user_data.pop("custom_athkar_name", None)
        if not name:
            context.user_data.pop("awaiting_custom_athkar_text", None)
            await update.message.reply_text(tr(lang, "custom_athkar_restart"))
            return
        prefs = await get_user_prefs(user_id)
        custom_items = parse_custom_athkar(prefs.custom_athkar if prefs else None)
        custom_id = f"custom_{uuid4().hex[:12]}"
        custom_items.append({"id": custom_id, "name": name, "text": text_value})
        selected = context.user_data.setdefault(
            "draft_selected",
            parse_selected(prefs.selected_athkar if prefs else None),
        )
        if custom_id not in selected:
            selected.append(custom_id)
        await update_user_settings(
            user_id,
            custom_athkar=json.dumps(custom_items, ensure_ascii=False),
            selected_athkar=json.dumps(selected),
        )
        context.user_data.pop("awaiting_custom_athkar_text", None)
        prompt_id = context.user_data.pop("custom_athkar_prompt_id", None)
        if prompt_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=prompt_id)
            except BadRequest:
                pass
        menu_id = context.user_data.get("athkar_menu_message_id")
        menu_chat_id = context.user_data.get("athkar_menu_chat_id", update.effective_chat.id)
        if menu_id:
            await render_athkar_selection_card(context, menu_chat_id, menu_id, user_id, lang)
        else:
            fresh_prefs = await get_user_prefs(user_id)
            items = [
                (item["id"], item["ar" if lang == "ar" else "en"], item["id"] in selected)
                for item in all_athkar_options(fresh_prefs)
            ]
            await update.message.reply_text(tr(lang, "athkar_menu_title"), reply_markup=athkar_select_menu(lang, items))
        return

    if context.user_data.get("awaiting_custom_interval"):
        if not numeric_value.isdigit():
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        minutes = int(numeric_value)
        if minutes < 1 or minutes > 1440:
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        context.user_data["awaiting_custom_interval"] = False
        await update_user_settings(user_id, frequency="custom_interval", custom_frequency_minutes=minutes, daily_goal_count=None)
        await rebuild_user_schedule(context)
        if context.user_data.get("setup_flow"):
            prefs = await get_user_prefs(user_id)
            await update.message.reply_text(setup_delivery_prompt(prefs, lang), reply_markup=delivery_menu(lang, is_daily_goal(prefs)))
        else:
            await update.message.reply_text(tr(lang, "saved"))
        return

    if context.user_data.get("awaiting_custom_goal_scope"):
        if not numeric_value.isdigit():
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        goal_count = int(numeric_value)
        if goal_count < 1 or goal_count > 10000:
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        scope = context.user_data.pop("awaiting_custom_goal_scope")
        prefs = await get_user_prefs(user_id)
        selected = parse_selected(prefs.selected_athkar if prefs else None)
        if scope == "total":
            await update_user_settings(user_id, frequency="goal_per_day", daily_goal_count=goal_count, daily_goal_per_athkar="{}", custom_frequency_minutes=None)
        else:
            values = {athkar_id: goal_count for athkar_id in selected}
            await update_user_settings(user_id, frequency="goal_per_athkar", daily_goal_count=sum(values.values()), daily_goal_per_athkar=json.dumps(values), custom_frequency_minutes=None)
        await rebuild_user_schedule(context)
        if context.user_data.get("setup_flow"):
            prefs = await get_user_prefs(user_id)
            await update.message.reply_text(setup_delivery_prompt(prefs, lang), reply_markup=delivery_menu(lang, is_daily_goal(prefs)))
        else:
            await update.message.reply_text(tr(lang, "saved"))
        return

    if context.user_data.get("awaiting_advanced_goal"):
        if not numeric_value.isdigit() or not 1 <= int(numeric_value) <= 10000:
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        context.user_data.pop("awaiting_advanced_goal", None)
        selected = context.user_data.get("advanced_goal_ids", [])
        index = context.user_data.get("advanced_goal_index", 0)
        if index >= len(selected):
            return
        context.user_data.setdefault("advanced_goal_values", {})[selected[index]] = int(numeric_value)
        context.user_data["advanced_goal_index"] = index + 1
        index += 1
        if index >= len(selected):
            values = context.user_data.get("advanced_goal_values", {})
            await update_user_settings(user_id, frequency="goal_per_athkar", daily_goal_count=sum(values.values()), daily_goal_per_athkar=json.dumps(values), custom_frequency_minutes=None)
            for key in ("advanced_goal_ids", "advanced_goal_values", "advanced_goal_index"):
                context.user_data.pop(key, None)
            await rebuild_user_schedule(context)
            prefs = await get_user_prefs(user_id)
            await update.message.reply_text(setup_delivery_prompt(prefs, lang), reply_markup=delivery_menu(lang, is_daily_goal(prefs)))
            return
        prefs = await get_user_prefs(user_id)
        athkar = find_athkar(selected[index], prefs)
        name = athkar["ar" if lang == "ar" else "en"] if athkar else selected[index]
        prompt = tr(lang, "advanced_goal_title").replace("{name}", name).replace("{position}", str(index + 1)).replace("{total}", str(len(selected)))
        text_result = setup_schedule_context(prefs, lang, prompt) if context.user_data.get("setup_flow") else prompt
        await update.message.reply_text(text_result, reply_markup=advanced_goal_menu(lang))
        return

    if context.user_data.get("awaiting_custom_quiet_hours"):
        value = normalize_digits(text_value).replace(" ", "").replace("،", ",").replace(";", ",")
        values = [item for item in value.split(",") if item]
        periods: list[tuple[int, int]] = []
        for item in values:
            match = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", item)
            if not match:
                await update.message.reply_text(tr(lang, "quiet_custom_invalid"))
                return
            start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
            if start_hour > 23 or end_hour > 23 or start_minute > 59 or end_minute > 59:
                await update.message.reply_text(tr(lang, "quiet_custom_invalid"))
                return
            periods.append((start_hour * 60 + start_minute, end_hour * 60 + end_minute))
        if not periods:
            await update.message.reply_text(tr(lang, "quiet_custom_invalid"))
            return
        context.user_data.pop("awaiting_custom_quiet_hours", None)
        first_start, first_end = periods[0]
        await update_user_settings(
            user_id,
            quiet_hours_preset="custom",
            quiet_start_hour=first_start // 60,
            quiet_start_minute=first_start % 60,
            quiet_end_hour=first_end // 60,
            quiet_end_minute=first_end % 60,
            quiet_periods=json.dumps([list(period) for period in periods]),
        )
        await rebuild_user_schedule(context)
        prefs = await get_user_prefs(user_id)
        context.user_data.pop("setup_flow", None)
        await update.message.reply_text(setup_summary_text(prefs, lang), reply_markup=setup_complete_menu(lang))
        return

    if context.user_data.get("pending_quiet_preset"):
        lat, lon, display = await city_to_coords(text_value)
        if lat is None or lon is None:
            await update.message.reply_text(tr(lang, "prayer_city_failed"))
            return
        timezone_name = await resolve_timezone_from_coords(lat, lon)
        if not timezone_name:
            await update.message.reply_text(tr(lang, "prayer_city_failed"))
            return
        preset = context.user_data.pop("pending_quiet_preset")
        start, end = {"fajr_isha": (0, 0), "sleep_10_fajr": (22, 5), "sleep_11_fajr": (23, 5), "sleep_12_fajr": (0, 5), "sleep_1_fajr": (1, 5)}[preset]
        await update_user_settings(
            user_id, prayer_city=display.split(",")[0], timezone=timezone_name,
            quiet_hours_preset=preset, quiet_start_hour=start, quiet_end_hour=end, quiet_start_minute=0, quiet_end_minute=0,
        )
        await rebuild_user_schedule(context)
        prefs = await get_user_prefs(user_id)
        context.user_data.pop("setup_flow", None)
        await update.message.reply_text(setup_summary_text(prefs, lang), reply_markup=setup_complete_menu(lang))
        return

    if context.user_data.get("awaiting_community_post_text"):
        draft = context.user_data.get("draft_community_post")
        if not draft:
            context.user_data.pop("awaiting_community_post_text", None)
            return
        draft["text_content"] = text_value
        context.user_data.pop("awaiting_community_post_text", None)
        await update.message.reply_text(tr(lang, "post_schedule_title"), reply_markup=post_schedule_menu(lang))
        return

    if context.user_data.get("awaiting_community_post_clock"):
        time_value = normalize_digits(text_value).replace("٫", ":").replace("：", ":")
        if not re.fullmatch(r"\d{1,2}:\d{2}", time_value):
            await update.message.reply_text(tr(lang, "post_invalid_time"))
            return
        hour, minute = map(int, time_value.split(":"))
        if hour > 23 or minute > 59:
            await update.message.reply_text(tr(lang, "post_invalid_time"))
            return
        post = await save_community_post(update, context, schedule_type="clock", time_of_day=f"{hour:02d}:{minute:02d}")
        if not post:
            return
        target = await get_target(user_id, context.user_data.get("selected_target_id", ""))
        posts = await list_community_posts(user_id, target.chat_id)
        await update.message.reply_text(tr(lang, "post_saved"), reply_markup=community_posts_menu(lang, posts))
        return

    if context.user_data.get("awaiting_community_post_interval"):
        if not numeric_value.isdigit() or not 5 <= int(numeric_value) <= 1440:
            await update.message.reply_text(tr(lang, "post_prompt_interval"))
            return
        post = await save_community_post(update, context, schedule_type="interval", interval_minutes=int(numeric_value))
        if not post:
            return
        target = await get_target(user_id, context.user_data.get("selected_target_id", ""))
        posts = await list_community_posts(user_id, target.chat_id)
        await update.message.reply_text(tr(lang, "post_saved"), reply_markup=community_posts_menu(lang, posts))
        return

    if context.user_data.get("awaiting_target_city") or context.user_data.get("awaiting_target_location"):
        target = await get_target(user_id, context.user_data.get("selected_target_id", ""))
        if not target:
            context.user_data.pop("awaiting_target_city", None)
            context.user_data.pop("awaiting_target_location", None)
            await update.message.reply_text(tr(lang, "target_none"), reply_markup=community_connect_menu(lang))
            return
        lat, lon, display = await city_to_coords(text_value)
        if lat is None or lon is None:
            await update.message.reply_text(tr(lang, "community_city_failed"))
            return
        timezone_name = await resolve_timezone_from_coords(lat, lon)
        if not timezone_name:
            await update.message.reply_text(tr(lang, "community_city_failed"))
            return
        city_name = display.split(",")[0]
        if context.user_data.get("awaiting_target_location"):
            await complete_community_location(
                update, context, latitude=lat, longitude=lon,
                city=city_name, timezone_name=timezone_name,
            )
            return
        target = await update_target_settings(
            user_id, target.chat_id, city=city_name, timezone=timezone_name,
        )
        context.user_data.pop("awaiting_target_city", None)
        context.user_data.pop("awaiting_target_location", None)
        timings = await fetch_prayer_times(city_name, datetime.now(pytz.timezone(timezone_name)).date(), target.prayer_method or 3, lat, lon)
        saved = tr(lang, "community_city_saved").replace("{target}", target.chat_title or target.chat_id).replace("{city}", city_name).replace("{timezone}", timezone_name)
        if timings:
            await update.message.reply_text(
                f"{saved}\n\n{format_community_prayer_times(lang, target, timings)}",
                reply_markup=community_menu(lang, target),
            )
        else:
            await update.message.reply_text(f"{saved}\n\n{tr(lang, 'community_prayer_failed')}", reply_markup=community_menu(lang, target))
        return

    if context.user_data.get("awaiting_timezone_setup"):
        lat, lon, display = await city_to_coords(text_value)
        timezone_name = await resolve_timezone_from_coords(lat, lon) if lat is not None else None
        if not timezone_name:
            await update.message.reply_text(tr(lang, "prayer_city_failed"))
            return
        city = display.split(",")[0] if display else None
        context.user_data.pop("awaiting_timezone_setup", None)
        resume_after_timezone = context.user_data.pop("resume_after_timezone", None)
        context.user_data.pop("timezone_back_callback", None)
        await update_user_settings(
            user_id, timezone=timezone_name, timezone_confirmed=True, prayer_city=city,
        )
        if resume_after_timezone == "personal_quiet":
            preset = context.user_data.pop("timezone_pending_quiet_preset", None)
            if preset:
                start, end = {
                    "fajr_isha": (0, 0), "sleep_10_fajr": (22, 5),
                    "sleep_11_fajr": (23, 5), "sleep_12_fajr": (0, 5), "sleep_1_fajr": (1, 5),
                }[preset]
                await update_user_settings(
                    user_id, quiet_hours_preset=preset, quiet_start_hour=start,
                    quiet_end_hour=end, quiet_start_minute=0, quiet_end_minute=0,
                )
        await rebuild_user_schedule(context)
        if resume_after_timezone == "personal_schedule":
            context.user_data["setup_flow"] = True
            prefs = await get_user_prefs(user_id)
            text_result = f"☑️ {tr(lang, 'setup_timezone_selected').replace('{timezone}', timezone_name)}\n\n{setup_schedule_prompt(prefs, lang)}"
            reply_markup = schedule_menu(lang)
        elif resume_after_timezone == "personal_quiet":
            prefs = await get_user_prefs(user_id)
            context.user_data.pop("setup_flow", None)
            text_result = await setup_summary_with_locality(prefs, lang)
            reply_markup = setup_complete_menu(lang)
        else:
            text_result = f"{tr(lang, 'timezone_success').replace('{timezone}', timezone_name)}\n\n{tr(lang, 'choose_mode')}"
            reply_markup = home_menu(lang)
        main_message_id = context.user_data.pop("timezone_main_message_id", None)
        prompt_message_id = context.user_data.pop("timezone_location_prompt_id", None)
        try:
            await update.message.delete()
            if prompt_message_id:
                await context.bot.delete_message(update.effective_chat.id, prompt_message_id)
            keyboard_reset = await context.bot.send_message(
                chat_id=update.effective_chat.id, text=".", reply_markup=ReplyKeyboardRemove(),
            )
            await keyboard_reset.delete()
        except Exception:
            logger.debug("Could not remove temporary typed-city messages", exc_info=True)
        if main_message_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id, message_id=main_message_id,
                    text=text_result, reply_markup=reply_markup,
                )
                return
            except BadRequest:
                logger.debug("Could not update typed-city timezone message", exc_info=True)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text_result, reply_markup=reply_markup)
        return

    if context.user_data.get("awaiting_prayer_setup"):
        lat, lon, display = await city_to_coords(text_value)
        if lat is None or lon is None:
            await update.message.reply_text(tr(lang, "prayer_city_failed"))
            return
        timezone_name = await resolve_timezone_from_coords(lat, lon)
        if not timezone_name:
            await update.message.reply_text(tr(lang, "prayer_city_failed"))
            return
        await complete_morning_evening_setup(
            update, context, city=display.split(",")[0], timezone_name=timezone_name,
        )
        return


async def send_user_reminder(telegram_id: str):
    prefs = await get_user_prefs(telegram_id)
    if not prefs:
        return
    if await is_quiet_time(prefs):
        return
    selected = parse_selected(prefs.selected_athkar)
    if not selected:
        return
    lang = "ar" if prefs.language == "ar" else "en"
    if prefs.delivery_mode == "batch":
        ids = selected
    elif prefs.frequency == "goal_per_athkar":
        try:
            goal_map = json.loads(prefs.daily_goal_per_athkar or "{}")
        except Exception:
            goal_map = {}
        weighted = [athkar_id for athkar_id in selected for _ in range(max(1, int(goal_map.get(athkar_id, 1))))]
        if prefs.delivery_mode == "random":
            ids = [random.choice(weighted)]
        else:
            # A complete goal cycle groups repetitions of an Athkar together:
            # e.g. 50 of one Athkar, then the next, before starting over.
            idx = rotation_state.get(telegram_id, 0) % len(weighted)
            ids = [weighted[idx]]
            rotation_state[telegram_id] = (idx + 1) % len(weighted)
    elif prefs.delivery_mode == "random":
        ids = [random.choice(selected)]
    else:
        idx = rotation_state.get(telegram_id, 0) % len(selected)
        ids = [selected[idx]]
        rotation_state[telegram_id] = (idx + 1) % len(selected)

    application = get_application()
    if not application:
        logger.error("Cannot send user reminder: Telegram application is not ready")
        return

    messages = []
    for athkar_id in ids:
        item = find_athkar(athkar_id, prefs)
        if not item:
            continue
        text_key = "text_en" if lang == "en" else "text_ar"
        messages.append(item[text_key])
    if messages:
        await application.bot.send_message(chat_id=int(telegram_id), text="\n\n".join(messages))


async def fetch_prayer_times_by_city(city: str, target_date):
    # The coordinate-backed community fetcher also handles multi-word cities
    # such as San Francisco, unlike Aladhan's city-only endpoint.
    return await fetch_prayer_times(city, target_date, 3)


def parse_prayer_datetime(day, prayer_name: str, timings: dict, timezone_name: str):
    raw = timings.get(prayer_name)
    if not raw:
        return None
    hm = raw.split(" ")[0]
    h, m = map(int, hm.split(":"))
    tz = pytz.timezone(timezone_name or "Africa/Cairo")
    dt = datetime.combine(day, datetime.min.time().replace(hour=h, minute=m))
    return tz.localize(dt)


async def send_morning_evening_athkar(telegram_id: str, kind: str):
    application = get_application()
    if not application:
        logger.error("Cannot send morning/evening athkar: Telegram application is not ready")
        return
    filename = "أذكار_الصباح.jpg" if kind == "morning" else "أذكار_المساء.jpg"
    image_path = Path(__file__).resolve().parent.parent / "الأذكار" / filename
    if image_path.exists():
        with image_path.open("rb") as image:
            await application.bot.send_photo(chat_id=int(telegram_id), photo=image)
        return
    text = "🌅 أذكار الصباح" if kind == "morning" else "🌙 أذكار المساء"
    await application.bot.send_message(chat_id=int(telegram_id), text=text)


async def is_quiet_time(user) -> bool:
    """Evaluate the user's saved quiet hours in their own timezone."""
    if user.quiet_hours_preset == "none":
        return False
    try:
        local_now = datetime.now(pytz.timezone(user.timezone or "Africa/Cairo"))
    except Exception:
        local_now = datetime.now(CAIRO_TZ)
    if user.quiet_hours_preset in {"fajr_isha", "sleep_10_fajr", "sleep_11_fajr", "sleep_12_fajr", "sleep_1_fajr"} and user.prayer_city:
        cache_key = (user.prayer_city.casefold(), local_now.date().isoformat())
        timings = quiet_timing_cache.get(cache_key)
        if timings is None and cache_key not in quiet_timing_cache:
            timings = await fetch_prayer_times_by_city(user.prayer_city, local_now.date())
            if timings:
                quiet_timing_cache[cache_key] = timings
        if timings:
            fajr = parse_prayer_datetime(local_now.date(), "Fajr", timings, user.timezone or "Africa/Cairo")
            isha = parse_prayer_datetime(local_now.date(), "Isha", timings, user.timezone or "Africa/Cairo")
            if fajr:
                if user.quiet_hours_preset == "fajr_isha" and isha:
                    return local_now < fajr or local_now >= isha
                start_hour = {"sleep_10_fajr": 22, "sleep_11_fajr": 23, "sleep_12_fajr": 0, "sleep_1_fajr": 1}.get(user.quiet_hours_preset)
                if start_hour is not None:
                    return local_now < fajr or local_now.hour >= start_hour
        # A temporary provider failure must never turn the Isha-to-Fajr choice
        # into a full-day pause.  The next send retries the prayer lookup.
        if user.quiet_hours_preset == "fajr_isha":
            return False
    current = local_now.hour * 60 + local_now.minute
    if user.quiet_hours_preset == "custom":
        periods = parse_quiet_periods(getattr(user, "quiet_periods", None))
        if periods:
            return any(
                start <= current < end if start < end else current >= start or current < end
                for start, end in periods
            )
    start = (user.quiet_start_hour or 0) * 60 + (user.quiet_start_minute or 0)
    end = (user.quiet_end_hour or 0) * 60 + (user.quiet_end_minute or 0)
    return start <= current < end if start < end else current >= start or current < end


async def build_jobs_for_user(user):
    selected = parse_selected(user.selected_athkar)
    if selected:
        if user.frequency in {"goal_per_day", "goal_per_athkar"} and user.daily_goal_count and user.daily_goal_count > 0:
            start, end = user.quiet_start_hour or 23, user.quiet_end_hour or 6
            awake_seconds = 86400 if user.quiet_hours_preset == "none" else (24 - ((end - start) % 24)) * 3600
            seconds = max(60, int(round(awake_seconds / user.daily_goal_count)))
        else:
            seconds = frequency_to_seconds(user.frequency or "every_30_min", user.custom_frequency_minutes)
        reminder_scheduler.add_job(
            send_user_reminder,
            trigger="interval",
            seconds=seconds,
            args=[str(user.telegram_id)],
            id=f"user_reminder_{user.telegram_id}",
            replace_existing=True,
            misfire_grace_time=60,
        )

    if user.prayer_athkar_enabled and user.prayer_city:
        now = datetime.now(pytz.timezone(user.timezone or "Africa/Cairo"))
        morning_scheduled = False
        evening_scheduled = False
        for day in (now.date(), now.date() + timedelta(days=1)):
            timings = await fetch_prayer_times_by_city(user.prayer_city, day)
            if not timings:
                continue
            fajr = parse_prayer_datetime(day, "Fajr", timings, user.timezone or "Africa/Cairo")
            asr = parse_prayer_datetime(day, "Asr", timings, user.timezone or "Africa/Cairo")
            if fajr and not morning_scheduled:
                run_time = fajr + timedelta(minutes=30)
                if run_time > now:
                    reminder_scheduler.add_job(
                        send_morning_evening_athkar,
                        trigger="date",
                        run_date=run_time,
                        args=[str(user.telegram_id), "morning"],
                        id=f"morning_evening_{user.telegram_id}_morning",
                        replace_existing=True,
                        misfire_grace_time=300,
                    )
                    morning_scheduled = True
            if asr and not evening_scheduled:
                run_time = asr + timedelta(minutes=30)
                if run_time > now:
                    reminder_scheduler.add_job(
                        send_morning_evening_athkar,
                        trigger="date",
                        run_date=run_time,
                        args=[str(user.telegram_id), "evening"],
                        id=f"morning_evening_{user.telegram_id}_evening",
                        replace_existing=True,
                        misfire_grace_time=300,
                    )
                    evening_scheduled = True
            if morning_scheduled and evening_scheduled:
                break


async def rebuild_user_schedule(context: ContextTypes.DEFAULT_TYPE):
    set_application(context.application)
    for job in reminder_scheduler.get_jobs():
        if job.id.startswith(("user_reminder_", "prayer_reminder_", "morning_evening_")):
            reminder_scheduler.remove_job(job.id)
    users = await list_active_users()
    for user in users:
        await build_jobs_for_user(user)


async def choose_group_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Compatibility entry point for buttons from earlier releases."""
    await choose_community_mode(update, context)


async def choose_channel_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Compatibility entry point for buttons from earlier releases."""
    await choose_community_mode(update, context)


async def choose_community_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if query.from_user:
        await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, mode="community")
    context.user_data["active_mode"] = "community"
    await show_target_picker(query, context, lang)


async def show_target_picker(query, context: ContextTypes.DEFAULT_TYPE, lang: str):
    targets = await list_targets(str(query.from_user.id))
    if not targets:
        await query.edit_message_text(
            text=f"{tr(lang, 'target_setup_community')}\n\n{tr(lang, 'target_none')}",
            reply_markup=community_connect_menu(lang),
        )
        return
    await query.edit_message_text(text=tr(lang, "target_picker_title"), reply_markup=target_picker_menu(lang, targets))


async def request_target_discovery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open Telegram's native chooser for chats where this bot is already a member."""
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if query.data == "targets_refresh":
        await query.edit_message_text(text=tr(lang, "target_setup_community"), reply_markup=community_connect_menu(lang))
        return
    mode = "channel" if query.data == "targets_refresh_channel" else "group"
    context.user_data["awaiting_target_mode"] = mode
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=tr(lang, "target_discovery_prompt"),
        reply_markup=target_request_keyboard(lang, mode),
    )


async def handle_chat_shared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.chat_shared or not update.effective_user:
        return
    mode = context.user_data.get("awaiting_target_mode")
    if not mode:
        return
    lang = get_lang(context)
    chat_id = update.message.chat_shared.chat_id
    try:
        chat = await context.bot.get_chat(chat_id)
        bot_user = await context.bot.get_me()
        membership = await context.bot.get_chat_member(chat_id, bot_user.id)
        if membership.status not in ("administrator", "owner", "creator"):
            await update.message.reply_text(tr(lang, "target_needs_admin"), reply_markup=ReplyKeyboardRemove())
            return
        await add_or_update_target(
            str(update.effective_user.id), str(chat_id), chat.title or chat.username or str(chat_id), chat.type,
        )
        context.user_data.pop("awaiting_target_mode", None)
        await update.message.reply_text(tr(lang, "target_discovered"), reply_markup=ReplyKeyboardRemove())
        targets = await list_targets(str(update.effective_user.id))
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=tr(lang, "target_picker_title"),
            reply_markup=target_picker_menu(lang, targets),
        )
    except Exception:
        logger.exception("Failed to discover shared chat %s", chat_id)
        await update.message.reply_text(tr(lang, "target_discovery_failed"), reply_markup=ReplyKeyboardRemove())


async def select_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target_id = query.data.removeprefix("target_select_")
    context.user_data["selected_target_id"] = target_id
    lang = get_lang(context)
    target = await get_target(str(query.from_user.id), target_id)
    if not target:
        await show_target_picker(query, context, lang)
        return
    if not target.city:
        await begin_community_location_setup(query, context, lang)
        return
    await render_community_menu(query, context, lang, target)


async def render_community_menu(query, context: ContextTypes.DEFAULT_TYPE, lang: str, target=None):
    if target is None:
        if not query.from_user:
            return
        target = await get_target(str(query.from_user.id), context.user_data.get("selected_target_id", ""))
    if not target:
        await show_target_picker(query, context, lang)
        return
    title = target.chat_title or target.chat_id
    text_value = (
        f"{tr(lang, 'community_title').replace('{target}', title)}\n\n"
        f"{tr(lang, 'community_intro').replace('{target}', title)}\n\n"
        f"📍 {target.city} · {target.timezone}"
    )
    await query.edit_message_text(text=text_value, reply_markup=community_menu(lang, target))


async def toggle_community_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.from_user:
        return
    target = await get_target(str(query.from_user.id), context.user_data.get("selected_target_id", ""))
    if not target:
        await show_target_picker(query, context, get_lang(context))
        return
    fields = {
        "morning": "morning_athkar_enabled", "night": "night_athkar_enabled",
        "monday": "monday_fasting_enabled", "thursday": "thursday_fasting_enabled",
    }
    field = fields.get(query.data.removeprefix("community_toggle_"))
    if not field:
        return
    setattr(target, field, not bool(getattr(target, field)))
    await update_target_settings(str(query.from_user.id), target.chat_id, **{field: getattr(target, field)})
    await render_community_menu(query, context, get_lang(context), target)


async def change_community_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("selected_target_id"):
        await show_target_picker(query, context, get_lang(context))
        return
    await begin_community_location_setup(query, context, get_lang(context))


def format_community_prayer_times(lang: str, target, timings: dict) -> str:
    try:
        local_day = datetime.now(pytz.timezone(target.timezone or "Africa/Cairo")).date()
    except pytz.UnknownTimeZoneError:
        local_day = datetime.now(CAIRO_TZ).date()
    labels = {
        "ar": (("Fajr", "الفجر"), ("Sunrise", "الشروق"), ("Dhuhr", "الظهر"), ("Asr", "العصر"), ("Maghrib", "المغرب"), ("Isha", "العشاء")),
        "en": (("Fajr", "Fajr"), ("Sunrise", "Sunrise"), ("Dhuhr", "Dhuhr"), ("Asr", "Asr"), ("Maghrib", "Maghrib"), ("Isha", "Isha")),
    }
    pairs = labels["ar" if lang == "ar" else "en"]
    heading = tr(lang, "community_prayer_title").replace("{city}", target.city).replace("{date}", local_day.isoformat())
    return "\n".join([heading, *(f"{label}: {timings.get(key, '—').split(' ')[0]}" for key, label in pairs)])


async def show_community_prayer_times(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    target = await get_target(str(query.from_user.id), context.user_data.get("selected_target_id", ""))
    if not target or not target.city:
        await query.edit_message_text(text=tr(lang, "community_prayer_missing_city"), reply_markup=community_connect_menu(lang))
        return
    try:
        local_day = datetime.now(pytz.timezone(target.timezone or "Africa/Cairo")).date()
    except pytz.UnknownTimeZoneError:
        local_day = datetime.now(CAIRO_TZ).date()
    timings = await fetch_prayer_times(target.city, local_day, target.prayer_method or 3)
    if not timings:
        await query.edit_message_text(text=tr(lang, "community_prayer_failed"), reply_markup=community_menu(lang, target))
        return
    await query.edit_message_text(text=format_community_prayer_times(lang, target, timings), reply_markup=community_menu(lang, target))


async def render_community_posts(query, context: ContextTypes.DEFAULT_TYPE, lang: str, *, notice: str | None = None):
    if not query.from_user:
        return
    target = await get_target(str(query.from_user.id), context.user_data.get("selected_target_id", ""))
    if not target:
        await show_target_picker(query, context, lang)
        return
    posts = await list_community_posts(str(query.from_user.id), target.chat_id)
    text_value = notice or tr(lang, "community_other_posts")
    if not posts:
        text_value = f"{text_value}\n\n{tr(lang, 'post_none')}"
    await query.edit_message_text(text=text_value, reply_markup=community_posts_menu(lang, posts))


async def open_community_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await render_community_posts(query, context, get_lang(context))


async def begin_community_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if not query.from_user:
        return
    target = await get_target(str(query.from_user.id), context.user_data.get("selected_target_id", ""))
    if not target:
        await show_target_picker(query, context, lang)
        return
    kind = query.data.removeprefix("community_post_add_")
    if kind == "personal":
        prefs = await get_user_prefs(str(query.from_user.id))
        if not prefs or not parse_selected(prefs.selected_athkar):
            await query.edit_message_text(text=tr(lang, "post_personal_missing"), reply_markup=community_menu(lang, target))
            return
        context.user_data["draft_community_post"] = {"content_type": "personal_athkar"}
        await query.edit_message_text(text=tr(lang, "post_schedule_title"), reply_markup=post_schedule_menu(lang))
        return
    if kind == "text":
        context.user_data["draft_community_post"] = {"content_type": "text"}
        context.user_data["awaiting_community_post_text"] = True
        await query.edit_message_text(text=tr(lang, "post_prompt_message"), reply_markup=community_menu(lang, target))
        return
    if kind == "photo":
        context.user_data["draft_community_post"] = {"content_type": "photo"}
        context.user_data["awaiting_community_post_photo"] = True
        await query.edit_message_text(text=tr(lang, "post_prompt_image"), reply_markup=community_menu(lang, target))


async def handle_community_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo or not update.effective_user:
        return
    if not context.user_data.get("awaiting_community_post_photo"):
        return
    draft = context.user_data.get("draft_community_post")
    if not draft:
        return
    draft["photo_file_id"] = update.message.photo[-1].file_id
    draft["caption"] = update.message.caption or None
    context.user_data.pop("awaiting_community_post_photo", None)
    await update.message.reply_text(tr(get_lang(context), "post_schedule_title"), reply_markup=post_schedule_menu(get_lang(context)))


async def choose_community_post_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if not context.user_data.get("draft_community_post"):
        await render_community_posts(query, context, lang)
        return
    choice = query.data.removeprefix("community_post_schedule_")
    if choice == "clock":
        context.user_data["awaiting_community_post_clock"] = True
        await query.edit_message_text(text=tr(lang, "post_prompt_clock"), reply_markup=post_schedule_menu(lang))
    elif choice == "interval":
        context.user_data["awaiting_community_post_interval"] = True
        await query.edit_message_text(text=tr(lang, "post_prompt_interval"), reply_markup=post_schedule_menu(lang))
    elif choice == "prayer":
        await query.edit_message_text(text=tr(lang, "post_schedule_title"), reply_markup=post_prayer_anchor_menu(lang))


async def save_community_post(update: Update, context: ContextTypes.DEFAULT_TYPE, *, schedule_type: str, time_of_day: str | None = None, prayer_name: str | None = None, interval_minutes: int | None = None):
    user_id = str(update.effective_user.id)
    target = await get_target(user_id, context.user_data.get("selected_target_id", ""))
    draft = context.user_data.get("draft_community_post")
    if not target or not draft:
        return None
    post = await create_community_post(
        user_id, target.chat_id, content_type=draft["content_type"],
        text_content=draft.get("text_content"), photo_file_id=draft.get("photo_file_id"), caption=draft.get("caption"),
        schedule_type=schedule_type, time_of_day=time_of_day, prayer_name=prayer_name, interval_minutes=interval_minutes,
    )
    context.user_data.pop("draft_community_post", None)
    context.user_data.pop("awaiting_community_post_text", None)
    context.user_data.pop("awaiting_community_post_clock", None)
    context.user_data.pop("awaiting_community_post_interval", None)
    return post


async def set_community_post_anchor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prayer_name = query.data.removeprefix("community_post_anchor_")
    if prayer_name not in {"Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"}:
        return
    post = await save_community_post(update, context, schedule_type="prayer", prayer_name=prayer_name)
    if not post:
        return
    await render_community_posts(query, context, get_lang(context), notice=tr(get_lang(context), "post_saved"))


async def delete_community_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.from_user:
        return
    try:
        post_id = int(query.data.removeprefix("community_post_delete_"))
    except ValueError:
        return
    await remove_community_post(str(query.from_user.id), post_id)
    await render_community_posts(query, context, get_lang(context))


async def community_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    for key in (
        "draft_community_post", "awaiting_community_post_text", "awaiting_community_post_photo",
        "awaiting_community_post_clock", "awaiting_community_post_interval",
    ):
        context.user_data.pop(key, None)
    await render_community_menu(query, context, get_lang(context))


async def auto_register_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Register a group/channel when the bot itself becomes an administrator."""
    change = update.my_chat_member
    if not change or change.chat.type not in ("group", "supergroup", "channel"):
        return
    if change.new_chat_member.status not in ("administrator", "owner", "creator"):
        return
    owner = change.from_user
    if not owner:
        return
    chat = change.chat
    await add_or_update_target(str(owner.id), str(chat.id), chat.title or chat.username or str(chat.id), chat.type)
    logger.info("Auto-registered %s %s for owner %s", chat.type, chat.id, owner.id)


async def manage_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.from_user:
        return

    lang = get_lang(context)
    targets = await list_targets(str(query.from_user.id))
    if not targets:
        await query.edit_message_text(
            text=f"{tr(lang, 'target_setup_community')}\n\n{tr(lang, 'target_none')}",
            reply_markup=community_connect_menu(lang),
        )
        return

    lines = [tr(lang, "target_list_title")]
    for t in targets:
        lines.append(f"- {t.chat_title} ({t.chat_type})")

    remove_entries = [(t.chat_id, t.chat_title or t.chat_id) for t in targets]
    await query.edit_message_text(text="\n".join(lines), reply_markup=remove_target_menu(lang, remove_entries))


async def remove_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.from_user:
        return

    lang = get_lang(context)
    chat_id = query.data.replace("target_remove_", "")
    await remove_target(str(query.from_user.id), chat_id)
    context.user_data.pop("selected_target_id", None)
    await query.edit_message_text(text=tr(lang, "target_unlinked"), reply_markup=community_connect_menu(lang))


async def link_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat or not update.message:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup", "channel"):
        return

    owner_id = str(update.effective_user.id)
    title = chat.title or chat.username or str(chat.id)
    await add_or_update_target(owner_id, str(chat.id), title, chat.type)

    try:
        await update.message.reply_text("☑️ Linked to your private setup successfully.")
    except Exception as exc:
        logger.warning("Unable to reply in target chat: %s", exc)


async def send_test_to_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.from_user:
        return

    lang = get_lang(context)
    target = await get_target(str(query.from_user.id), context.user_data.get("selected_target_id", ""))
    if not target:
        await query.edit_message_text(text=tr(lang, "no_target_for_test"), reply_markup=community_connect_menu(lang))
        return
    back_menu = community_menu(lang, target)
    targets = [target]

    for t in targets:
        try:
            await context.bot.send_message(chat_id=int(t.chat_id), text=tr(lang, "community_test_text"))
        except Exception as exc:
            logger.warning("Failed sending test to %s: %s", t.chat_id, exc)

    await query.edit_message_text(text=tr(lang, "test_sent"), reply_markup=back_menu)
