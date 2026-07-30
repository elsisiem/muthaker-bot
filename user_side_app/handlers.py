import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

import aiohttp
import pytz
from telegram import ReplyKeyboardRemove, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from .db import (
    add_or_update_target,
    get_user_prefs,
    list_active_users,
    list_targets,
    remove_target,
    update_user_settings,
    upsert_user_prefs,
)
from .i18n import normalize_lang, tr
from .keyboards import (
    athkar_select_menu,
    channel_menu,
    delivery_menu,
    goal_menu,
    group_menu,
    home_menu,
    interval_menu,
    language_menu,
    location_request_keyboard,
    personal_menu,
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
from services.timezone_service import detect_timezone_from_location

logger = logging.getLogger(__name__)
UI_BUILD = "user-side-v180"
CAIRO_TZ = pytz.timezone("Africa/Cairo")
QUIET_HOUR_PRESETS = {"normal": (23, 6), "early": (21, 5), "night_owl": (1, 9), "none": (0, 0)}

ATHKAR_OPTIONS = [
    {"id": "hizb", "ar": "ورد الحرز", "en": "Hizb Wird", "text_ar": "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير.", "text_en": "There is no god but Allah alone with no partner."},
    {"id": "baaqiyat", "ar": "الباقيات الصالحات", "en": "Eternal Good Deeds", "text_ar": "سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر.", "text_en": "Glory be to Allah, praise be to Allah, there is no god but Allah, and Allah is the Greatest."},
    {"id": "istighfar", "ar": "الاستغفار", "en": "Istighfar", "text_ar": "أستغفر الله العظيم وأتوب إليه.", "text_en": "I seek forgiveness from Allah and repent to Him."},
    {"id": "salat", "ar": "الصلاة على النبي", "en": "Salawat", "text_ar": "اللهم صل وسلم وبارك على محمد.", "text_en": "O Allah, send prayers and peace upon Muhammad."},
]

rotation_state: dict[str, int] = {}


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

    text_value = f"{tr(lang, 'welcome')}\n\n{tr(lang, 'choose_mode')}\n\n({UI_BUILD})"
    await send_or_edit(update, context, text_value, home_menu(lang))


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(
        text=f"{tr(lang, 'welcome')}\n\n{tr(lang, 'choose_mode')}\n\n({UI_BUILD})",
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
        await query.edit_message_text(text=f"{tr(lang, 'language_saved')}\n\n{tr(lang, 'choose_mode')}", reply_markup=home_menu(lang))
        return
    await query.edit_message_text(text=f"{tr(lang, 'lang_set')}\n\n{tr(lang, 'choose_mode')}", reply_markup=home_menu(lang))


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
    prefs = await get_user_prefs(str(query.from_user.id))
    if not prefs or not prefs.timezone_confirmed:
        context.user_data["resume_after_timezone"] = "personal_setup"
        await present_timezone_setup(query, context, get_lang(context))
        return
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
        await query.edit_message_text(text=tr(lang, "goal_menu_title"), reply_markup=goal_menu(lang))
        return

    if query.data == "schedule_custom":
        context.user_data["awaiting_custom_interval"] = True
        await query.edit_message_text(text=tr(lang, "prompt_custom_interval"), reply_markup=interval_menu(lang))
        return

    if query.data == "schedule_goal_custom":
        context.user_data["awaiting_custom_goal"] = True
        await query.edit_message_text(text=tr(lang, "prompt_custom_goal"), reply_markup=goal_menu(lang))
        return

    if query.data.startswith("schedule_goal_"):
        raw = query.data.replace("schedule_goal_", "")
        goal_value = int(raw)
        await update_user_settings(user_id, frequency="goal_per_day", daily_goal_count=goal_value, custom_frequency_minutes=None)
        await rebuild_user_schedule(context)
        await continue_after_schedule(query, context, lang)
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
    if preset not in QUIET_HOUR_PRESETS:
        return
    start, end = QUIET_HOUR_PRESETS[preset]
    await update_user_settings(str(query.from_user.id), quiet_hours_preset=preset, quiet_start_hour=start, quiet_end_hour=end)
    await rebuild_user_schedule(context)
    lang = get_lang(context)
    if context.user_data.pop("setup_flow", False):
        prefs = await get_user_prefs(str(query.from_user.id))
        selected = parse_selected(prefs.selected_athkar if prefs else None)
        names = "، ".join(selected_names(selected, lang)) or tr(lang, "empty_athkar")
        schedule = {
            "every_5_min": tr(lang, "interval_5"),
            "every_30_min": tr(lang, "interval_30"),
            "hourly": tr(lang, "interval_60"),
            "goal_per_day": tr(lang, "daily_goal_summary").replace("{count}", str(prefs.daily_goal_count or 100)),
            "custom_interval": tr(lang, "custom_interval_summary").replace("{minutes}", str(prefs.custom_frequency_minutes or 30)),
        }.get(prefs.frequency if prefs else "every_30_min", tr(lang, "interval_30"))
        quiet = tr(lang, f"quiet_{prefs.quiet_hours_preset or 'normal'}") if prefs else tr(lang, "quiet_normal")
        text_value = (
            f"{tr(lang, 'setup_ready_title')}\n\n"
            f"{tr(lang, 'setup_ready_intro')}\n\n"
            f"• {tr(lang, 'field_athkar')}: {names}\n"
            f"• {tr(lang, 'field_schedule')}: {schedule}\n"
            f"• {tr(lang, 'cfg_quiet_hours')}: {quiet}"
        )
        await query.edit_message_text(text=text_value, reply_markup=setup_complete_menu(lang))
    else:
        await query.edit_message_text(text=tr(lang, "saved"), reply_markup=personal_menu(lang))


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


async def handle_location_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.location or not update.effective_user:
        return
    if not (context.user_data.get("awaiting_prayer_setup") or context.user_data.get("awaiting_timezone_setup")):
        return

    lang = get_lang(context)
    user_id = str(update.effective_user.id)
    latitude = update.message.location.latitude
    longitude = update.message.location.longitude

    timezone_name = await resolve_timezone_from_coords(latitude, longitude)

    if not timezone_name:
        await update.message.reply_text(tr(lang, "prayer_location_failed"), reply_markup=ReplyKeyboardRemove())
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

    if context.user_data.get("awaiting_custom_goal"):
        if not numeric_value.isdigit():
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        goal_count = int(numeric_value)
        if goal_count < 1 or goal_count > 10000:
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        context.user_data["awaiting_custom_goal"] = False
        await update_user_settings(user_id, frequency="goal_per_day", daily_goal_count=goal_count, custom_frequency_minutes=None)
        await rebuild_user_schedule(context)
        if context.user_data.get("setup_flow"):
            await update.message.reply_text(tr(lang, "setup_step_delivery"), reply_markup=delivery_menu(lang))
        else:
            await update.message.reply_text(tr(lang, "saved"))
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
    if is_quiet_time(prefs):
        return
    selected = parse_selected(prefs.selected_athkar)
    if not selected:
        return
    lang = "ar" if prefs.language == "ar" else "en"
    if prefs.delivery_mode == "batch":
        ids = selected
    else:
        idx = rotation_state.get(telegram_id, 0) % len(selected)
        ids = [selected[idx]]
        rotation_state[telegram_id] = (idx + 1) % len(selected)

    application = get_application()
    if not application:
        logger.error("Cannot send user reminder: Telegram application is not ready")
        return

    for athkar_id in ids:
        item = find_athkar(athkar_id)
        if not item:
            continue
        text_key = "text_en" if lang == "en" else "text_ar"
        await application.bot.send_message(chat_id=int(telegram_id), text=item[text_key])


async def fetch_prayer_times_by_city(city: str, target_date):
    date_str = target_date.strftime("%d-%m-%Y")
    url = f"https://api.aladhan.com/v1/timings/{date_str}"
    params = {"city": city, "method": 3}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=15) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("data", {}).get("timings")


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


def is_quiet_time(user) -> bool:
    """Evaluate the user's saved quiet hours in their own timezone."""
    if user.quiet_hours_preset == "none":
        return False
    try:
        local_now = datetime.now(pytz.timezone(user.timezone or "Africa/Cairo"))
    except Exception:
        local_now = datetime.now(CAIRO_TZ)
    start, end, hour = user.quiet_start_hour or 23, user.quiet_end_hour or 6, local_now.hour
    return start <= hour < end if start < end else hour >= start or hour < end


async def build_jobs_for_user(user):
    selected = parse_selected(user.selected_athkar)
    if selected:
        if user.frequency == "goal_per_day" and user.daily_goal_count and user.daily_goal_count > 0:
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
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if query.from_user:
        await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, mode="group")
    context.user_data["active_mode"] = "group"
    await show_target_picker(query, context, lang, "group")


async def choose_channel_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if query.from_user:
        await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, mode="channel")
    context.user_data["active_mode"] = "channel"
    await show_target_picker(query, context, lang, "channel")


async def show_target_picker(query, context: ContextTypes.DEFAULT_TYPE, lang: str, mode: str):
    targets = await list_targets(str(query.from_user.id), mode)
    if not targets:
        setup_key = "target_setup_channel" if mode == "channel" else "target_setup_group"
        await query.edit_message_text(text=f"{tr(lang, setup_key)}\n\n{tr(lang, 'target_none')}", reply_markup=group_menu(lang) if mode == "group" else channel_menu(lang))
        return
    await query.edit_message_text(text=tr(lang, "target_picker_title"), reply_markup=target_picker_menu(lang, targets))


async def request_target_discovery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open Telegram's native chooser for chats where this bot is already a member."""
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    mode = context.user_data.get("active_mode", "group")
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
        targets = await list_targets(str(update.effective_user.id), mode)
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
    context.user_data["selected_target_id"] = query.data.removeprefix("target_select_")
    lang = get_lang(context)
    await query.edit_message_text(text=tr(lang, "target_selected"), reply_markup=group_menu(lang) if context.user_data.get("active_mode") == "group" else channel_menu(lang))


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
    mode = context.user_data.get("active_mode", "group")
    targets = await list_targets(str(query.from_user.id))
    if not targets:
        setup_text = tr(lang, "target_setup_channel") if mode == "channel" else tr(lang, "target_setup_group")
        back_menu = channel_menu(lang) if mode == "channel" else group_menu(lang)
        await query.edit_message_text(text=f"{setup_text}\n\n{tr(lang, 'target_none')}", reply_markup=back_menu)
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
    mode = context.user_data.get("active_mode", "group")
    chat_id = query.data.replace("target_remove_", "")
    await remove_target(str(query.from_user.id), chat_id)
    back_menu = channel_menu(lang) if mode == "channel" else group_menu(lang)
    await query.edit_message_text(text=tr(lang, "target_unlinked"), reply_markup=back_menu)


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
    mode = context.user_data.get("active_mode", "group")
    back_menu = channel_menu(lang) if mode == "channel" else group_menu(lang)
    targets = await list_targets(str(query.from_user.id))
    if not targets:
        await query.edit_message_text(text=tr(lang, "no_target_for_test"), reply_markup=back_menu)
        return

    for t in targets:
        try:
            await context.bot.send_message(chat_id=int(t.chat_id), text="📿 رسالة اختبار من مذكر الاذكار")
        except Exception as exc:
            logger.warning("Failed sending test to %s: %s", t.chat_id, exc)

    await query.edit_message_text(text=tr(lang, "test_sent"), reply_markup=back_menu)


async def config_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    mode = context.user_data.get("active_mode", "personal")
    if mode == "channel":
        back_menu = channel_menu(lang)
    elif mode == "group":
        back_menu = group_menu(lang)
    else:
        back_menu = personal_menu(lang)
    await query.edit_message_text(text=tr(lang, "cfg_comming_soon"), reply_markup=back_menu)
