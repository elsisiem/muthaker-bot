import logging
from datetime import datetime, date
from typing import Optional

import aiohttp
import pytz

from config import ALADHAN_API_URL, DEFAULT_PRAYER_METHOD

logger = logging.getLogger(__name__)


async def fetch_prayer_times(city: str, country: str = "", method: int = DEFAULT_PRAYER_METHOD, dt: Optional[date] = None) -> Optional[dict]:
    if dt is None:
        dt = date.today()

    params = {
        "city": city,
        "country": country,
        "method": method,
        "date": dt.strftime("%d-%m-%Y"),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ALADHAN_API_URL, params=params, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Prayer API returned {resp.status} for city={city}")
                    return None
                data = await resp.json()
                if data.get("code") != 200:
                    logger.warning(f"Prayer API error: {data.get('data')} for city={city}")
                    return None
                return data["data"]["timings"]
    except Exception as e:
        logger.error(f"Failed to fetch prayer times for {city}: {e}")
        return None


async def get_user_prayer_times(city: str, country: str, method: int, user_timezone_str: str) -> Optional[dict]:
    timings = await fetch_prayer_times(city, country, method)
    if not timings:
        return None

    try:
        user_tz = pytz.timezone(user_timezone_str)
    except Exception:
        user_tz = pytz.UTC

    result = {}
    today = date.today()
    for prayer_name in ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]:
        time_str = timings.get(prayer_name)
        if time_str:
            time_str = time_str.split(" ")[0]
            try:
                hour, minute = map(int, time_str.split(":"))
                prayer_dt = datetime(today.year, today.month, today.day, hour, minute)
                prayer_dt = pytz.timezone("UTC").localize(prayer_dt)
                result[prayer_name] = prayer_dt.astimezone(user_tz)
            except (ValueError, AttributeError):
                pass

    return result if len(result) == 5 else None