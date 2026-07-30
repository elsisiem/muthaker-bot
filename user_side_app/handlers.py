import json
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta

import aiohttp
import pytz
from telegram import ReplyKeyboardRemove, Update
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
    delivery_menu,
    goal_menu,
    goal_scope_menu,
    home_menu,
    interval_menu,
    language_menu,
    location_request_keyboard,
    personal_menu,
    post_prayer_anchor_menu,
    post_schedule_menu,
    quiet_hours_menu,
    remove_target_menu,
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
UI_BUILD = "user-side-v200"
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


def normalize_digits(value: str) -> str:
    """Accept Arabic-Indic and Eastern Arabic-Indic digits in numeric settings."""
    return value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))


def selected_names(selected_ids: list[str], lang: str) -> list[str]:
    key = "ar" if lang == "ar" else "en"
    return [x[key] for x in ATHKAR_OPTIONS if x["id"] in selected_ids]


def find_athkar(athkar_id: str):
    for item in ATHKAR_OPTIONS:
        if item["id"] == athkar_id:
            return item
    return None


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


async def send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text_value: str, reply_markup):
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=text_value, reply_markup=reply_markup)
        except BadRequest as exc:
            if "Message is not modified" not in str(exc):
                raise
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text_value, reply_markup=reply_markup)


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

    text_value = f"{tr(lang, 'welcome')}\n\n{tr(lang, 'choose_mode')}"
    await send_or_edit(update, context, text_value, home_menu(lang))


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(
        text=f"{tr(lang, 'welcome')}\n\n{tr(lang, 'choose_mode')}",
        reply_markup=home_menu(lang),
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
        await query.edit_message_text(text=f"{tr(lang, 'welcome')}\n\n{tr(lang, 'choose_mode')}", reply_markup=home_menu(lang))
        return
    await query.edit_message_text(text=f"{tr(lang, 'welcome')}\n\n{tr(lang, 'choose_mode')}", reply_markup=home_menu(lang))


async def present_timezone_setup(query, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """Reuse the current setup message; only the temporary location prompt is separate."""
    context.user_data["awaiting_timezone_setup"] = True
    context.user_data["timezone_main_message_id"] = query.message.message_id
    await query.edit_message_text(
        text=f"{tr(lang, 'timezone_title')}\n\n{tr(lang, 'prayer_prompt_help')}\n\n{tr(lang, 'prayer_prompt_privacy')}",
        reply_markup=personal_menu(lang),
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
    selected = context.user_data.get("draft_selected", [])
    key = "en" if lang == "en" else "ar"
    items = [(x["id"], x[key], x["id"] in selected) for x in ATHKAR_OPTIONS]
    await query.edit_message_text(text=tr(lang, "athkar_menu_title"), reply_markup=athkar_select_menu(lang, items))


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
    context.user_data["draft_selected"] = [x["id"] for x in ATHKAR_OPTIONS]
    await render_athkar_selection(query, context, get_lang(context))


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
        key = "en" if lang == "en" else "ar"
        items = [(x["id"], x[key], False) for x in ATHKAR_OPTIONS]
        await query.edit_message_text(text=tr(lang, "need_athkar"), reply_markup=athkar_select_menu(lang, items))
        return
    await update_user_settings(user_id, selected_athkar=json.dumps(selected))
    prefs = await get_user_prefs(user_id)
    # Time zone is only needed once the user starts arranging actual sends.
    # Letting Step 1 work without it keeps first-run setup light and focused.
    if context.user_data.get("setup_flow") and not (prefs and prefs.timezone_confirmed):
        context.user_data["resume_after_timezone"] = "personal_schedule"
        await present_timezone_setup(query, context, lang)
        return
    await rebuild_user_schedule(context)
    if context.user_data.get("setup_flow"):
        await query.edit_message_text(text=tr(lang, "setup_step_schedule"), reply_markup=schedule_menu(lang))
        return
    await query.edit_message_text(text=tr(lang, "athkar_saved"), reply_markup=personal_menu(lang))


async def open_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(text=tr(lang, "strategy_menu_title"), reply_markup=schedule_menu(lang))


async def set_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)

    if query.data == "schedule_strategy_interval":
        await query.edit_message_text(text=tr(lang, "schedule_menu_title"), reply_markup=interval_menu(lang))
        return

    if query.data == "schedule_strategy_goal":
        await query.edit_message_text(text=tr(lang, "goal_menu_title"), reply_markup=goal_scope_menu(lang))
        return

    if query.data == "schedule_custom":
        context.user_data["awaiting_custom_interval"] = True
        await query.edit_message_text(text=tr(lang, "prompt_custom_interval"), reply_markup=interval_menu(lang))
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
    if scope == "total":
        await query.edit_message_text(text=tr(lang, "goal_scope_total_title"), reply_markup=goal_menu(lang, "total"))
        return
    if scope == "each":
        await query.edit_message_text(text=tr(lang, "goal_scope_each_title"), reply_markup=goal_menu(lang, "each"))
        return
    if scope == "advanced":
        prefs = await get_user_prefs(str(query.from_user.id))
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
    athkar = find_athkar(selected[index])
    name = athkar["ar" if lang == "ar" else "en"] if athkar else selected[index]
    text_value = tr(lang, "advanced_goal_title").replace("{name}", name).replace("{position}", str(index + 1)).replace("{total}", str(len(selected)))
    await query.edit_message_text(text=text_value, reply_markup=advanced_goal_menu(lang))


async def set_goal_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    raw = query.data.removeprefix("goal_")
    scope, value = raw.split("_", 1)
    if value == "custom":
        context.user_data["awaiting_custom_goal_scope"] = scope
        await query.edit_message_text(text=tr(lang, "prompt_custom_goal"), reply_markup=goal_menu(lang, scope))
        return
    await finish_goal_setup(query, context, lang, scope, int(value))


async def set_advanced_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    raw = query.data.removeprefix("goal_adv_")
    lang = get_lang(context)
    if raw == "custom":
        context.user_data["awaiting_advanced_goal"] = True
        await query.edit_message_text(text=tr(lang, "prompt_custom_goal"), reply_markup=advanced_goal_menu(lang))
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
        await query.edit_message_text(text=tr(lang, "setup_step_delivery"), reply_markup=delivery_menu(lang))
    else:
        await query.edit_message_text(text=tr(lang, "saved"), reply_markup=personal_menu(lang))


async def open_delivery_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(text=tr(lang, "delivery_menu_title"), reply_markup=delivery_menu(lang))


async def open_quiet_hours_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(text=tr(lang, "quiet_hours_title"), reply_markup=quiet_hours_menu(lang))


async def set_quiet_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset = query.data.removeprefix("quiet_")
    if preset == "custom":
        context.user_data["awaiting_custom_quiet_hours"] = True
        await query.edit_message_text(text=tr(get_lang(context), "quiet_custom_prompt"), reply_markup=quiet_hours_menu(get_lang(context)))
        return
    dynamic = {
        "fajr_isha": (0, 0), "sleep_10_fajr": (22, 5),
        "sleep_11_fajr": (23, 5), "sleep_12_fajr": (0, 5),
    }
    if preset not in QUIET_HOUR_PRESETS and preset not in dynamic:
        return
    prefs = await get_user_prefs(str(query.from_user.id))
    if preset in dynamic and not (prefs and prefs.prayer_city):
        context.user_data["pending_quiet_preset"] = preset
        await query.edit_message_text(text=tr(get_lang(context), "quiet_city_prompt"), reply_markup=quiet_hours_menu(get_lang(context)))
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
    names = "، ".join(selected_names(selected, lang)) or tr(lang, "empty_athkar")
    schedule = {
        "every_5_min": tr(lang, "interval_5"),
        "every_30_min": tr(lang, "interval_30"),
        "hourly": tr(lang, "interval_60"),
        "goal_per_day": tr(lang, "daily_goal_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
        "goal_per_athkar": tr(lang, "daily_goal_each_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
        "custom_interval": tr(lang, "custom_interval_summary").replace("{minutes}", str(prefs.custom_frequency_minutes or 30)),
    }.get(prefs.frequency if prefs else "every_30_min", tr(lang, "interval_30"))
    quiet = tr(lang, f"quiet_{prefs.quiet_hours_preset}") if prefs and prefs.quiet_hours_preset else tr(lang, "quiet_none")
    return (
        f"{tr(lang, 'setup_ready_title')}\n"
        f"{tr(lang, 'setup_ready_intro')}\n\n"
        f"• {tr(lang, 'field_athkar')}: {names}\n"
        f"• {tr(lang, 'field_schedule')}: {schedule}\n"
        f"• {tr(lang, 'cfg_quiet_hours')}: {quiet}"
    )


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
    mode = "batch" if query.data == "delivery_batch" else "rotating"
    await update_user_settings(user_id, delivery_mode=mode)
    await rebuild_user_schedule(context)
    if context.user_data.get("setup_flow"):
        await query.edit_message_text(text=tr(lang, "setup_step_quiet"), reply_markup=quiet_hours_menu(lang))
    else:
        await query.edit_message_text(text=tr(lang, "saved"), reply_markup=personal_menu(lang))


async def show_personal_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    prefs = await get_user_prefs(str(query.from_user.id))
    selected = parse_selected(prefs.selected_athkar if prefs else None)
    names = selected_names(selected, lang)

    frequency_label = {
        "every_5_min": tr(lang, "interval_5"),
        "every_30_min": tr(lang, "interval_30"),
        "hourly": tr(lang, "interval_60"),
        "custom_interval": f"{prefs.custom_frequency_minutes or 30} min",
        "goal_per_day": f"{prefs.daily_goal_count or 100} / day",
        "goal_per_athkar": tr(lang, "daily_goal_each_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
    }.get((prefs.frequency if prefs else "every_30_min"), tr(lang, "interval_30"))

    delivery_label = tr(lang, "delivery_batch") if prefs and prefs.delivery_mode == "batch" else tr(lang, "delivery_rotating")
    prayer_label = tr(lang, "prayer_on") if prefs and prefs.prayer_athkar_enabled else tr(lang, "prayer_off")
    city = prefs.prayer_city if prefs and prefs.prayer_city else "-"
    timezone_name = prefs.timezone if prefs and prefs.timezone else "Africa/Cairo"
    athkar_lines = "\n".join([f"- {n}" for n in names]) if names else tr(lang, "empty_athkar")

    text_value = (
        f"{tr(lang, 'settings_title')}\n\n"
        f"{tr(lang, 'field_athkar')}:\n{athkar_lines}\n\n"
        f"{tr(lang, 'field_schedule')}: {frequency_label}\n"
        f"{tr(lang, 'field_delivery')}: {delivery_label}\n"
        f"{tr(lang, 'field_prayer')}: {prayer_label}\n"
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
    names = selected_names(selected, lang)
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
        f"{tr(lang, 'cfg_quiet_hours')}: {tr(lang, f'quiet_{prefs.quiet_hours_preset}') if prefs else tr(lang, 'quiet_none')}"
    )
    await update.message.reply_text(text_value, reply_markup=personal_menu(lang))


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

    if prefs and prefs.timezone_confirmed:
        context.user_data["awaiting_prayer_setup"] = True
        await query.edit_message_text(text=tr(lang, "prayer_prompt_city"), reply_markup=personal_menu(lang))
        return

    context.user_data["awaiting_prayer_setup"] = True
    context.user_data["timezone_main_message_id"] = query.message.message_id
    await query.edit_message_text(
        text=f"{tr(lang, 'prayer_prompt_title')}\n\n{tr(lang, 'prayer_prompt_help')}\n\n{tr(lang, 'prayer_prompt_privacy')}\n\n{tr(lang, 'prayer_prompt_city')}",
        reply_markup=personal_menu(lang),
    )
    location_prompt = await context.bot.send_message(
        chat_id=query.from_user.id,
        text=f"{tr(lang, 'prayer_prompt_title')}\n\n{tr(lang, 'prayer_prompt_help')}",
        reply_markup=location_request_keyboard(lang),
    )
    context.user_data["timezone_location_prompt_id"] = location_prompt.message_id


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

    prayer_setup = context.user_data.pop("awaiting_prayer_setup", False)
    context.user_data.pop("awaiting_timezone_setup", None)
    onboarding = context.user_data.pop("onboarding", False)
    resume_after_timezone = context.user_data.pop("resume_after_timezone", None)
    # Coordinates are deliberately not persisted; location is used only to infer timezone.
    await update_user_settings(
        user_id,
        timezone=timezone_name,
        timezone_confirmed=True,
        onboarding_complete=True if onboarding else None,
    )
    await rebuild_user_schedule(context)
    if resume_after_timezone == "personal_setup":
        context.user_data["setup_flow"] = True
        prefs = await get_user_prefs(user_id)
        context.user_data["draft_selected"] = parse_selected(prefs.selected_athkar if prefs else None)
        selected = context.user_data["draft_selected"]
        key = "en" if lang == "en" else "ar"
        items = [(x["id"], x[key], x["id"] in selected) for x in ATHKAR_OPTIONS]
        text_value = f"{tr(lang, 'timezone_success').replace('{timezone}', timezone_name)}\n\n{tr(lang, 'setup_step_athkar')}"
        reply_markup = athkar_select_menu(lang, items)
    elif resume_after_timezone == "personal_schedule":
        context.user_data["setup_flow"] = True
        text_value = f"{tr(lang, 'timezone_success').replace('{timezone}', timezone_name)}\n\n{tr(lang, 'setup_step_schedule')}"
        reply_markup = schedule_menu(lang)
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
            await update.message.reply_text(tr(lang, "setup_step_delivery"), reply_markup=delivery_menu(lang))
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
            await update.message.reply_text(tr(lang, "setup_step_delivery"), reply_markup=delivery_menu(lang))
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
            await update.message.reply_text(tr(lang, "setup_step_delivery"), reply_markup=delivery_menu(lang))
            return
        athkar = find_athkar(selected[index])
        name = athkar["ar" if lang == "ar" else "en"] if athkar else selected[index]
        prompt = tr(lang, "advanced_goal_title").replace("{name}", name).replace("{position}", str(index + 1)).replace("{total}", str(len(selected)))
        await update.message.reply_text(prompt, reply_markup=advanced_goal_menu(lang))
        return

    if context.user_data.get("awaiting_custom_quiet_hours"):
        value = normalize_digits(text_value).replace(" ", "")
        match = re.fullmatch(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})", value)
        if not match:
            await update.message.reply_text(tr(lang, "quiet_custom_invalid"))
            return
        start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
        if start_hour > 23 or end_hour > 23 or start_minute > 59 or end_minute > 59:
            await update.message.reply_text(tr(lang, "quiet_custom_invalid"))
            return
        context.user_data.pop("awaiting_custom_quiet_hours", None)
        await update_user_settings(user_id, quiet_hours_preset="custom", quiet_start_hour=start_hour, quiet_end_hour=end_hour, quiet_start_minute=start_minute, quiet_end_minute=end_minute)
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
        start, end = {"fajr_isha": (0, 0), "sleep_10_fajr": (22, 5), "sleep_11_fajr": (23, 5), "sleep_12_fajr": (0, 5)}[preset]
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
        lat, lon, _ = await city_to_coords(text_value)
        timezone_name = await resolve_timezone_from_coords(lat, lon) if lat is not None else None
        if not timezone_name:
            await update.message.reply_text(tr(lang, "prayer_city_failed"))
            return
        context.user_data.pop("awaiting_timezone_setup", None)
        await update_user_settings(user_id, timezone=timezone_name)
        await rebuild_user_schedule(context)
        await update.message.reply_text(tr(lang, 'prayer_timezone_detected').replace('{timezone}', timezone_name), reply_markup=ReplyKeyboardRemove())
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
        await update_user_settings(
            user_id,
            prayer_athkar_enabled=True,
            prayer_city=display.split(",")[0],
            timezone=timezone_name,
        )
        context.user_data["awaiting_prayer_setup"] = False
        await rebuild_user_schedule(context)
        city_name = display.split(",")[0]
        await update.message.reply_text(
            f"{tr(lang, 'prayer_enabled_done')}\n{tr(lang, 'prayer_timezone_detected').replace('{timezone}', timezone_name)}\n{tr(lang, 'prayer_city_saved').replace('{city}', city_name)}",
            reply_markup=ReplyKeyboardRemove(),
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
        idx = rotation_state.get(telegram_id, 0) % len(weighted)
        ids = [weighted[idx]]
        rotation_state[telegram_id] = (idx + 1) % len(weighted)
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
        item = find_athkar(athkar_id)
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


async def send_prayer_message(telegram_id: str, kind: str):
    application = get_application()
    if not application:
        logger.error("Cannot send prayer athkar: Telegram application is not ready")
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
    if user.quiet_hours_preset in {"fajr_isha", "sleep_10_fajr", "sleep_11_fajr", "sleep_12_fajr"} and user.prayer_city:
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
                start_hour = {"sleep_10_fajr": 22, "sleep_11_fajr": 23, "sleep_12_fajr": 0}.get(user.quiet_hours_preset)
                if start_hour is not None:
                    return local_now < fajr or local_now.hour >= start_hour
        # A temporary provider failure must never turn the Fajr-to-Isha choice
        # into a full-day pause.  The next send retries the prayer lookup.
        if user.quiet_hours_preset == "fajr_isha":
            return False
    start = (user.quiet_start_hour or 0) * 60 + (user.quiet_start_minute or 0)
    end = (user.quiet_end_hour or 0) * 60 + (user.quiet_end_minute or 0)
    current = local_now.hour * 60 + local_now.minute
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
        for day in (now.date(), now.date() + timedelta(days=1)):
            timings = await fetch_prayer_times_by_city(user.prayer_city, day)
            if not timings:
                continue
            fajr = parse_prayer_datetime(day, "Fajr", timings, user.timezone or "Africa/Cairo")
            asr = parse_prayer_datetime(day, "Asr", timings, user.timezone or "Africa/Cairo")
            if fajr:
                run_time = fajr + timedelta(minutes=35)
                if run_time > now:
                    reminder_scheduler.add_job(
                        send_prayer_message,
                        trigger="date",
                        run_date=run_time,
                        args=[str(user.telegram_id), "morning"],
                        id=f"prayer_reminder_{user.telegram_id}_morning",
                        replace_existing=True,
                        misfire_grace_time=300,
                    )
                    break
            if asr:
                run_time = asr + timedelta(minutes=30)
                if run_time > now:
                    reminder_scheduler.add_job(
                        send_prayer_message,
                        trigger="date",
                        run_date=run_time,
                        args=[str(user.telegram_id), "evening"],
                        id=f"prayer_reminder_{user.telegram_id}_evening",
                        replace_existing=True,
                        misfire_grace_time=300,
                    )
                    break


async def rebuild_user_schedule(context: ContextTypes.DEFAULT_TYPE):
    set_application(context.application)
    for job in reminder_scheduler.get_jobs():
        if job.id.startswith("user_reminder_") or job.id.startswith("prayer_reminder_"):
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
        await update.message.reply_text("✅ Linked to your private setup successfully.")
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
