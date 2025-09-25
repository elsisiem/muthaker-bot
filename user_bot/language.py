from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import text
from user_side import async_session, get_user_language, MAIN_MENU

async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection."""
    query = update.callback_query
    await query.answer()
    choice = query.data  # "lang_ar" or "lang_en"
    lang = "ar" if choice == "lang_ar" else "en"
    user_id = str(update.effective_user.id)
    
    # Save language to database
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET language = :lang WHERE telegram_id = :tid"),
            {"lang": lang, "tid": user_id}
        )
        await session.commit()
    
    if lang == "ar":
        message = "مرحبا بك في مذكر! اختر خيار التكوين:"
    else:
        message = "Welcome to Muthaker! Choose a configuration option:"
    
    # Present configuration options
    keyboard = [
        [InlineKeyboardButton("تكوين تذكير الأذكار" if lang == "ar" else "Configure Athkar Reminders", callback_data="config_athkar")],
        [InlineKeyboardButton("تكوين ورد القرآن" if lang == "ar" else "Configure Quran Wird", callback_data="config_quran")],
        [InlineKeyboardButton("تعيين أدعية وقت النوم" if lang == "ar" else "Set Sleep-Time Supplications", callback_data="config_sleep")],
        [InlineKeyboardButton("تعيين المدينة/المنطقة الزمنية" if lang == "ar" else "Set City/Timezone", callback_data="config_city")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=message, reply_markup=reply_markup)
    return MAIN_MENU
