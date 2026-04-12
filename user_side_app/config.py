import os

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")
