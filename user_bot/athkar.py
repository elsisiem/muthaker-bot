from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import text
import json
from db import async_session, get_user_language, ATHKAR, ATHKAR_FREQ
import logging

logger = logging.getLogger(__name__)

# Predefined Athkar list
ATHKAR_LIST_AR = [
    "تهليل (La ilaha illa Allah)",
    "تسبيح (SubhanAllah)",
    "تحميد (Alhamdulillah)",
    "تكبير (Allahu Akbar)",
    "حوقلة (La hawla wa la quwwata illa billah)",
    "الصلاة على النبي (Salawat)",
    "دعاء ذي النون (La ilaha illa anta subhanaka inni kuntu min al-zalimin)",
    "سبحان الله وبحمده، سبحان الله العظيم",
]

ATHKAR_LIST_EN = [
    "Tahleel (La ilaha illa Allah)",
    "Tasbeeh (SubhanAllah)",
    "Tahmeed (Alhamdulillah)",
    "Takbeer (Allahu Akbar)",
    "Hawqala (La hawla wa la quwwata illa billah)",
    "Salawat (Prayers upon the Prophet)",
    "Dua of Dhun-Noon (La ilaha illa anta subhanaka inni kuntu min al-zalimin)",
    "Subhan Allah wa bihamdihi, subhan Allah al-adheem",
]

async def athkar_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for Athkar configuration."""
    query = update.callback_query
    try:
        await query.answer()
        user_id = str(update.effective_user.id)
        lang = await get_user_language(user_id)
        athkar_list = ATHKAR_LIST_AR if lang == "ar" else ATHKAR_LIST_EN
        context.user_data["athkar_list"] = athkar_list
        if lang == "ar":
            text = "اختر الأذكار التي تريد التذكير بها:\n" + "\n".join(f"{i+1}: {item}" for i, item in enumerate(athkar_list))
            text += "\n\nيرجى الرد بأرقام الاختيارات مفصولة بفواصل (مثال: 1,3,5)."
        else:
            text = "Select the Athkar you want reminders for:\n" + "\n".join(f"{i+1}: {item}" for i, item in enumerate(athkar_list))
            text += "\n\nPlease reply with the numbers of the selections separated by commas (e.g. 1,3,5)."
        await query.edit_message_text(text=text)
        return ATHKAR
    except Exception as e:
        logger.exception("Error in athkar_config_entry")
        await query.edit_message_text("An error occurred. Please try again.")

async def athkar_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive user's Athkar selections."""
    try:
        athkar_list = context.user_data.get("athkar_list", ATHKAR_LIST_AR)
        selections = update.message.text.split(",")
        indices = [int(s.strip()) for s in selections if s.strip().isdigit() and 1 <= int(s.strip()) <= len(athkar_list)]
        chosen = [athkar_list[i-1] for i in indices]
        context.user_data["athkar"] = chosen
        lang = await get_user_language(str(update.effective_user.id))
        if lang == "ar":
            keyboard = [
                [InlineKeyboardButton("عدد ثابت يوميًا", callback_data="freq_fixed")],
                [InlineKeyboardButton("فترة زمنية (مثل كل ساعتين)", callback_data="freq_interval")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("اختر وضع التكرار لتذكيرات الأذكار:", reply_markup=reply_markup)
        else:
            keyboard = [
                [InlineKeyboardButton("Fixed Number per Day", callback_data="freq_fixed")],
                [InlineKeyboardButton("Time Interval (e.g. every 2 hours)", callback_data="freq_interval")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Choose the frequency mode for Athkar reminders:", reply_markup=reply_markup)
        return ATHKAR_FREQ
    except Exception as e:
        logger.exception("Error in athkar_receive")
        await update.message.reply_text("Invalid input. Please try again.")

async def athkar_freq_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process frequency choice for Athkar reminders."""
    query = update.callback_query
    try:
        await query.answer()
        mode = query.data  # "freq_fixed" or "freq_interval"
        context.user_data["athkar_freq_mode"] = mode
        lang = await get_user_language(str(update.effective_user.id))
        if mode == "freq_fixed":
            msg = "أدخل العدد الثابت من التذكيرات يوميًا (مثال: 10):" if lang == "ar" else "Enter the fixed number of reminders per day (e.g., 10):"
        else:
            msg = "أدخل الفترة الزمنية بالدقائق (مثال: 30 لكل 30 دقيقة):" if lang == "ar" else "Enter the time interval in minutes (e.g., 30 for every 30 minutes):"
        await query.edit_message_text(msg)
        return ATHKAR_FREQ
    except Exception as e:
        logger.exception("Error in athkar_freq_choice")
        await query.edit_message_text("An error occurred. Please try again.")

async def athkar_freq_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the frequency value for Athkar reminders."""
    try:
        value = int(update.message.text.strip())
        context.user_data["athkar_freq_value"] = value
        athkar_prefs = {
            "selected": context.user_data.get("athkar", []),
            "mode": context.user_data.get("athkar_freq_mode"),
            "value": value
        }
        user_id = str(update.effective_user.id)
        async with async_session() as session:
            await session.execute(
                text("UPDATE users SET athkar_preferences = :prefs WHERE telegram_id = :tid"),
                {"prefs": json.dumps(athkar_prefs), "tid": user_id}
            )
            await session.commit()
        lang = await get_user_language(user_id)
        success_msg = "تم حفظ تفضيلات الأذكار بنجاح." if lang == "ar" else "Athkar preferences saved successfully."
        await update.message.reply_text(success_msg)
        return -1  # End conversation
    except Exception as e:
        logger.exception("Error in athkar_freq_receive")
        await update.message.reply_text("Invalid input. Please enter a valid number.")