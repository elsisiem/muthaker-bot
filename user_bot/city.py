from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import text
from db import async_session, get_user_language, CITY_INFO
import logging

logger = logging.getLogger(__name__)

async def city_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry for city/timezone configuration."""
    query = update.callback_query
    try:
        await query.answer()
        user_id = str(update.effective_user.id)
        lang = await get_user_language(user_id)
        msg = "أدخل اسم المدينة أو المنطقة الزمنية (مثال: Riyadh):" if lang == "ar" else "Enter your city or timezone (e.g., Riyadh):"
        await query.edit_message_text(msg)
        return CITY_INFO
    except Exception as e:
        logger.exception("Error in city_config_entry")
        await query.edit_message_text("An error occurred. Please try again.")

async def city_config_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive city info and save to DB."""
    try:
        city = update.message.text.strip()
        user_id = str(update.effective_user.id)
        async with async_session() as session:
            await session.execute(
                text("UPDATE users SET city = :city WHERE telegram_id = :tid"),
                {"city": city, "tid": user_id}
            )
            await session.commit()
        lang = await get_user_language(user_id)
        success_msg = "تم حفظ المدينة/المنطقة الزمنية بنجاح." if lang == "ar" else "City/Timezone saved successfully."
        await update.message.reply_text(success_msg)
        return -1  # End conversation
    except Exception as e:
        logger.exception("Error in city_config_receive")
        await update.message.reply_text("An error occurred. Please try again.")