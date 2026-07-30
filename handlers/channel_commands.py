import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from database import get_session, ChatRepository

logger = logging.getLogger(__name__)


async def channel_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if update.effective_chat.type == "private":
        await update.message.reply_text("This command works in channels and groups.")
        return

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("Only admins can check channel status.")
            return
    except Exception:
        return

    session = get_session()
    try:
        db_chat = ChatRepository.get_or_create(session, chat_id)
        if not db_chat:
            await update.message.reply_text(
                "This chat is not set up yet. Use /setup_channel to configure."
            )
            return

        settings = ChatRepository.get_settings(session, chat_id)

        text = (
            "**Channel Status**\n\n"
            f"Active: {'Yes' if db_chat.is_active else 'Paused'}\n"
            f"City: {settings.city}\n"
            f"Country: {settings.country or 'N/A'}\n"
            f"Timezone: {settings.timezone}\n\n"
            "**Features:**\n"
            f"Morning Athkar: {'ON' if settings.morning_athkar_enabled else 'OFF'} ({settings.morning_offset_minutes}m after Fajr)\n"
            f"Night Athkar: {'ON' if settings.night_athkar_enabled else 'OFF'} ({settings.night_offset_minutes}m after Asr)\n"
            f"Quran Pages: {'ON' if settings.quran_pages_enabled else 'OFF'} ({settings.quran_offset_minutes}m after night)\n"
            f"Status Reports: {'ON' if settings.status_message_enabled else 'OFF'}\n\n"
            "Commands:\n"
            "/setup_channel - Reconfigure\n"
            "/channel_disable - Pause the bot\n"
            "/channel_enable - Resume the bot"
        )

        await update.message.reply_text(text, parse_mode="Markdown")
    finally:
        session.close()


async def channel_disable_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if update.effective_chat.type == "private":
        return

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("Only admins can manage the bot.")
            return
    except Exception:
        return

    session = get_session()
    try:
        db_chat = ChatRepository.get_or_create(session, chat_id)
        ChatRepository.update(session, db_chat, is_active=False)
        session.commit()
        await update.message.reply_text(
            "Bot paused for this chat. Use /channel_enable to resume."
        )
    finally:
        session.close()


async def channel_enable_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if update.effective_chat.type == "private":
        return

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("Only admins can manage the bot.")
            return
    except Exception:
        return

    session = get_session()
    try:
        db_chat = ChatRepository.get_or_create(session, chat_id)
        ChatRepository.update(session, db_chat, is_active=True)
        session.commit()
        await update.message.reply_text(
            "Bot resumed! Athkar and Quran pages will be sent as configured."
        )
    finally:
        session.close()


def register_channel_commands(application):
    application.add_handler(CommandHandler("channel_status", channel_status_command))
    application.add_handler(CommandHandler("channel_disable", channel_disable_command))
    application.add_handler(CommandHandler("channel_enable", channel_enable_command))