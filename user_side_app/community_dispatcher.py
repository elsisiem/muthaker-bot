"""Delivery engine for linked groups and channels.

Each target keeps its own city, timezone, enabled posts and delivery history.  A
single minute-level job therefore serves any number of communities without
mixing their schedules or sending a post twice after a restart.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import pytz

from .db import list_schedulable_targets, update_target_settings
from .scheduler import get_application

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent
ASSET_PATHS = {
    "morning": ROOT_DIR / "الأذكار" / "أذكار_الصباح.jpg",
    "night": ROOT_DIR / "الأذكار" / "أذكار_المساء.jpg",
    "monday": ROOT_DIR / "الصيام" / "صيام الإثنين.jpg",
    "thursday": ROOT_DIR / "الصيام" / "صيام الخميس.jpg",
}
FALLBACK_TEXT = {
    "morning": "🌅 أذكار الصباح",
    "night": "🌙 أذكار المساء",
    "monday": "🍃 تذكير بصيام يوم الإثنين",
    "thursday": "🍃 تذكير بصيام يوم الخميس",
}
_timings_cache: dict[tuple[str, str, int], dict | None] = {}


def _timezone(timezone_name: str | None):
    try:
        return pytz.timezone(timezone_name or "Africa/Cairo")
    except pytz.UnknownTimeZoneError:
        return pytz.timezone("Africa/Cairo")


async def fetch_prayer_times(city: str, target_date, method: int = 3) -> dict | None:
    """Fetch one day's timings and cache them for this running process."""
    key = (city.casefold(), target_date.isoformat(), method)
    if key in _timings_cache:
        return _timings_cache[key]

    url = f"https://api.aladhan.com/v1/timings/{target_date.strftime('%d-%m-%Y')}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"city": city, "method": method}, timeout=15) as response:
                if response.status != 200:
                    logger.warning("Prayer API returned %s for %s", response.status, city)
                    _timings_cache[key] = None
                    return None
                data = await response.json()
                timings = data.get("data", {}).get("timings")
                _timings_cache[key] = timings
                return timings
    except Exception:
        logger.exception("Prayer API request failed for %s", city)
        return None


def prayer_datetime(day, prayer_name: str, timings: dict, timezone_name: str):
    raw = timings.get(prayer_name)
    if not raw:
        return None
    try:
        hour, minute = map(int, raw.split(" ", 1)[0].split(":"))
    except (TypeError, ValueError):
        return None
    return _timezone(timezone_name).localize(datetime.combine(day, datetime.min.time().replace(hour=hour, minute=minute)))


async def _send_target_post(target, kind: str) -> bool:
    application = get_application()
    if not application:
        logger.warning("Community dispatcher skipped: Telegram application is not ready")
        return False
    try:
        image_path = ASSET_PATHS[kind]
        if image_path.exists():
            with image_path.open("rb") as image:
                await application.bot.send_photo(chat_id=int(target.chat_id), photo=image)
        else:
            await application.bot.send_message(chat_id=int(target.chat_id), text=FALLBACK_TEXT[kind])
        return True
    except Exception:
        logger.exception("Could not send %s post to target %s", kind, target.chat_id)
        return False


async def _dispatch_if_due(target, *, kind: str, run_at, history_field: str, history_date: str, now) -> None:
    if getattr(target, history_field) == history_date:
        return
    # A short window absorbs scheduler drift/restarts.  The saved history makes
    # this idempotent even when more than one tick lands in the window.
    if not (run_at <= now < run_at + timedelta(minutes=3)):
        return
    if await _send_target_post(target, kind):
        await update_target_settings(target.owner_telegram_id, target.chat_id, **{history_field: history_date})
        setattr(target, history_field, history_date)
        logger.info("Posted %s to linked target %s", kind, target.chat_id)


async def dispatch_community_posts():
    """Post enabled morning/evening athkar and fasting reminders when due."""
    targets = await list_schedulable_targets()
    for target in targets:
        tz = _timezone(target.timezone)
        now = datetime.now(tz)
        timings = await fetch_prayer_times(target.city, now.date(), target.prayer_method or 3)
        if not timings:
            continue

        fajr = prayer_datetime(now.date(), "Fajr", timings, target.timezone)
        asr = prayer_datetime(now.date(), "Asr", timings, target.timezone)
        isha = prayer_datetime(now.date(), "Isha", timings, target.timezone)
        date_key = now.date().isoformat()

        if fajr and target.morning_athkar_enabled:
            await _dispatch_if_due(target, kind="morning", run_at=fajr + timedelta(minutes=30), history_field="last_morning_sent_date", history_date=date_key, now=now)
        if asr and target.night_athkar_enabled:
            await _dispatch_if_due(target, kind="night", run_at=asr + timedelta(minutes=30), history_field="last_night_sent_date", history_date=date_key, now=now)
        if isha and now.weekday() == 6 and target.monday_fasting_enabled:
            await _dispatch_if_due(target, kind="monday", run_at=isha + timedelta(minutes=30), history_field="last_monday_sent_date", history_date=date_key, now=now)
        if isha and now.weekday() == 2 and target.thursday_fasting_enabled:
            await _dispatch_if_due(target, kind="thursday", run_at=isha + timedelta(minutes=30), history_field="last_thursday_sent_date", history_date=date_key, now=now)
