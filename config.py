import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///muthaker.db")
PORT = int(os.environ.get("PORT", 8080))
HEROKU_APP_NAME = os.environ.get("HEROKU_APP_NAME", "")
WEBHOOK_MODE = os.environ.get("WEBHOOK_MODE", "false").lower() == "true"

DEFAULT_LANGUAGE = "en"
DEFAULT_TIMEZONE = "UTC"
DEFAULT_PRAYER_METHOD = 4
DEFAULT_MORNING_OFFSET = 30
DEFAULT_NIGHT_OFFSET = 30
DEFAULT_SLEEP_START_HOUR = 23
DEFAULT_SLEEP_START_MINUTE = 0
DEFAULT_SLEEP_END_HOUR = 5
DEFAULT_SLEEP_END_MINUTE = 0

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/elsisiem/muthaker-bot/master"
MORNING_ATHKAR_URL = f"{GITHUB_RAW_BASE}/الأذكار/أذكار_الصباح.jpg"
NIGHT_ATHKAR_URL = f"{GITHUB_RAW_BASE}/الأذكار/أذكار_المساء.jpg"

ALADHAN_API_URL = "https://api.aladhan.com/v1/timingsByCity"

SUPPORTED_LANGUAGES = {
    "en": "English",
    "ar": "العربية",
    "fr": "Français",
    "ru": "Русский",
}

SLEEP_PRESETS = {
    "early": {"label": "en: Early Sleeper (9PM-5AM)", "start": (21, 0), "end": (5, 0)},
    "normal": {"label": "en: Normal (11PM-6AM)", "start": (23, 0), "end": (6, 0)},
    "night_owl": {"label": "en: Night Owl (1AM-9AM)", "start": (1, 0), "end": (9, 0)},
    "minimal": {"label": "en: Minimal (12AM-4AM)", "start": (0, 0), "end": (4, 0)},
    "none": {"label": "en: No Sleep Hours", "start": None, "end": None},
}

ATHKAR_CATEGORIES = {
    "istighfar": "en: Istighfar (Seeking Forgiveness)",
    "tasbih": "en: Tasbih (Glorification)",
    "tahmid": "en: Tahmid (Praise)",
    "takbir": "en: Takbir (Magnification)",
    "tahlil": "en: Tahlil (Oneness of Allah)",
    "salawat": "en: Salawat (Blessings on Prophet)",
    "mixed": "en: Mixed Athkar (Variety)",
}