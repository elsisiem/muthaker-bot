import json
import logging
from datetime import datetime, timedelta

import aiohttp
import pytz
from telegram import ReplyKeyboardRemove, Update
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
from .i18n import tr
from .keyboards import (
    athkar_select_menu,
    channel_menu,
    delivery_menu,
    group_menu,
    home_menu,
    language_menu,
    location_request_keyboard,
    personal_menu,
    remove_target_menu,
    schedule_menu,
)
from .scheduler import (
    reminder_scheduler,
    rebuild_all_jobs,
    set_application,
    bot_application,
)

logger = logging.getLogger(__name__)
UI_BUILD = "user-side-v180"
CAIRO_TZ = pytz.timezone("Africa/Cairo")

ATHKAR_OPTIONS = [
    {"id": "hizb", "ar": "ورد الحرز", "en": "Hizb Wird", "text_ar": "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير.", "text_en": "There is no god but Allah alone with no partner."},
    {"id": "baaqiyat", "ar": "الباقيات الصالحات", "en": "Eternal Good Deeds", "text_ar": "سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر.", "text_en": "Glory be to Allah, praise be to Allah, there is no god but Allah, and Allah is the Greatest."},
    {"id": "istighfar", "ar": "الاستغفار", "en": "Istighfar", "text_ar": "أستغفر الله العظيم وأتوب إليه.", "text_en": "I seek forgiveness from Allah and repent to Him."},
    {"id": "salat", "ar": "الصلاة على النبي", "en": "Salawat", "text_ar": "اللهم صل وسلم وبارك على محمد.", "text_en": "O Allah, send prayers and peace upon Muhammad."},
]

rotation_state: dict[str, int] = {}


def get_lang(context: ContextTypes.DEFAULT_TYPE, fallback: str = "ar") -> str:
    return "en" if context.user_data.get("lang") == "en" else fallback


def parse_selected(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def selected_names(selected_ids: list[str], lang: str) -> list[str]:
    key = "en" if lang == "en" else "ar"
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
    if frequency == "custom_interval" and custom_minutes:
        return max(60, custom_minutes * 60)
    return 1800


async def send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text_value: str, reply_markup):
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text_value, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text_value, reply_markup=reply_markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name
    prefs = await get_user_prefs(user_id)

    lang = prefs.language if prefs and prefs.language in ("ar", "en") else "ar"
    context.user_data["lang"] = lang
    await upsert_user_prefs(user_id, first_name, language=lang)

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

    lang = "en" if query.data == "lang_en" else "ar"
    context.user_data["lang"] = lang
    await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, language=lang)
    await query.edit_message_text(text=f"{tr(lang, 'lang_set')}\n\n{tr(lang, 'choose_mode')}", reply_markup=home_menu(lang))


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


async def open_personal_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)
    prefs = await get_user_prefs(user_id)
    selected = parse_selected(prefs.selected_athkar if prefs else None)
    context.user_data["draft_selected"] = selected

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

    key = "en" if lang == "en" else "ar"
    items = [(x["id"], x[key], x["id"] in selected) for x in ATHKAR_OPTIONS]
    await query.edit_message_text(text=tr(lang, "athkar_menu_title"), reply_markup=athkar_select_menu(lang, items))


async def select_all_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["draft_selected"] = [x["id"] for x in ATHKAR_OPTIONS]
    await open_personal_athkar(update, context)


async def clear_all_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["draft_selected"] = []
    await open_personal_athkar(update, context)


async def save_athkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)
    selected = context.user_data.get("draft_selected", [])
    await update_user_settings(user_id, selected_athkar=json.dumps(selected))
    await rebuild_user_schedule(context)
    await query.edit_message_text(text=tr(lang, "athkar_saved"), reply_markup=personal_menu(lang))


async def open_schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(text=tr(lang, "schedule_menu_title"), reply_markup=schedule_menu(lang))


async def set_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)

    if query.data == "schedule_custom":
        context.user_data["awaiting_custom_interval"] = True
        await query.edit_message_text(text=tr(lang, "prompt_custom_interval"), reply_markup=personal_menu(lang))
        return

    mapping = {
        "schedule_every_5": "every_5_min",
        "schedule_every_30": "every_30_min",
        "schedule_hourly": "hourly",
    }
    frequency = mapping.get(query.data, "every_30_min")
    await update_user_settings(user_id, frequency=frequency, custom_frequency_minutes=None)
    await rebuild_user_schedule(context)
    await query.edit_message_text(text=tr(lang, "saved"), reply_markup=personal_menu(lang))


async def open_delivery_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(text=tr(lang, "delivery_menu_title"), reply_markup=delivery_menu(lang))


async def set_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    user_id = str(query.from_user.id)
    mode = "batch" if query.data == "delivery_batch" else "rotating"
    await update_user_settings(user_id, delivery_mode=mode)
    await rebuild_user_schedule(context)
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

    context.user_data["awaiting_prayer_setup"] = True
    await query.edit_message_text(
        text=f"{tr(lang, 'prayer_need_location')}\n\n{tr(lang, 'prayer_privacy_note')}\n\n{tr(lang, 'prayer_city_prompt')}",
        reply_markup=personal_menu(lang),
    )
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=tr(lang, "prayer_need_location"),
        reply_markup=location_request_keyboard(lang),
    )


async def fetch_timezone_by_coords(latitude: float, longitude: float):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m",
        "forecast_days": 1,
        "timezone": "auto",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=15) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("timezone")


async def reverse_city(latitude: float, longitude: float):
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": latitude, "lon": longitude, "format": "jsonv2"}
    headers = {"User-Agent": "muthaker-bot/1.0"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers, timeout=15) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            address = data.get("address", {})
            return address.get("city") or address.get("town") or address.get("village") or address.get("state")


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
    if not context.user_data.get("awaiting_prayer_setup"):
        return

    lang = get_lang(context)
    user_id = str(update.effective_user.id)
    latitude = update.message.location.latitude
    longitude = update.message.location.longitude

    timezone_name = await fetch_timezone_by_coords(latitude, longitude)
    city = await reverse_city(latitude, longitude)

    try:
        await update.message.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=tr(lang, "location_deleted"), reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    if not timezone_name:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=tr(lang, "prayer_location_failed"))
        return

    if not city:
        city = "Unknown"

    await update_user_settings(
        user_id,
        prayer_athkar_enabled=True,
        prayer_city=city,
        timezone=timezone_name,
    )
    context.user_data["awaiting_prayer_setup"] = False
    await rebuild_user_schedule(context)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=tr(lang, "prayer_enabled_done"), reply_markup=ReplyKeyboardRemove())


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    lang = get_lang(context)
    user_id = str(update.effective_user.id)
    text_value = (update.message.text or "").strip()

    if context.user_data.get("awaiting_custom_interval"):
        if not text_value.isdigit():
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        minutes = int(text_value)
        if minutes < 1 or minutes > 1440:
            await update.message.reply_text(tr(lang, "invalid_number"))
            return
        context.user_data["awaiting_custom_interval"] = False
        await update_user_settings(user_id, frequency="custom_interval", custom_frequency_minutes=minutes)
        await rebuild_user_schedule(context)
        await update.message.reply_text(tr(lang, "saved"))
        return

    if context.user_data.get("awaiting_prayer_setup"):
        lat, lon, display = await city_to_coords(text_value)
        if lat is None or lon is None:
            await update.message.reply_text(tr(lang, "prayer_city_failed"))
            return
        timezone_name = await fetch_timezone_by_coords(lat, lon)
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
        await update.message.reply_text(tr(lang, "prayer_enabled_done"), reply_markup=ReplyKeyboardRemove())
        return


async def send_user_reminder(telegram_id: str):
    prefs = await get_user_prefs(telegram_id)
    if not prefs:
        return
    selected = parse_selected(prefs.selected_athkar)
    if not selected:
        return
    lang = "en" if prefs.language == "en" else "ar"
    if prefs.delivery_mode == "batch":
        ids = selected
    else:
        idx = rotation_state.get(telegram_id, 0) % len(selected)
        ids = [selected[idx]]
        rotation_state[telegram_id] = (idx + 1) % len(selected)

    for athkar_id in ids:
        item = find_athkar(athkar_id)
        if not item or not bot_application:
            continue
        text_key = "text_en" if lang == "en" else "text_ar"
        await bot_application.bot.send_message(chat_id=int(telegram_id), text=item[text_key])


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
    if not bot_application:
        return
    text = "🌅 أذكار الصباح" if kind == "morning" else "🌙 أذكار المساء"
    await bot_application.bot.send_message(chat_id=int(telegram_id), text=text)


async def build_jobs_for_user(user):
    selected = parse_selected(user.selected_athkar)
    if selected:
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
        now = datetime.now(CAIRO_TZ)
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
    await query.edit_message_text(text=f"{tr(lang, 'group_menu')}\n\n{tr(lang, 'target_setup_group')}", reply_markup=group_menu(lang))


async def choose_channel_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    if query.from_user:
        await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, mode="channel")
    context.user_data["active_mode"] = "channel"
    await query.edit_message_text(text=f"{tr(lang, 'channel_menu')}\n\n{tr(lang, 'target_setup_channel')}", reply_markup=channel_menu(lang))


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
