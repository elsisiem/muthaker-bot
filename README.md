# Muthaker Bot 🤖
**Personalized Islamic Reminders - Quran & Athkar**

A two-sided Telegram bot system running on Heroku that combines:
1. **Channel Bot** - Posts daily Quran pages + Athkar to a channel on schedule
2. **User Bot** - Interactive interface for users to configure their personal Athkar reminders

---

## Current Features

### 📡 Channel Bot (fazkerbot.py)
- **Automatic Daily Posts** to configured channel:
  - 🌅 Morning Athkar (after Fajr prayer)
  - 📖 Quran reading pages (2-3 pages daily on a continuous cycle)
  - 🌙 Evening Athkar (after Asr prayer)

- **Smart Scheduling**:
  - Fetches Cairo prayer times via Aladhan API
  - Calculates prayer times for each day
  - Schedules tasks based on actual prayer times (not fixed hours)
  - Fallback times if API fails
  - Tasks carry over to next day if missed

### 💬 User Bot (user_side.py)
Beautiful interactive interface where users can:

1. **Select Athkar** - Choose from 9 options with visual toggles:
   - 🛡️ Al-Hizb (The Shield)
   - ✨ Eternal Good Works
   - 🤲 Hawqalah
   - 📿 Tasbih (Glorification)
   - 🌙 Dua of Dhun-Nun
   - 📣 Tahlil (Declaration of Oneness)
   - 🙏 Tahmid (Praise)
   - 🔄 Istighfar (Repentance)
   - 💌 Salat on the Prophet

2. **Choose Frequency**:
   - 1x daily (9:00 AM)
   - 2x daily (9:00 AM, 6:00 PM)
   - 3x daily (9:00 AM, 1:00 PM, 6:00 PM)

3. **Manage Preferences**:
   - View current settings
   - Edit Athkar selections anytime
   - Change reminder frequency
   - All saved to database

### 🗄️ Database
- PostgreSQL on Heroku
- Stores user preferences persistently
- Tracks: telegram ID, selected Athkar, frequency, timezone, created/updated dates

---

## How to Use

### Users
1. Open the bot and send `/start`
2. Click "اختيار الأذكار" (Select Athkar)
3. Toggle desired Athkar with checkmarks
4. Click "تم" to proceed
5. Choose frequency preference
6. Done! Preferences saved to database

Users will receive their personalized reminders based on their selections.

### Admins
- **Edit Channel**: Set `TELEGRAM_CHAT_ID` in Heroku config
- **Edit Bot Token**: Update `TELEGRAM_BOT_TOKEN`
- **Database**: Automatically managed on Heroku Postgres
- **Logs**: View with `heroku logs -t -a muthaker-bot`

---

## Architecture

```
main.py (Entry Point)
├── Channel Bot (fazkerbot.py)
│   ├── Fetch prayer times (Aladhan API)
│   ├── Schedule daily tasks
│   ├── Send Quran pages + Athkar to channel
│   └── Heartbeat monitoring
│
├── User Bot (user_side.py)
│   ├── /start command
│   ├── Interactive menus (callbacks)
│   ├── Database operations
│   └── Webhook server
│
└── Web Server (aiohttp)
    └── Telegram webhook receiver
```

---

## Environment Variables (Heroku)

```bash
TELEGRAM_BOT_TOKEN=<your_bot_token>
TELEGRAM_CHAT_ID=<your_channel_id>
DATABASE_URL=<auto_set_by_heroku_postgres>
PORT=<auto_set_by_heroku>
```

---

## Logs & Monitoring

Clean, organized logs show:
- ✅ Initialization of each component
- 🔗 Telegram connection status
- 📍 Prayer times API calls
- 📅 Tasks scheduled (with times)
- 💓 Heartbeat every 5 minutes
- 💬 User interactions

Example:
```
📡 Starting channel posting bot...
✅ Channel bot task created
🌐 Starting web server for Telegram webhook...
📦 Initializing user preferences database...
✅ All components started successfully
```

---

## Recent Changes

✅ **Cleanup**:
- Removed all test files and unused directories
- Cleaned up requirements.txt
- Fixed imports and dependencies

✅ **Clean Logging**:
- Structured startup sequence
- Reduced noise from third-party libraries
- Clear status indicators with emojis

✅ **New User Interface**:
- Complete rewrite of user_side.py
- Beautiful Arabic/English UI
- Interactive Athkar selection with toggles
- Frequency options
- Preferences persisted to database

---

## Tech Stack

- **Python 3.11** - Core language
- **python-telegram-bot** - Telegram API
- **APScheduler** - Task scheduling
- **SQLAlchemy** - ORM for database
- **AsyncPG** - Async database driver
- **aiohttp** - Async web server
- **pytz** - Timezone handling
- **Heroku** - Hosting platform
- **PostgreSQL** - Database

---

## Next Steps (Optional)

- [ ] Implement personalized reminder sending to users
- [ ] Add timezone selection for users
- [ ] Create web dashboard for admin management
- [ ] Add custom time slot selection
- [ ] Multi-language support enhancements
- [ ] Admin notifications for new users

---

**Last Updated**: April 1, 2026
**Status**: Production ✅
