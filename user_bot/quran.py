from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import text
import json
from user_side import async_session, get_user_language, QURAN_CHOICE, QURAN_DETAILS

async def quran_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Quran Wird configuration."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    lang = await get_user_language(user_id)
    if lang == "ar":
        keyboard = [
            [InlineKeyboardButton("عدد صفحات ثابت يوميًا", callback_data="quran_pages")],
            [InlineKeyboardButton("جزء محدد (1-30)", callback_data="quran_juz")],
            [InlineKeyboardButton("سورة محددة", callback_data="quran_surah")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("اختر وضع تلاوة القرآن:", reply_markup=reply_markup)
    else:
        keyboard = [
            [InlineKeyboardButton("Fixed Pages per Day", callback_data="quran_pages")],
            [InlineKeyboardButton("Specific Juz’ (1-30)", callback_data="quran_juz")],
            [InlineKeyboardButton("Specific Surah", callback_data="quran_surah")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Choose your Quran recitation mode:", reply_markup=reply_markup)
    return QURAN_CHOICE

async def quran_config_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the Quran Wird choice and ask for details."""
    query = update.callback_query
    await query.answer()
    choice = query.data  # "quran_pages", "quran_juz" or "quran_surah"
    context.user_data["quran_mode"] = choice
    user_id = str(update.effective_user.id)
    lang = await get_user_language(user_id)
    if choice == "quran_pages":
        msg = "أدخل عدد الصفحات التي تريد تلاوتها يوميًا (مثال: 2):" if lang == "ar" else "Enter the number of pages you want to recite per day (e.g., 2):"
    elif choice == "quran_juz":
        msg = "أدخل رقم الجزء (1-30):" if lang == "ar" else "Enter the Juz’ number (1-30):"
    else:
        msg = "أدخل اسم السورة أو رقمها:" if lang == "ar" else "Enter the Surah name or number:"
    await query.edit_message_text(msg)
    return QURAN_DETAILS

async def quran_config_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive Quran Wird configuration details and save to DB."""
    detail = update.message.text.strip()
    context.user_data["quran_detail"] = detail
    import json
    quran_settings = {
        "mode": context.user_data.get("quran_mode"),
        "detail": detail,
        "last_recited": None
    }
    user_id = str(update.effective_user.id)
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET quran_settings = :settings WHERE telegram_id = :tid"),
            {"settings": json.dumps(quran_settings), "tid": user_id}
        )
        await session.commit()
    lang = await get_user_language(user_id)
    success_msg = "تم حفظ إعدادات ورد القرآن بنجاح." if lang == "ar" else "Quran Wird settings saved successfully."
    await update.message.reply_text(success_msg)
    return -1  # End conversation
