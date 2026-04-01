# Muthaker Bot - User Preferences System

Complete implementation of a two-sided Telegram bot for personalized Athkar reminders.

## What's New

### Three Components Working Together:

1. **Channel Bot** (`fazkerbot.py`) - Unchanged
   - Posts Quran pages + Athkar to your admin channel on schedule
   - Continues working as before

2. **User Preferences Bot** (`user_side.py`) - NEW ✨
   - Beautiful interactive interface for users
   - Users select Athkar reminders they want (9 options)
   - Users choose frequency (1x, 2x, 3x daily, or custom)
   - Stores preferences in PostgreSQL database
   - Supports Arabic and English

3. **User Reminders Scheduler** (`user_reminders.py`) - NEW ✨
   - Reads user preferences from database
   - Sends personalized Athkar reminders via DM
   - Respects each user's selected frequency
   - Randomly picks from user's selected Athkar each time

### Database Schema

A single table `user_preferences` stores:
- `telegram_id` (unique user ID)
- `selected_athkar` (JSON list of selected Athkar)
- `frequency` (how often to send: "1x_daily", "2x_daily", "3x_daily", "custom_N")
- `timezone` (Africa/Cairo by default)
- `language` (ar/en)
- Plus timestamps for tracking

## How It Works

### User Flow:

```
/start
  ↓
Choose Language (العربية / English)
  ↓
Select Athkar (can choose multiple with beautiful buttons)
  ✅ منبة الحرز
  ✅ الباقيات الصالحات
  ✅ الحوقلة
  ✅ التسبيح
  ✅ دعاء ذي النون
  ✅ التهليل
  ✅ الحمد
  ✅ الاستغفار
  ✅ الصلاة على النبي
  ↓
Select Frequency:
  • مرة واحدة يومياً (6:00 AM)
  • مرتان يومياً (6:00 AM + 7:00 PM)
  • ثلاث مرات يومياً (6:00 AM + 1:00 PM + 7:00 PM)
  • مخصص (enter number)
  ↓
Saved! User receives reminders at selected times
```

### Reminder Flow:

Every minute, the scheduler:
1. Gets all active users from database
2. Checks if anyone should receive a reminder at this time
3. For users due for a reminder:
   - Picks a random Athkar from their selection
   - Sends it to them via DM
   - Includes the full text and emoji

Example reminder:
```
🛡️ منبة الحرز

لا اله إلا اللّٰه وحده لا شريك له ، له الملك وله الحمد

🌙 ذكر الله في كل وقت 🌙
```

## Files Changed/Added

```
fazkerbot.py          → Unchanged (channel bot)
main.py               → Updated (runs all 3 components)
user_side.py          → NEW (user preferences interface)
user_reminders.py     → NEW (personalized reminder scheduler)
test_user_system.py   → NEW (test database connection)
```

## Environment Variables (Already Set on Heroku)

```
TELEGRAM_BOT_TOKEN     → Your bot token
TELEGRAM_CHAT_ID       → Your channel ID
DATABASE_URL           → Heroku PostgreSQL (auto-set)
PORT                   → 8080 (default)
```

## Running Locally

```bash
# Install dependencies
pip install python-telegram-bot sqlalchemy asyncpg aiohttp apscheduler

# Set environment variables
export TELEGRAM_BOT_TOKEN="your-token"
export TELEGRAM_CHAT_ID="your-chat-id"
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db"

# Run tests
python test_user_system.py

# Run bot
python main.py
```

## Heroku Webhook Setup

The bot uses webhook mode (not polling) for Telegram updates. After deployment:

```bash
# Set webhook URL with Telegram
# Replace YOUR_HEROKU_APP with your app name
curl -X POST https://api.telegram.org/botTOKEN/setWebhook \
  -d url=https://YOUR_HEROKU_APP.herokuapp.com/webhook
```

Or use the Telegram Bot API directly.

## Testing

Run the test script:
```bash
python test_user_system.py
```

This verifies:
- ✅ Database connection works
- ✅ Athkar options are defined (9 options)
- ✅ Frequency options are defined

## Features

✅ Beautiful Arabic UI with emojis
✅ Multi-select Athkar with "Select All"
✅ 3 predefined + custom frequency options
✅ Per-user personalization
✅ Smart scheduling (respects user's selected times)
✅ Bilingual (Arabic + English)
✅ Channel posts continue unchanged
✅ Zero impact on existing functionality

## Future Enhancements (Optional)

- Edit preferences after initial setup
- Analytics (show users stats)
- Integration with prayer times
- Audio/voice versions of Athkar
- Web dashboard for admins
