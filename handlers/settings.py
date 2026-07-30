import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from i18n import t
from keyboards import (
    language_keyboard, settings_menu_keyboard, timezone_choices_keyboard,
    schedule_management_keyboard, sleep_preset_keyboard, prayer_settings_keyboard,
    back_keyboard, confirm_keyboard, main_menu_keyboard,
)
from database import get_session, UserRepository, ScheduleRepository, SettingsRepository

logger = logging.getLogger(__name__)


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    user = update.effective_user
    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user.id)
        lang = db_user.language or "en"

        if data == "menu:language":
            await query.edit_message_text(
                t("select_language", lang),
                reply_markup=language_keyboard(db_user.language),
            )

        elif data == "menu:timezone":
            await query.edit_message_text(
                t("timezone_prompt", lang),
                reply_markup=timezone_choices_keyboard(lang=lang),
            )

        elif data == "menu:schedules":
            schedules = ScheduleRepository.get_for_user(session, user.id)
            if not schedules:
                await query.edit_message_text(
                    t("no_schedules", lang),
                    reply_markup=back_keyboard(),
                )
            else:
                await query.edit_message_text(
                    t("schedule_list", lang),
                    reply_markup=schedule_management_keyboard(schedules, lang),
                )

        elif data == "menu:sleep":
            sleep_info = SettingsRepository.get_sleep(session, user.id)
            if sleep_info.is_enabled:
                text = t("sleep_set", lang,
                         start=sleep_info.sleep_start_hour,
                         start_min=sleep_info.sleep_start_minute,
                         end=sleep_info.sleep_end_hour,
                         end_min=sleep_info.sleep_end_minute)
            else:
                text = t("sleep_disabled", lang)
            await query.edit_message_text(
                text + "\n\n" + t("select_new", lang),
                reply_markup=sleep_preset_keyboard(lang),
            )

        elif data == "menu:prayer":
            prayer = SettingsRepository.get_prayer(session, user.id)
            city_text = f"City: {prayer.city}" if prayer and prayer.city else t("prayer_not_set", lang)
            await query.edit_message_text(
                city_text + "\n\n" + t("prayer_settings_menu", lang),
                reply_markup=prayer_settings_keyboard(prayer, lang),
            )

        elif data == "menu:status":
            await show_status_inline(query, session, db_user, lang)

        elif data == "menu:delete":
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            await query.edit_message_text(
                t("delete_confirm", lang),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t("yes", lang), callback_data="del_confirm:yes"),
                    InlineKeyboardButton(t("no", lang), callback_data="del_confirm:no"),
                ]]),
            )

        elif data == "menu:main":
            await query.edit_message_text(
                t("settings_menu", lang),
                reply_markup=settings_menu_keyboard(lang),
            )

        session.commit()
    finally:
        session.close()


async def handle_language_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang_code = query.data.split(":")[1]

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        UserRepository.update(session, db_user, language=lang_code)
        session.commit()
        await query.edit_message_text(
            t("language_set", lang_code) + "\n\n" + t("settings_menu", lang_code),
            reply_markup=settings_menu_keyboard(lang_code),
        )
    finally:
        session.close()


async def handle_timezone_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        lang = db_user.language or "en"

        if data.startswith("tz:select:"):
            tz_name = data.split(":", 2)[2]
            UserRepository.update(session, db_user, timezone=tz_name)
            session.commit()
            await query.edit_message_text(
                t("timezone_set", lang, timezone=tz_name),
                reply_markup=back_keyboard(),
            )
        elif data.startswith("tz:page:"):
            page = int(data.split(":")[2])
            await query.edit_message_reply_markup(
                reply_markup=timezone_choices_keyboard(page=page, lang=lang),
            )

    finally:
        session.close()


async def handle_sleep_preset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset = query.data.split(":")[1]

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        lang = db_user.language or "en"
        sleep_settings = SettingsRepository.get_sleep(session, db_user.id)

        from config import SLEEP_PRESETS
        if preset in SLEEP_PRESETS:
            preset_data = SLEEP_PRESETS[preset]
            if preset == "none":
                SettingsRepository.update_sleep(sleep_settings, is_enabled=False)
                text = t("sleep_disabled", lang)
            else:
                start_h, start_m = preset_data["start"]
                end_h, end_m = preset_data["end"]
                SettingsRepository.update_sleep(sleep_settings,
                                                is_enabled=True,
                                                sleep_start_hour=start_h,
                                                sleep_start_minute=start_m,
                                                sleep_end_hour=end_h,
                                                sleep_end_minute=end_m)
                text = t("sleep_set", lang, start=start_h, start_min=start_m, end=end_h, end_min=end_m)

            session.commit()
            await query.edit_message_text(
                text,
                reply_markup=back_keyboard(),
            )

    finally:
        session.close()


async def handle_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        lang = db_user.language or "en"

        if data == "sched:add":
            context.user_data["adding_schedule"] = True
            await query.edit_message_text(
                "Starting schedule setup... Use /setup to configure a new athkar schedule.",
                reply_markup=back_keyboard(),
            )

        elif data.startswith("sched:toggle:"):
            sched_id = int(data.split(":")[2])
            schedules = ScheduleRepository.get_for_user(session, db_user.id)
            for s in schedules:
                if s.id == sched_id:
                    ScheduleRepository.update(session, s, is_active=not s.is_active)
                    break
            session.commit()
            schedules = ScheduleRepository.get_for_user(session, db_user.id)
            await query.edit_message_text(
                t("schedule_list", lang),
                reply_markup=schedule_management_keyboard(schedules, lang),
            )

        elif data.startswith("sched:delete:"):
            sched_id = int(data.split(":")[2])
            ScheduleRepository.delete(session, sched_id)
            session.commit()
            schedules = ScheduleRepository.get_for_user(session, db_user.id)
            if not schedules:
                await query.edit_message_text(
                    t("no_schedules", lang),
                    reply_markup=back_keyboard(),
                )
            else:
                await query.edit_message_text(
                    t("schedule_list", lang),
                    reply_markup=schedule_management_keyboard(schedules, lang),
                )

    finally:
        session.close()


async def handle_prayer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        lang = db_user.language or "en"
        prayer = SettingsRepository.get_prayer(session, db_user.id)

        if data == "prayer:morning_toggle":
            SettingsRepository.update_prayer(prayer, morning_athkar_enabled=not prayer.morning_athkar_enabled)
            session.commit()
            await query.edit_message_text(
                "Morning athkar toggled!\n\n" + t("prayer_settings_menu", lang),
                reply_markup=prayer_settings_keyboard(prayer, lang),
            )

        elif data == "prayer:night_toggle":
            SettingsRepository.update_prayer(prayer, night_athkar_enabled=not prayer.night_athkar_enabled)
            session.commit()
            await query.edit_message_text(
                "Night athkar toggled!\n\n" + t("prayer_settings_menu", lang),
                reply_markup=prayer_settings_keyboard(prayer, lang),
            )

        elif data == "prayer:city":
            context.user_data["awaiting_prayer_city"] = True
            await query.edit_message_text(
                t("prayer_city_prompt", lang),
                reply_markup=back_keyboard(),
            )

        elif data == "prayer:morning_offset":
            context.user_data["awaiting_morning_offset"] = True
            await query.edit_message_text(
                f"Current morning athkar offset: {prayer.morning_offset_minutes} minutes after Fajr.\nEnter new offset in minutes:",
                reply_markup=back_keyboard(),
            )

        elif data == "prayer:night_offset":
            context.user_data["awaiting_night_offset"] = True
            await query.edit_message_text(
                f"Current night athkar offset: {prayer.night_offset_minutes} minutes after Asr.\nEnter new offset in minutes:",
                reply_markup=back_keyboard(),
            )

        elif data == "prayer:back":
            await query.edit_message_text(
                t("settings_menu", lang),
                reply_markup=settings_menu_keyboard(lang),
            )

    finally:
        session.close()


async def handle_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        lang = db_user.language or "en"

        if data == "del_confirm:yes":
            UserRepository.delete(session, db_user.id)
            session.commit()
            await query.edit_message_text(t("deleted", lang))
        else:
            await query.edit_message_text(
                t("settings_menu", lang),
                reply_markup=settings_menu_keyboard(lang),
            )
    finally:
        session.close()


async def handle_prayer_city_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_prayer_city"):
        return

    context.user_data["awaiting_prayer_city"] = False
    city = update.message.text.strip()
    lang = "en"

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        lang = db_user.language or "en"
        prayer = SettingsRepository.get_prayer(session, db_user.id)

        from services.prayer_api import fetch_prayer_times
        times = await fetch_prayer_times(city)
        if times:
            SettingsRepository.update_prayer(prayer, city=city)
            session.commit()
            await update.message.reply_text(
                t("prayer_city_set", lang, city=city),
                reply_markup=prayer_settings_keyboard(prayer, lang),
            )
        else:
            await update.message.reply_text(
                t("prayer_not_found", lang, city=city),
            )
    finally:
        session.close()


async def handle_morning_offset_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_morning_offset"):
        return

    context.user_data["awaiting_morning_offset"] = False
    lang = "en"

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        lang = db_user.language or "en"
        prayer = SettingsRepository.get_prayer(session, db_user.id)

        try:
            offset = int(update.message.text.strip())
            if 0 <= offset <= 180:
                SettingsRepository.update_prayer(prayer, morning_offset_minutes=offset)
                session.commit()
                await update.message.reply_text(
                    f"Morning athkar offset set to {offset} minutes after Fajr.",
                    reply_markup=prayer_settings_keyboard(prayer, lang),
                )
            else:
                await update.message.reply_text(
                    "Please enter a value between 0 and 180 minutes.",
                )
        except ValueError:
            await update.message.reply_text(
                "Please enter a valid number.",
            )
    finally:
        session.close()


async def handle_night_offset_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_night_offset"):
        return

    context.user_data["awaiting_night_offset"] = False
    lang = "en"

    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, update.effective_user.id)
        lang = db_user.language or "en"
        prayer = SettingsRepository.get_prayer(session, db_user.id)

        try:
            offset = int(update.message.text.strip())
            if 0 <= offset <= 180:
                SettingsRepository.update_prayer(prayer, night_offset_minutes=offset)
                session.commit()
                await update.message.reply_text(
                    f"Night athkar offset set to {offset} minutes after Asr.",
                    reply_markup=prayer_settings_keyboard(prayer, lang),
                )
            else:
                await update.message.reply_text(
                    "Please enter a value between 0 and 180 minutes.",
                )
        except ValueError:
            await update.message.reply_text(
                "Please enter a valid number.",
            )
    finally:
        session.close()


async def get_user_lang(user_id: int) -> str:
    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user_id)
        return db_user.language or "en"
    finally:
        session.close()


async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user.id)
        await show_status_inline(update, session, db_user, db_user.language or "en")
    finally:
        session.close()


async def show_status_inline(update_or_query, session, db_user, lang: str):
    schedules = ScheduleRepository.get_active_for_user(session, db_user.id)
    sleep = SettingsRepository.get_sleep(session, db_user.id)
    prayer = SettingsRepository.get_prayer(session, db_user.id)

    if sleep.is_enabled:
        sleep_text = t("sleep_set", lang,
                       start=sleep.sleep_start_hour,
                       start_min=sleep.sleep_start_minute,
                       end=sleep.sleep_end_hour,
                       end_min=sleep.sleep_end_minute)
    else:
        sleep_text = t("sleep_disabled", lang)

    morning_status = t("morning_enabled", lang, offset=prayer.morning_offset_minutes) if prayer.morning_athkar_enabled else t("morning_disabled", lang)
    night_status = t("night_enabled", lang, offset=prayer.night_offset_minutes) if prayer.night_athkar_enabled else t("night_disabled", lang)

    text = t("status_message", lang,
             language=db_user.language or "en",
             timezone=db_user.timezone,
             schedule_count=len(schedules),
             sleep_summary=sleep_text,
             prayer_city=prayer.city if prayer else "N/A",
             morning_status=morning_status,
             night_status=night_status)

    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(
            text,
            reply_markup=back_keyboard(),
        )
    else:
        await update_or_query.message.reply_text(
            text,
            reply_markup=back_keyboard(),
        )


def register_settings_handlers(application):
    application.add_handler(CallbackQueryHandler(handle_menu_callback, pattern=r"^menu:"))
    application.add_handler(CallbackQueryHandler(handle_language_change, pattern=r"^lang:"))
    application.add_handler(CallbackQueryHandler(handle_timezone_select, pattern=r"^tz:"))
    application.add_handler(CallbackQueryHandler(handle_sleep_preset, pattern=r"^sleep:"))
    application.add_handler(CallbackQueryHandler(handle_schedule_callback, pattern=r"^sched:"))
    application.add_handler(CallbackQueryHandler(handle_prayer_callback, pattern=r"^prayer:"))
    application.add_handler(CallbackQueryHandler(handle_delete_confirm, pattern=r"^del_confirm:"))

    from telegram.ext import MessageHandler, filters
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prayer_city_text), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_morning_offset_text), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_night_offset_text), group=1)