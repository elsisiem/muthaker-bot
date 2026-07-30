import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from database import get_session, ChatRepository
from services.timezone_service import resolve_timezone
from services.prayer_api import fetch_prayer_times

logger = logging.getLogger(__name__)

(
    CH_SELECT_CITY,
    CH_SELECT_COUNTRY,
    CH_SELECT_TIMEZONE,
    CH_CONFIG_FEATURES,
    CH_SET_OFFSET,
    CH_CONFIRM,
) = range(6)


def build_feature_keyboard(settings):
    buttons = [
        [InlineKeyboardButton(
            f"Morning Athkar: {'ON' if settings.morning_athkar_enabled else 'OFF'}",
            callback_data="ch:toggle:morning"
        )],
        [InlineKeyboardButton(
            f"Night Athkar: {'ON' if settings.night_athkar_enabled else 'OFF'}",
            callback_data="ch:toggle:night"
        )],
        [InlineKeyboardButton(
            f"Quran Pages: {'ON' if settings.quran_pages_enabled else 'OFF'}",
            callback_data="ch:toggle:quran"
        )],
        [InlineKeyboardButton(
            f"Status Reports: {'ON' if settings.status_message_enabled else 'OFF'}",
            callback_data="ch:toggle:status"
        )],
        [InlineKeyboardButton(
            f"Morning Offset: {settings.morning_offset_minutes} min",
            callback_data="ch:offset:morning"
        )],
        [InlineKeyboardButton(
            f"Night Offset: {settings.night_offset_minutes} min",
            callback_data="ch:offset:night"
        )],
        [InlineKeyboardButton(
            f"Quran Offset: {settings.quran_offset_minutes} min",
            callback_data="ch:offset:quran"
        )],
        [InlineKeyboardButton("Done / Confirm", callback_data="ch:done")],
    ]
    return InlineKeyboardMarkup(buttons)


async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "The /setup_channel command must be used in a channel or group where you are an admin."
        )
        return False

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text(
                "Only channel/group admins can configure the bot for this chat."
            )
            return False
    except Exception:
        await update.message.reply_text(
            "Could not verify admin status. Please make sure you're an admin."
        )
        return False

    return True


async def start_channel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_admin(update, context):
        return ConversationHandler.END

    chat = update.effective_chat
    session = get_session()
    try:
        db_chat = ChatRepository.get_or_create(session, chat.id, chat.title, chat.type, update.effective_user.id)
        settings = ChatRepository.get_settings(session, chat.id)
        session.commit()

        context.user_data["chat_setup"] = {"chat_id": chat.id}

        await update.message.reply_text(
            "Channel Setup\n\n"
            f"City: {settings.city}\n"
            "Enter the city name for prayer time calculations\n"
            "(e.g., 'Cairo', 'Makkah', 'London'):"
        )
        return CH_SELECT_CITY
    finally:
        session.close()


async def handle_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip()
    context.user_data["chat_setup"]["city"] = city

    await update.message.reply_text(
        "Enter the country name (e.g., 'Egypt', 'Saudi Arabia', 'UK'):\n"
        "Or type 'skip' to use the city name only."
    )
    return CH_SELECT_COUNTRY


async def handle_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "skip":
        context.user_data["chat_setup"]["country"] = ""
    else:
        context.user_data["chat_setup"]["country"] = text

    await update.message.reply_text(
        "Enter the timezone for this channel (e.g., 'Africa/Cairo', 'Asia/Riyadh', 'Europe/London'):\n"
        "This is needed to schedule messages at the right local time."
    )
    return CH_SELECT_TIMEZONE


async def handle_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    tz_name = resolve_timezone(text)

    if not tz_name:
        await update.message.reply_text(
            "Could not find that timezone. Try a format like 'Africa/Cairo' or 'Asia/Riyadh':"
        )
        return CH_SELECT_TIMEZONE

    context.user_data["chat_setup"]["timezone"] = tz_name

    # Verify prayer times work for the city
    city = context.user_data["chat_setup"]["city"]
    country = context.user_data["chat_setup"].get("country", "")
    times = await fetch_prayer_times(city, country)

    if not times:
        await update.message.reply_text(
            f"Could not find prayer times for '{city}'. Please check the city name and try again:"
        )
        return CH_SELECT_CITY

    # Save initial settings
    chat_id = context.user_data["chat_setup"]["chat_id"]
    session = get_session()
    try:
        db_chat = ChatRepository.get_or_create(session, chat_id, is_active=True)
        settings = ChatRepository.get_settings(session, chat_id)
        ChatRepository.update_settings(session, settings,
                                       city=city,
                                       country=country,
                                       timezone=tz_name)
        session.commit()

        await update.message.reply_text(
            f"Prayer times found for {city}!\n"
            f"Timezone: {tz_name}\n\n"
            "Now configure which features you want:",
            reply_markup=build_feature_keyboard(settings),
        )
        return CH_CONFIG_FEATURES
    finally:
        session.close()


async def handle_feature_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = context.user_data["chat_setup"]["chat_id"]

    session = get_session()
    try:
        settings = ChatRepository.get_settings(session, chat_id)

        if data == "ch:toggle:morning":
            ChatRepository.update_settings(session, settings, morning_athkar_enabled=not settings.morning_athkar_enabled)
        elif data == "ch:toggle:night":
            ChatRepository.update_settings(session, settings, night_athkar_enabled=not settings.night_athkar_enabled)
        elif data == "ch:toggle:quran":
            ChatRepository.update_settings(session, settings, quran_pages_enabled=not settings.quran_pages_enabled)
        elif data == "ch:toggle:status":
            ChatRepository.update_settings(session, settings, status_message_enabled=not settings.status_message_enabled)
        elif data == "ch:done":
            await query.edit_message_text(
                get_settings_summary(settings),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Confirm & Start", callback_data="ch:confirm"),
                    InlineKeyboardButton("Edit More", callback_data="ch:edit"),
                ]]),
            )
            session.commit()
            return CH_CONFIRM

        session.commit()
        await query.edit_message_reply_markup(reply_markup=build_feature_keyboard(settings))
        return CH_CONFIG_FEATURES
    finally:
        session.close()


async def handle_offset_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = context.user_data["chat_setup"]["chat_id"]

    if data == "ch:offset:morning":
        context.user_data["chat_setup"]["setting_offset"] = "morning"
        await query.edit_message_text(
            "Enter the morning athkar offset in minutes after Fajr (default: 35):",
        )
        return CH_SET_OFFSET
    elif data == "ch:offset:night":
        context.user_data["chat_setup"]["setting_offset"] = "night"
        await query.edit_message_text(
            "Enter the night athkar offset in minutes after Asr (default: 30):",
        )
        return CH_SET_OFFSET
    elif data == "ch:offset:quran":
        context.user_data["chat_setup"]["setting_offset"] = "quran"
        await query.edit_message_text(
            "Enter the Quran pages offset in minutes after night athkar (default: 10):",
        )
        return CH_SET_OFFSET

    return CH_CONFIG_FEATURES


async def handle_offset_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.user_data["chat_setup"]["chat_id"]
    offset_type = context.user_data["chat_setup"].get("setting_offset")

    try:
        value = int(update.message.text.strip())
        if value < 0 or value > 180:
            await update.message.reply_text("Please enter a value between 0 and 180 minutes:")
            return CH_SET_OFFSET
    except ValueError:
        await update.message.reply_text("Please enter a valid number:")
        return CH_SET_OFFSET

    session = get_session()
    try:
        settings = ChatRepository.get_settings(session, chat_id)
        if offset_type == "morning":
            ChatRepository.update_settings(session, settings, morning_offset_minutes=value)
        elif offset_type == "night":
            ChatRepository.update_settings(session, settings, night_offset_minutes=value)
        elif offset_type == "quran":
            ChatRepository.update_settings(session, settings, quran_offset_minutes=value)
        session.commit()

        await update.message.reply_text(
            f"Offset updated!\n\nConfigure your features:",
            reply_markup=build_feature_keyboard(settings),
        )
        return CH_CONFIG_FEATURES
    finally:
        session.close()


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = context.user_data["chat_setup"]["chat_id"]

    if data == "ch:edit":
        session = get_session()
        try:
            settings = ChatRepository.get_settings(session, chat_id)
            await query.edit_message_text(
                "Configure your features:",
                reply_markup=build_feature_keyboard(settings),
            )
            return CH_CONFIG_FEATURES
        finally:
            session.close()

    elif data == "ch:confirm":
        session = get_session()
        try:
            ChatRepository.update(session, ChatRepository.get_or_create(session, chat_id), is_active=True)
            settings = ChatRepository.get_settings(session, chat_id)
            session.commit()

            await query.edit_message_text(
                "Channel setup complete! The bot will now:\n"
                f"• Send morning athkar {settings.morning_offset_minutes} min after Fajr ({'ON' if settings.morning_athkar_enabled else 'OFF'})\n"
                f"• Send night athkar {settings.night_offset_minutes} min after Asr ({'ON' if settings.night_athkar_enabled else 'OFF'})\n"
                f"• Send Quran pages {settings.quran_offset_minutes} min after night athkar ({'ON' if settings.quran_pages_enabled else 'OFF'})\n"
                f"• Send hourly status reports ({'ON' if settings.status_message_enabled else 'OFF'})\n\n"
                f"Use /channel_status to see current settings.\n"
                f"Use /setup_channel to reconfigure.\n"
                f"Use /channel_disable to pause the bot in this chat."
            )
            context.user_data.pop("chat_setup", None)
            return ConversationHandler.END
        finally:
            session.close()

    return CH_CONFIRM


async def cancel_channel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("chat_setup", None)
    await update.message.reply_text("Channel setup cancelled.")
    return ConversationHandler.END


def get_settings_summary(settings):
    return (
        "**Channel Settings Summary:**\n\n"
        f"City: {settings.city}\n"
        f"Timezone: {settings.timezone}\n"
        f"Morning Athkar: {'ON' if settings.morning_athkar_enabled else 'OFF'} ({settings.morning_offset_minutes} min after Fajr)\n"
        f"Night Athkar: {'ON' if settings.night_athkar_enabled else 'OFF'} ({settings.night_offset_minutes} min after Asr)\n"
        f"Quran Pages: {'ON' if settings.quran_pages_enabled else 'OFF'} ({settings.quran_offset_minutes} min after night athkar)\n"
        f"Status Reports: {'ON' if settings.status_message_enabled else 'OFF'}"
    )


def register_channel_handlers(application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("setup_channel", start_channel_setup)],
        states={
            CH_SELECT_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city)],
            CH_SELECT_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_country)],
            CH_SELECT_TIMEZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_timezone)],
            CH_CONFIG_FEATURES: [
                CallbackQueryHandler(handle_feature_toggle, pattern=r"^ch:toggle:"),
                CallbackQueryHandler(handle_offset_setup, pattern=r"^ch:offset:"),
                CallbackQueryHandler(handle_feature_toggle, pattern=r"^ch:done"),
            ],
            CH_SET_OFFSET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_offset_value)],
            CH_CONFIRM: [
                CallbackQueryHandler(handle_confirmation, pattern=r"^ch:confirm"),
                CallbackQueryHandler(handle_confirmation, pattern=r"^ch:edit"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_channel_setup)],
        name="channel_setup",
        persistent=False,
    )
    application.add_handler(conv_handler)

    # Commands for channel management outside conversation
    from .channel_commands import register_channel_commands
    register_channel_commands(application)