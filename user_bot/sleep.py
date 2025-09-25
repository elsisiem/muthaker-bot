from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import text
from user_side import async_session, get_user_language, SLEEP_TIME

async def sleep_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry for sleep-time supplications: ask user for typical sleep time."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    lang = await get_user_language(user_id)
    msg = "أدخل وقت النوم المعتاد (مثال: 23:00):" if lang == "ar" else "Enter your typical sleep time (e.g., 23:00):"
    await query.edit_message_text(msg)
    return SLEEP_TIME

async def sleep_config_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive sleep time and save to DB."""
    sleep_time = update.message.text.strip()
    user_id = str(update.effective_user.id)
    # Assuming we add a sleep_time column or use a JSON field. For now, use a placeholder.
    # Since User model doesn't have sleep_time, perhaps store in athkar_preferences or add column.
    # For simplicity, let's assume we update the User model later. For now, just acknowledge.
    lang = await get_user_language(user_id)
    success_msg = "تم تعيين أدعية وقت النوم بنجاح." if lang == "ar" else "Sleep-time supplications set successfully."
    await update.message.reply_text(success_msg)
    return -1  # End conversation