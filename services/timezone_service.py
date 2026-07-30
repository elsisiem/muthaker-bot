import logging
from typing import Optional, Tuple

import pytz
from timezonefinder import TimezoneFinder

logger = logging.getLogger(__name__)
_tf = TimezoneFinder()

COMMON_TIMEZONE_OFFSETS = {
    "Africa/Cairo": "UTC+2/+3",
    "Asia/Riyadh": "UTC+3",
    "Asia/Dubai": "UTC+4",
    "Asia/Karachi": "UTC+5",
    "Asia/Dhaka": "UTC+6",
    "Asia/Jakarta": "UTC+7",
    "Asia/Kuala_Lumpur": "UTC+8",
    "Europe/London": "UTC+0/+1",
    "Europe/Paris": "UTC+1/+2",
    "Europe/Moscow": "UTC+3",
    "America/New_York": "UTC-5/-4",
    "America/Chicago": "UTC-6/-5",
    "America/Denver": "UTC-7/-6",
    "America/Los_Angeles": "UTC-8/-7",
    "UTC": "UTC+0",
}


def detect_timezone_from_location(latitude: float, longitude: float) -> Optional[str]:
    try:
        tz_name = _tf.timezone_at(lat=latitude, lng=longitude)
        if tz_name:
            pytz.timezone(tz_name)
            return tz_name
    except Exception as e:
        logger.warning(f"Timezone detection failed for ({latitude}, {longitude}): {e}")
    return None


def resolve_timezone(text: str) -> Optional[str]:
    text = text.strip()

    for tz_name in COMMON_TIMEZONE_OFFSETS:
        if text.lower() == tz_name.lower():
            return tz_name

    for tz_name in pytz.all_timezones:
        if text.lower() == tz_name.lower():
            return tz_name

    city_map = {
        "cairo": "Africa/Cairo", "القاهرة": "Africa/Cairo",
        "alexandria": "Africa/Cairo", "الإسكندرية": "Africa/Cairo",
        "riyadh": "Asia/Riyadh", "الرياض": "Asia/Riyadh",
        "jeddah": "Asia/Riyadh", "جدة": "Asia/Riyadh",
        "mecca": "Asia/Riyadh", "مكة": "Asia/Riyadh", "makkah": "Asia/Riyadh",
        "medina": "Asia/Riyadh", "المدينة": "Asia/Riyadh",
        "dubai": "Asia/Dubai", "دبي": "Asia/Dubai",
        "abu dhabi": "Asia/Dubai", "أبوظبي": "Asia/Dubai",
        "doha": "Asia/Qatar",
        "kuwait": "Asia/Kuwait", "الكويت": "Asia/Kuwait",
        "manama": "Asia/Bahrain",
        "muscat": "Asia/Muscat", "مسقط": "Asia/Muscat",
        "amman": "Asia/Amman", "عمان": "Asia/Amman",
        "beirut": "Asia/Beirut", "بيروت": "Asia/Beirut",
        "damascus": "Asia/Damascus", "دمشق": "Asia/Damascus",
        "baghdad": "Asia/Baghdad", "بغداد": "Asia/Baghdad",
        "istanbul": "Europe/Istanbul", "إسطنبول": "Europe/Istanbul",
        "ankara": "Europe/Istanbul",
        "london": "Europe/London", "لندن": "Europe/London",
        "paris": "Europe/Paris", "باريس": "Europe/Paris",
        "berlin": "Europe/Berlin",
        "new york": "America/New_York", "نيويورك": "America/New_York",
        "los angeles": "America/Los_Angeles",
        "chicago": "America/Chicago",
        "toronto": "America/Toronto",
        "kuala lumpur": "Asia/Kuala_Lumpur", "كوالالمبور": "Asia/Kuala_Lumpur",
        "jakarta": "Asia/Jakarta", "جاكرتا": "Asia/Jakarta",
        "karachi": "Asia/Karachi", "كراتشي": "Asia/Karachi",
        "dhaka": "Asia/Dhaka", "دكا": "Asia/Dhaka",
        "moscow": "Europe/Moscow", "موسكو": "Europe/Moscow",
    }
    text_lower = text.lower()
    if text_lower in city_map:
        return city_map[text_lower]

    for tz_name in pytz.all_timezones:
        if text_lower in tz_name.lower():
            return tz_name

    return None


def get_timezone_choices():
    return [
        ("Africa/Cairo", "القاهرة / Cairo (UTC+2/+3)"),
        ("Asia/Riyadh", "الرياض / Riyadh (UTC+3)"),
        ("Asia/Dubai", "دبي / Dubai (UTC+4)"),
        ("Asia/Karachi", "كراتشي / Karachi (UTC+5)"),
        ("Asia/Dhaka", "دكا / Dhaka (UTC+6)"),
        ("Asia/Kuala_Lumpur", "كوالالمبور / KL (UTC+8)"),
        ("Europe/London", "لندن / London (UTC+0/+1)"),
        ("Europe/Paris", "باريس / Paris (UTC+1/+2)"),
        ("Europe/Moscow", "موسكو / Moscow (UTC+3)"),
        ("America/New_York", "نيويورك / New York (UTC-5/-4)"),
        ("America/Chicago", "شيكاغو / Chicago (UTC-6/-5)"),
        ("America/Los_Angeles", "لوس أنجلوس / LA (UTC-8/-7)"),
    ]


def validate_timezone(tz_name: str) -> bool:
    try:
        pytz.timezone(tz_name)
        return True
    except Exception:
        return False