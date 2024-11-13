import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters
import requests

# Constants for API
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
GITHUB_RAW_URL = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
QURAN_PAGES_URL = f"{GITHUB_RAW_URL}/%D8%A7%D9%84%D9%85%D8%B5%D8%AD%D9%81"
PRAYER_API = "https://api.aladhan.com/v1/timingsByCity"

# Define conversation states
LANGUAGE, LOCATION, CONFIGURE_WIRD, CHOOSE_QURAN_AMOUNT, CHOOSE_FORMAT, CHOOSE_FREQUENCY, CHOOSE_TIME, SPECIFY_PAGE = range(8)

# Pre-defined options
LANGUAGE_OPTIONS = [['Arabic', 'English', 'French', 'Russian']]
WIRD_OPTIONS = [['Ajzaa', 'Ahzab', 'Pages']]
FORMAT_OPTIONS = [['Written', 'Audio', 'Both']]
FREQUENCY_OPTIONS = [['Daily', '3 times a week', 'Weekly']]
TIME_OPTIONS = [['After Fajr', 'After Dhuhr', 'After Asr', 'After Maghrib', 'After Isha']]

async def start(update: Update, context):
    """Start the bot and prompt user to choose a language."""
    reply_markup = ReplyKeyboardMarkup(LANGUAGE_OPTIONS, one_time_keyboard=True)
    await update.message.reply_text(
        "Welcome! Please choose your preferred language:", reply_markup=reply_markup)
    return LANGUAGE

async def choose_language(update: Update, context):
    """Handle language selection and move to location prompt."""
    user_choice = update.message.text
    context.user_data['language'] = user_choice
    await update.message.reply_text(f"Great! You've selected {user_choice}. Now, please enter your country and city separated by a comma (e.g., Egypt, Cairo):")
    return LOCATION

async def set_location(update: Update, context):
    """Save location details and move to Wird configuration."""
    location = update.message.text
    country, city = location.split(",")
    context.user_data['country'] = country.strip()
    context.user_data['city'] = city.strip()
    
    await update.message.reply_text(f"Got it! You are in {country}, {city}. Now let's configure your daily Wird.")
    # Prompt for the type of Quran reading (ajzaa, ahzab, pages)
    reply_markup = ReplyKeyboardMarkup(WIRD_OPTIONS, one_time_keyboard=True)
    await update.message.reply_text("How would you like to receive your Wird? Choose one:", reply_markup=reply_markup)
    return CONFIGURE_WIRD

async def configure_wird(update: Update, context):
    """Set Wird configuration: type (ajzaa, ahzab, etc.)"""
    wird_type = update.message.text
    context.user_data['wird_type'] = wird_type
    
    await update.message.reply_text(f"How many {wird_type.lower()} per day would you like to receive?")
    return CHOOSE_QURAN_AMOUNT

async def choose_quran_amount(update: Update, context):
    """User specifies the amount of Quran to send daily."""
    amount = update.message.text
    context.user_data['amount'] = amount
    
    # Prompt for format (written, audio, both)
    reply_markup = ReplyKeyboardMarkup(FORMAT_OPTIONS, one_time_keyboard=True)
    await update.message.reply_text(f"How would you like to receive the Quran? Choose one:", reply_markup=reply_markup)
    return CHOOSE_FORMAT

async def choose_format(update: Update, context):
    """User specifies the format (written, audio, both)."""
    format_choice = update.message.text
    context.user_data['format'] = format_choice
    
    # Prompt for frequency (daily, 3 times a week, weekly)
    reply_markup = ReplyKeyboardMarkup(FREQUENCY_OPTIONS, one_time_keyboard=True)
    await update.message.reply_text("How often would you like to receive the Quran?", reply_markup=reply_markup)
    return CHOOSE_FREQUENCY

async def choose_frequency(update: Update, context):
    """User specifies how often they want the Quran."""
    frequency = update.message.text
    context.user_data['frequency'] = frequency

    # Prompt for the time of day based on prayer times
    reply_markup = ReplyKeyboardMarkup(TIME_OPTIONS, one_time_keyboard=True)
    await update.message.reply_text("When would you like the Quran to be sent to you? Choose a time of day:", reply_markup=reply_markup)
    return CHOOSE_TIME

async def choose_time(update: Update, context):
    """User specifies the time of day to receive the Quran."""
    time_of_day = update.message.text
    context.user_data['time_of_day'] = time_of_day

    # Prompt the user to start from a specific Quran page or from the beginning
    await update.message.reply_text("Would you like to start from a specific page, or start from the beginning (page 1)? Type 'specific' or 'beginning'.")
    return SPECIFY_PAGE

async def specify_page(update: Update, context):
    """User specifies the starting page for the Quran reading."""
    choice = update.message.text.lower()
    
    if choice == 'specific':
        await update.message.reply_text("Please enter the page number you'd like to start from:")
        return SPECIFY_PAGE
    else:
        # Default starting from page 1
        context.user_data['start_page'] = 1
        await update.message.reply_text("You will start from page 1.")
        await complete_setup(update, context)
        return ConversationHandler.END

async def set_starting_page(update: Update, context):
    """User specifies a specific page to start from."""
    page_number = int(update.message.text)
    context.user_data['start_page'] = page_number
    
    await update.message.reply_text(f"You'll start receiving Quran from page {page_number}.")
    await complete_setup(update, context)
    return ConversationHandler.END

async def complete_setup(update: Update, context):
    """Complete the setup and display the user’s selections."""
    language = context.user_data.get('language')
    country = context.user_data.get('country')
    city = context.user_data.get('city')
    wird_type = context.user_data.get('wird_type')
    amount = context.user_data.get('amount')
    format_choice = context.user_data.get('format')
    frequency = context.user_data.get('frequency')
    time_of_day = context.user_data.get('time_of_day')
    start_page = context.user_data.get('start_page')

    summary = (f"Setup Complete!\n"
               f"Language: {language}\n"
               f"Location: {country}, {city}\n"
               f"Wird Type: {wird_type}\n"
               f"Amount per day: {amount}\n"
               f"Format: {format_choice}\n"
               f"Frequency: {frequency}\n"
               f"Time of day: {time_of_day}\n"
               f"Start page: {start_page}\n")

    await update.message.reply_text(summary)

    # TODO: Store this data in a database and set up scheduling logic based on the user's preferences.
    # At this point, the bot will be ready to fetch the correct Quran pages and send them based on prayer times.

async def error_handler(update: Update, context):
    """Log errors caused by updates."""
    print(f"Update {update} caused error {context.error}")

def main():
    """Run the bot."""
    application = Application.builder().token(TOKEN).build()

    # Define the conversation flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_language)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_location)],
            CONFIGURE_WIRD: [MessageHandler(filters.TEXT & ~filters.COMMAND, configure_wird)],
            CHOOSE_QURAN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_quran_amount)],
            CHOOSE_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_format)],
            CHOOSE_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_frequency)],
            CHOOSE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_time)],
            SPECIFY_PAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, specify_page),
                           MessageHandler(filters.TEXT & ~filters.COMMAND, set_starting_page)]
        },
        fallbacks=[CommandHandler('cancel', lambda update, context: ConversationHandler.END)],
    )

    # Add the conversation handler to the application
    application.add_handler(conv_handler)

    # Log errors
    application.add_error_handler(error_handler)

    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
