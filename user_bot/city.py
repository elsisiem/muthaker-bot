from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import text
import aiohttp
from user_side import async_session, get_user_language, CITY_INFO

async def city_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry for City/Timezone configuration: ask user for city and country."""
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    lang = await get_user_language(user_id)
    msg = "أرسل مدينتك وبلدك بالتنسيق التالي:\nمدينة، بلد\n(مثال: القاهرة، مصر)" if lang == "ar" else "Please send your city and country in the format:\nCity, Country\n(e.g., Cairo, Egypt)"
    await query.edit_message_text(msg)
    return CITY_INFO

async def city_config_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive city info, determine timezone using prayer API, and save to DB."""
    text = update.message.text.strip()
    if "," not in text:
        lang = await get_user_language(str(update.effective_user.id))
        error_msg = "تنسيق غير صحيح. يرجى استخدام: مدينة، بلد" if lang == "ar" else "Invalid format. Please use: City, Country"
        await update.message.reply_text(error_msg)
        return CITY_INFO
    city, country = [t.strip() for t in text.split(",", 1)]
    API_URL = "https://api.aladhan.com/v1/timingsByCity"
    params = {'city': city, 'country': country, 'method': 3}
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=params) as response:
            data = await response.json()
            timezone = data.get("data", {}).get("meta", {}).get("timezone", "Africa/Cairo")
    user_id = str(update.effective_user.id)
    async with async_session() as session:
        await session.execute(
            text("UPDATE users SET city = :city, country = :country, timezone = :tz WHERE telegram_id = :tid"),
            {"city": city, "country": country, "tz": timezone, "tid": user_id}
        )
        await session.commit()
    lang = await get_user_language(user_id)
    success_msg = f"تم حفظ التكوين. المنطقة الزمنية الخاصة بك مضبوطة على {timezone}." if lang == "ar" else f"Configuration saved. Your timezone is set to {timezone}."
    await update.message.reply_text(success_msg)
    return -1  # End conversation
