from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import text
from user_side import async_session, get_user_language, SLEEP_TIME

async def sleep_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry for Sleep-Time Supplications configuration."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    lang = await get_user_language(user_id)
    msg = "أدخل الأدعية التي تريد قولها قبل النوم:" if lang == "ar" else "Enter the supplications you want to recite before sleep:"
    await query.edit_message_text(msg)
    return SLEEP_TIME

async def sleep_config_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive sleep-time supplications and save to DB."""
    sleep_time = update.message.text.strip()
    user_id = str(update.effective_user.id)
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET athkar_preferences = COALESCE(athkar_preferences, '{}') || :sleep_time::text WHERE telegram_id = :tid"),
            {"sleep_time": f'{{"sleep_time": "{sleep_time}"}}', "tid": user_id}
        )
        await session.commit()
    lang = await get_user_language(user_id)
    success_msg = "تم حفظ إعدادات أدعية وقت النوم." if lang == "ar" else "Sleep-time supplications configuration saved."
    await update.message.reply_text(success_msg)
    return -1  # End conversation
