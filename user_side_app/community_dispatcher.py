"""Delivery engine for linked groups and channels.

Each target keeps its own city, timezone, enabled posts and delivery history.  A
single minute-level job therefore serves any number of communities without
mixing their schedules or sending a post twice after a restart.
"""

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
import pytz

from .db import (
    get_user_prefs,
    list_active_community_posts,
    list_schedulable_targets,
    mark_community_post_sent,
    update_target_settings,
)
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
_geocode_cache: dict[str, tuple[float, float] | None] = {}
PERSONAL_ATHKAR_TEXT = {
    "hizb": "حسبي الله لا إله إلا هو، عليه توكلت وهو رب العرش العظيم.",
    "hamd": "الحمد لله رب العالمين.",
    "hawqala": "لا حول ولا قوة إلا بالله.",
    "tahlil": "لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير.",
    "baaqiyat": "سبحان الله، والحمد لله، ولا إله إلا الله، والله أكبر.",
    "istighfar": "أستغفر الله العظيم وأتوب إليه.",
    "salat": "اللهم صل وسلم وبارك على محمد.",
    "tasbih": "سبحان الله وبحمده، سبحان الله العظيم.",
    "yunus": "لا إله إلا أنت سبحانك إني كنت من الظالمين.",
}


def _timezone(timezone_name: str | None):
    try:
        return pytz.timezone(timezone_name or "Africa/Cairo")
    except pytz.UnknownTimeZoneError:
        return pytz.timezone("Africa/Cairo")


async def geocode_city(city: str) -> tuple[float, float] | None:
    """Coordinate lookup for legacy targets created before coordinates were stored."""
    key = city.casefold()
    if key in _geocode_cache:
        return _geocode_cache[key]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "jsonv2", "limit": 1},
                headers={"User-Agent": "muthaker-bot/1.0"},
                timeout=15,
            ) as response:
                data = await response.json() if response.status == 200 else []
                result = (float(data[0]["lat"]), float(data[0]["lon"])) if data else None
                _geocode_cache[key] = result
                return result
    except Exception:
        logger.exception("Could not geocode community city %s", city)
        return None


async def fetch_prayer_times(
    city: str,
    target_date,
    method: int = 3,
    latitude: float | str | None = None,
    longitude: float | str | None = None,
) -> dict | None:
    """Fetch a day's timings from coordinates, falling back to a city lookup."""
    try:
        coordinates = (float(latitude), float(longitude)) if latitude is not None and longitude is not None else await geocode_city(city)
    except (TypeError, ValueError):
        coordinates = await geocode_city(city)
    location_key = f"{coordinates[0]:.5f},{coordinates[1]:.5f}" if coordinates else city.casefold()
    key = (location_key, target_date.isoformat(), method)
    if key in _timings_cache:
        return _timings_cache[key]

    url = f"https://api.aladhan.com/v1/timings/{target_date.strftime('%d-%m-%Y')}"
    params = {"method": method}
    if coordinates:
        params.update({"latitude": coordinates[0], "longitude": coordinates[1]})
    else:
        params["city"] = city
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as response:
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

    target_index = {(target.owner_telegram_id, target.chat_id): target for target in targets}
    for post in await list_active_community_posts():
        target = target_index.get((post.owner_telegram_id, post.target_chat_id))
        if not target:
            continue
        now = datetime.now(_timezone(target.timezone))
        timings = await fetch_prayer_times(target.city, now.date(), target.prayer_method or 3)
        await _dispatch_custom_post(post, target, now, timings)


async def _send_custom_post(post, target) -> bool:
    application = get_application()
    if not application:
        return False
    try:
        if post.content_type == "photo" and post.photo_file_id:
            await application.bot.send_photo(chat_id=int(target.chat_id), photo=post.photo_file_id, caption=post.caption or None)
        elif post.content_type == "personal_athkar":
            prefs = await get_user_prefs(post.owner_telegram_id)
            selected = json.loads(prefs.selected_athkar or "[]") if prefs else []
            content = [PERSONAL_ATHKAR_TEXT[item] for item in selected if item in PERSONAL_ATHKAR_TEXT]
            if not content:
                logger.warning("Custom personal-athkar post %s has no selected athkar", post.id)
                return False
            await application.bot.send_message(chat_id=int(target.chat_id), text="\n\n".join(content if prefs.delivery_mode == "batch" else content[:1]))
        elif post.text_content:
            await application.bot.send_message(chat_id=int(target.chat_id), text=post.text_content)
        else:
            return False
        return True
    except Exception:
        logger.exception("Could not send custom community post %s", post.id)
        return False


async def _dispatch_custom_post(post, target, now, timings) -> None:
    due = False
    sent_key = None
    if post.schedule_type == "interval" and post.interval_minutes:
        current_utc = datetime.utcnow()
        due = post.last_sent_at is None or current_utc >= post.last_sent_at + timedelta(minutes=post.interval_minutes)
        if due and await _send_custom_post(post, target):
            await mark_community_post_sent(post.id, sent_at=current_utc)
        return
    if post.schedule_type == "clock" and post.time_of_day:
        try:
            hour, minute = map(int, post.time_of_day.split(":"))
            run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            sent_key = f"{now.date().isoformat()}:{post.time_of_day}"
            due = post.last_sent_key != sent_key and run_at <= now < run_at + timedelta(minutes=3)
        except ValueError:
            logger.warning("Invalid clock time for custom post %s", post.id)
    elif post.schedule_type == "prayer" and post.prayer_name and timings:
        run_at = prayer_datetime(now.date(), post.prayer_name, timings, target.timezone)
        sent_key = f"{now.date().isoformat()}:{post.prayer_name}:{post.prayer_offset_minutes or 0}"
        due = bool(run_at and post.last_sent_key != sent_key and run_at + timedelta(minutes=post.prayer_offset_minutes or 0) <= now < run_at + timedelta(minutes=(post.prayer_offset_minutes or 0) + 3))
    if due and await _send_custom_post(post, target):
        await mark_community_post_sent(post.id, sent_key=sent_key, sent_at=datetime.utcnow())
