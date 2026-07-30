import re
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)
from telegram.constants import ParseMode

from i18n import t, get_languages_list, register_language
from i18n.en import translations as en_translations
from i18n.ar import translations as ar_translations
from keyboards import (
    language_keyboard, confirm_keyboard, timezone_choices_keyboard,
    athkar_type_keyboard, schedule_mode_keyboard, interval_keyboard,
    goal_keyboard, sleep_preset_keyboard, skip_or_enter_keyboard,
    main_menu_keyboard,
)
from database import get_session, UserRepository, ScheduleRepository, SettingsRepository
from services.timezone_service import detect_timezone_from_location, resolve_timezone

register_language("en", en_translations)
register_language("ar", ar_translations)

(
    SELECT_LANGUAGE,
    SELECT_TIMEZONE,
    SELECT_ATHKAR_TYPE,
    SELECT_SCHEDULE_MODE,
    SELECT_SCHEDULE_VALUE,
    SELECT_SLEEP,
    SELECT_SLEEP_CUSTOM,
    SELECT_PRAYER_CITY,
    CONFIRMATION,
) = range(9)


async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user.id, user.username, user.first_name)
        lang = db_user.language or "en"
        context.user_data["onboarding"] = {"lang": lang}
        session.commit()

        await update.message.reply_text(
            t("select_language", lang),
            reply_markup=language_keyboard(),
        )
        return SELECT_LANGUAGE
    finally:
        session.close()


async def handle_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang_code = query.data.split(":")[1]
    context.user_data["onboarding"]["lang"] = lang_code

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        UserRepository.update(session, db_user, language=lang_code)
        session.commit()
    finally:
        session.close()

    await query.edit_message_text(t("language_set", lang_code))

    await query.message.reply_text(
        t("timezone_prompt", lang_code),
        reply_markup=timezone_choices_keyboard(lang=lang_code),
    )
    return SELECT_TIMEZONE


async def handle_timezone_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    location = update.message.location

    tz_name = detect_timezone_from_location(location.latitude, location.longitude)
    if tz_name:
        context.user_data["onboarding"]["timezone"] = tz_name
        await update.message.reply_text(
            t("timezone_detected", lang, timezone=tz_name),
            reply_markup=confirm_keyboard(lang),
        )
        return SELECT_TIMEZONE
    else:
        await update.message.reply_text(
            t("timezone_invalid", lang),
            reply_markup=timezone_choices_keyboard(lang=lang),
        )
        return SELECT_TIMEZONE


async def handle_timezone_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    text = update.message.text.strip()

    tz_name = resolve_timezone(text)
    if tz_name:
        context.user_data["onboarding"]["timezone"] = tz_name
        await update.message.reply_text(
            t("timezone_detected", lang, timezone=tz_name),
            reply_markup=confirm_keyboard(lang),
        )
        return SELECT_TIMEZONE
    else:
        await update.message.reply_text(
            t("timezone_invalid", lang),
            reply_markup=timezone_choices_keyboard(lang=lang),
        )
        return SELECT_TIMEZONE


async def handle_timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    data = query.data

    if data == "tz:share":
        await query.edit_message_text(
            t("timezone_prompt", lang) + "\n\n" + t("privacy_notice", lang),
            reply_markup=skip_or_enter_keyboard("tz:back", lang),
        )
        return SELECT_TIMEZONE

    elif data.startswith("tz:select:"):
        tz_name = data.split(":", 2)[2]
        context.user_data["onboarding"]["timezone"] = tz_name
        await query.edit_message_text(t("timezone_set", lang, timezone=tz_name))
        await query.message.reply_text(
            t("athkar_type_prompt", lang),
            reply_markup=athkar_type_keyboard(lang),
        )
        return SELECT_ATHKAR_TYPE

    elif data.startswith("tz:page:"):
        page = int(data.split(":")[2])
        await query.edit_message_reply_markup(
            reply_markup=timezone_choices_keyboard(page=page, lang=lang),
        )
        return SELECT_TIMEZONE

    elif data.startswith("confirm:yes"):
        tz_name = context.user_data["onboarding"].get("timezone", "UTC")
        await query.edit_message_text(t("timezone_set", lang, timezone=tz_name))
        await query.message.reply_text(
            t("athkar_type_prompt", lang),
            reply_markup=athkar_type_keyboard(lang),
        )
        return SELECT_ATHKAR_TYPE

    elif data.startswith("confirm:no") or data == "tz:back":
        await query.edit_message_text(
            t("timezone_prompt", lang),
            reply_markup=timezone_choices_keyboard(lang=lang),
        )
        return SELECT_TIMEZONE

    elif data == "tz:manual":
        await query.edit_message_text(
            t("timezone_prompt", lang) + "\n\nType your timezone (e.g., 'America/New_York' or city name 'Cairo').",
        )
        return SELECT_TIMEZONE

    return SELECT_TIMEZONE


async def handle_athkar_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("onboarding", {}).get("lang", "en")

    athkar_type = query.data.split(":")[1]
    context.user_data["onboarding"]["athkar_type"] = athkar_type

    await query.edit_message_text(t("athkar_type_set", lang, athkar_type=athkar_type))

    await query.message.reply_text(
        t("schedule_mode_prompt", lang),
        reply_markup=schedule_mode_keyboard(lang),
    )
    return SELECT_SCHEDULE_MODE


async def handle_schedule_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("onboarding", {}).get("lang", "en")

    mode = query.data.split(":")[1]
    context.user_data["onboarding"]["schedule_mode"] = mode

    if mode == "interval":
        await query.edit_message_text(
            t("schedule_interval_prompt", lang),
            reply_markup=interval_keyboard(lang),
        )
    else:
        await query.edit_message_text(
            t("schedule_goal_prompt", lang),
            reply_markup=goal_keyboard(lang),
        )
    return SELECT_SCHEDULE_VALUE


async def handle_schedule_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("onboarding", {}).get("lang", "en")

    value = query.data.split(":")[1]
    if value.lower() in ["custom", "مخصص"]:
        await query.edit_message_text("Enter the interval in minutes (e.g., 20):")
        return SELECT_SCHEDULE_VALUE
    else:
        interval = int(value)
        context.user_data["onboarding"]["schedule_value"] = interval
        await query.edit_message_text(
            t("schedule_set", lang, mode="Interval", value=f"Every {interval} min"),
        )
        return await after_schedule_set(query, lang)


async def handle_schedule_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("onboarding", {}).get("lang", "en")

    value = query.data.split(":")[1]
    if value.lower() in ["custom", "مخصص"]:
        await query.edit_message_text("Enter the number of athkar per day (e.g., 300):")
        return SELECT_SCHEDULE_VALUE
    else:
        goal = int(value)
        context.user_data["onboarding"]["schedule_value"] = goal
        await query.edit_message_text(
            t("schedule_set", lang, mode="Daily Goal", value=f"{goal}/day"),
        )
        return await after_schedule_set(query, lang)


async def handle_schedule_custom_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    mode = context.user_data.get("onboarding", {}).get("schedule_mode", "interval")

    try:
        value = int(re.sub(r"[^0-9]", "", update.message.text))
        if value <= 0:
            raise ValueError
    except ValueError:
        if mode == "interval":
            await update.message.reply_text(
                "Please enter a valid number of minutes.",
                reply_markup=interval_keyboard(lang),
            )
        else:
            await update.message.reply_text(
                "Please enter a valid number.",
                reply_markup=goal_keyboard(lang),
            )
        return SELECT_SCHEDULE_VALUE

    context.user_data["onboarding"]["schedule_value"] = value
    display = f"Every {value} min" if mode == "interval" else f"{value}/day"
    await update.message.reply_text(t("schedule_set", lang, mode=mode.title(), value=display))

    await update.message.reply_text(
        t("sleep_prompt", lang),
        reply_markup=sleep_preset_keyboard(lang),
    )
    return SELECT_SLEEP


async def after_schedule_set(query, lang: str):
    await query.message.reply_text(
        t("sleep_prompt", lang),
        reply_markup=sleep_preset_keyboard(lang),
    )
    return SELECT_SLEEP


async def handle_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("onboarding", {}).get("lang", "en")

    preset = query.data.split(":")[1]

    from config import SLEEP_PRESETS
    if preset in SLEEP_PRESETS:
        preset_data = SLEEP_PRESETS[preset]
        if preset == "none":
            context.user_data["onboarding"]["sleep"] = {"enabled": False}
            await query.edit_message_text(t("sleep_disabled", lang))
        else:
            start_h, start_m = preset_data["start"]
            end_h, end_m = preset_data["end"]
            context.user_data["onboarding"]["sleep"] = {
                "enabled": True,
                "start_hour": start_h,
                "start_minute": start_m,
                "end_hour": end_h,
                "end_minute": end_m,
            }
            await query.edit_message_text(
                t("sleep_set", lang, start=start_h, start_min=start_m, end=end_h, end_min=end_m),
            )

        await query.message.reply_text(
            t("prayer_city_prompt", lang),
            reply_markup=skip_or_enter_keyboard("prayer:skip", lang),
        )
        return SELECT_PRAYER_CITY

    elif preset == "custom":
        await query.edit_message_text(t("sleep_custom_prompt", lang))
        return SELECT_SLEEP_CUSTOM

    return SELECT_SLEEP


async def handle_sleep_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    text = update.message.text.strip()

    pattern = r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})"
    match = re.match(pattern, text)
    if match:
        start_h, start_m, end_h, end_m = map(int, match.groups())
        if 0 <= start_h <= 23 and 0 <= start_m <= 59 and 0 <= end_h <= 23 and 0 <= end_m <= 59:
            context.user_data["onboarding"]["sleep"] = {
                "enabled": True,
                "start_hour": start_h,
                "start_minute": start_m,
                "end_hour": end_h,
                "end_minute": end_m,
            }
            await update.message.reply_text(
                t("sleep_set", lang, start=start_h, start_min=start_m, end=end_h, end_min=end_m),
            )
            await update.message.reply_text(
                t("prayer_city_prompt", lang),
                reply_markup=skip_or_enter_keyboard("prayer:skip", lang),
            )
            return SELECT_PRAYER_CITY

    await update.message.reply_text(
        "Invalid format. Please use HH:MM-HH:MM (e.g., 23:00-6:00):",
    )
    return SELECT_SLEEP_CUSTOM


async def handle_prayer_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    text = update.message.text.strip()

    context.user_data["onboarding"]["prayer_city"] = text

    from services.prayer_api import fetch_prayer_times
    times = await fetch_prayer_times(text)
    if times:
        await update.message.reply_text(t("prayer_city_set", lang, city=text))
    else:
        await update.message.reply_text(t("prayer_not_found", lang, city=text) + "\nTry another city:")
        return SELECT_PRAYER_CITY

    return await show_confirmation(update, context)


async def handle_prayer_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("onboarding", {}).get("lang", "en")

    context.user_data["onboarding"]["prayer_city"] = None
    await query.edit_message_text(t("prayer_city_skipped", lang))

    return await show_confirmation_callback(query, context)


async def show_confirmation(update_or_query, context):
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    data = context.user_data["onboarding"]

    athkar_type = data.get("athkar_type", "mixed")
    mode = data.get("schedule_mode", "interval")
    value = data.get("schedule_value", 15)
    schedule_summary = f"Every {value} min" if mode == "interval" else f"{value}/day"

    sleep_data = data.get("sleep", {})
    if sleep_data.get("enabled", True):
        sleep_summary = f"{sleep_data['start_hour']:02d}:{sleep_data['start_minute']:02d}-{sleep_data['end_hour']:02d}:{sleep_data['end_minute']:02d}"
    else:
        sleep_summary = "Disabled"

    prayer_city = data.get("prayer_city") or "Not set"

    text = t("confirm_setup", lang,
             language=data.get("lang", "en"),
             timezone=data.get("timezone", "UTC"),
             athkar_type=athkar_type,
             schedule_summary=schedule_summary,
             sleep_summary=sleep_summary,
             prayer_city=prayer_city)

    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text(
            text,
            reply_markup=confirm_keyboard(lang),
        )
    else:
        await update_or_query.message.reply_text(
            text,
            reply_markup=confirm_keyboard(lang),
        )
    return CONFIRMATION


async def show_confirmation_callback(query, context):
    return await show_confirmation(query, context)


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    data = query.data

    if data == "confirm:yes":
        await save_onboarding_data(update, context)
        await query.edit_message_text(t("setup_complete", lang))
        context.user_data.pop("onboarding", None)
        return ConversationHandler.END
    else:
        await query.edit_message_text(
            t("setup_cancelled", lang),
            reply_markup=main_menu_keyboard(lang),
        )
        context.user_data.pop("onboarding", None)
        return ConversationHandler.END


async def save_onboarding_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = context.user_data["onboarding"]

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user_id)
        UserRepository.update(session, db_user,
                              language=data.get("lang", "en"),
                              timezone=data.get("timezone", "UTC"),
                              onboarding_complete=True)

        athkar_type = data.get("athkar_type", "mixed")
        mode = data.get("schedule_mode", "interval")
        value = data.get("schedule_value", 15)

        if mode == "interval":
            ScheduleRepository.create(session, user_id, athkar_type=athkar_type, mode="interval", interval_minutes=value)
        else:
            ScheduleRepository.create(session, user_id, athkar_type=athkar_type, mode="goal", daily_goal=value)

        sleep_data = data.get("sleep", {})
        sleep_settings = SettingsRepository.get_sleep(session, user_id)
        if sleep_data.get("enabled", True):
            SettingsRepository.update_sleep(sleep_settings,
                                            is_enabled=True,
                                            sleep_start_hour=sleep_data.get("start_hour", 23),
                                            sleep_start_minute=sleep_data.get("start_minute", 0),
                                            sleep_end_hour=sleep_data.get("end_hour", 5),
                                            sleep_end_minute=sleep_data.get("end_minute", 0))
        else:
            SettingsRepository.update_sleep(sleep_settings, is_enabled=False)

        prayer_city = data.get("prayer_city")
        if prayer_city:
            prayer_settings = SettingsRepository.get_prayer(session, user_id)
            SettingsRepository.update_prayer(prayer_settings, city=prayer_city)

        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


async def cancel_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get("onboarding", {}).get("lang", "en")
    context.user_data.pop("onboarding", None)
    await update.message.reply_text(
        t("setup_cancelled", lang),
        reply_markup=main_menu_keyboard(lang),
    )
    return ConversationHandler.END


def register_onboarding_handlers(application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("setup", start_onboarding)],
        states={
            SELECT_LANGUAGE: [CallbackQueryHandler(handle_language, pattern=r"^lang:")],
            SELECT_TIMEZONE: [
                MessageHandler(filters.LOCATION, handle_timezone_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone_text),
                CallbackQueryHandler(handle_timezone_callback, pattern=r"^(tz:|confirm:)"),
            ],
            SELECT_ATHKAR_TYPE: [
                CallbackQueryHandler(handle_athkar_type, pattern=r"^athkar:"),
            ],
            SELECT_SCHEDULE_MODE: [
                CallbackQueryHandler(handle_schedule_mode, pattern=r"^mode:"),
            ],
            SELECT_SCHEDULE_VALUE: [
                CallbackQueryHandler(handle_schedule_interval, pattern=r"^interval:"),
                CallbackQueryHandler(handle_schedule_goal, pattern=r"^goal:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule_custom_value),
            ],
            SELECT_SLEEP: [
                CallbackQueryHandler(handle_sleep, pattern=r"^sleep:"),
            ],
            SELECT_SLEEP_CUSTOM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sleep_custom),
            ],
            SELECT_PRAYER_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prayer_city),
                CallbackQueryHandler(handle_prayer_skip, pattern=r"^prayer:skip"),
            ],
            CONFIRMATION: [
                CallbackQueryHandler(handle_confirmation, pattern=r"^confirm:"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_onboarding)],
        name="onboarding",
        persistent=False,
    )
    application.add_handler(conv_handler)