<h1 align="center">Muthaker (مُذكّر)</h1>
<p align="center">Telegram athkar reminders for individuals, groups, and channels.</p>
<p align="center">
  <a href="#how-it-works">How it works</a> ·
  <a href="#run-locally">Run locally</a> ·
  <a href="#deploy">Deploy</a>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-111318?style=flat-square" alt="MIT license">
  <img src="https://img.shields.io/badge/Python-3.11-111318?style=flat-square&logo=python&logoColor=white" alt="Python 3.11">
</p>

## Personal reminders

- Choose individual athkar and receive them on an interval, or spread a daily goal across awake hours.
- Select a quiet-hours preset (normal, early sleeper, night owl, or none). Reminders pause during that window.
- Set a timezone by sharing a Telegram location or typing a city. The bot stores only the detected timezone; coordinates are never persisted and the location message is deleted when Telegram permits it.
- Enable morning and evening athkar images, scheduled from Fajr and Asr. The city is requested separately for prayer-time calculation; the default is 30 minutes after each prayer and can be edited later.
- Arabic, English, Spanish, French, and Turkish interface selection is available from every main menu.

Commands: `/start`, `/view`, `/edit`, `/reset`, `/help`, `/groups`, `/link`.

## Groups and channels

- Add the bot as an administrator, then send `/link` inside the group or channel to connect it to your setup in the personal bot.
- A linked group or channel gets morning athkar 30 minutes after Fajr, evening athkar 30 minutes after Asr, and Monday and Thursday fasting reminders 30 minutes after Isha the evening before. Times use the target's own city and timezone.
- A separate channel publisher posts to the chat set in `TELEGRAM_CHAT_ID`: the morning and evening athkar images and the fasting reminders, on a Cairo prayer-time schedule. Quran page posting is paused.

## Languages

Arabic, English, Spanish, French, and Turkish. The interface language is chosen per user and can be changed from any main menu. Channel images are in Arabic.

## How it works

`main.py` runs three things in one asyncio process:

1. **Channel publisher** (`fazkerbot.py`). An APScheduler instance in Cairo time. It fetches the day's prayer times from the Aladhan API, falls back to fixed times if the API fails, and schedules the athkar and fasting posts for the channel.
2. **Personal bot** (`user_side_app/`). python-telegram-bot with long polling, and PostgreSQL through async SQLAlchemy for user settings and linked targets. At startup it builds one APScheduler job set per active user. A cron job at 00:05 rebuilds the one-off prayer jobs every day.
3. **Health server**. An aiohttp app on `$PORT` (default 8080) that answers `GET /` with a status line.

Delivery to linked groups and channels runs from a dispatcher job (`user_side_app/community_dispatcher.py`) every minute. A post is due inside a three-minute window after its target time. The dispatcher records what it sent (a last-sent date per post type, and a `last_sent_key` for custom posts), so overlapping ticks and restarts do not double-post.

External services:

- **Aladhan** for prayer times.
- **OpenStreetMap Nominatim** to turn a city name into coordinates, and to label a shared location with a city.
- **timezonefinder** to map shared coordinates to a timezone, with Open-Meteo and then Aladhan as fallbacks.

## Run locally

Requirements: Python 3.11, a PostgreSQL database, and a bot token from [@BotFather](https://t.me/BotFather).

```sh
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt "SQLAlchemy[asyncio]<2.1"
cp .env.example .env             # then fill in the values
set -a; source .env; set +a      # export the variables into your shell
python main.py
```

`main.py` reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` before any `.env` file would be loaded, so export the variables in your shell as shown. The `"SQLAlchemy[asyncio]<2.1"` pin is needed because `requirements.txt` does not cap SQLAlchemy and 2.1 switches the default `postgresql://` driver to psycopg, which is not listed there.

| Variable | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Channel or chat that the channel publisher posts to |
| `DATABASE_URL` | Yes | PostgreSQL URL. A `postgres://` URL, as Heroku sets it, is rewritten for asyncpg |
| `PORT` | No | Port for the health server. Defaults to 8080 |

## Deploy

The app runs on Heroku as a single `web` dyno. The `Procfile` is `web: python main.py` and `.python-version` pins Python 3.11.

```sh
heroku addons:create heroku-postgresql          # sets DATABASE_URL
heroku config:set TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
git push heroku master
heroku logs --tail
```

Run one instance only. The personal bot uses long polling, so a second instance would compete for the same updates.

Images for channel posts are loaded from `raw.githubusercontent.com/elsisiem/muthaker-bot/master/`. Keep the repository name and the `master` branch as they are, or update the URLs in `fazkerbot.py` and `config.py`.

## Project layout

```text
main.py              Entry point: starts the three services
fazkerbot.py         Channel publisher (prayer-time athkar images, fasting reminders)
user_side_app/       Personal bot and community dispatcher
  app.py             Telegram application, command and callback registration, health route
  handlers.py        Menus and setup flows
  db.py              SQLAlchemy models and queries
  scheduler.py       APScheduler jobs for reminders and daily rebuild
  community_dispatcher.py   One-minute loop for linked groups and channels
  i18n.py, keyboards.py     Five-language strings and inline keyboards
الأذكار/ الصيام/ المصحف/     Images served to channels from GitHub
services/, database/, config.py   Loaded at startup through services.timezone_service
bot.py, handlers/, keyboards.py, i18n/   Separate modular bot, not started by main.py
user_side.py, archive/       Compatibility shim and retired scripts
```

`bot.py` with `handlers/`, the root `keyboards.py` and `i18n/` form a second implementation that `main.py` does not import. `user_side_app/handlers.py` imports `services.timezone_service`, which loads the `services/` and `database/` packages and `config.py` at startup, so those stay in place.

## License

MIT. See [LICENSE](LICENSE).
