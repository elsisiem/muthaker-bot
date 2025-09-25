import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, text

# DATABASE_URL - Heroku automatically sets this when PostgreSQL addon is attached
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Convert postgres:// to postgresql+asyncpg:// for SQLAlchemy async
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL:
    pass
else:
    # Fallback to direct connection string (your provided credentials)
    DATABASE_URL = "postgresql+asyncpg://u3cmevgl2g6c6j:paf6377466881a2403b02f14624b98bf68879ed773b2ccf111d397fe536a381b9@c9pv5s2sq0i76o.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d1f1puvchrt773"

engine = create_async_engine(DATABASE_URL, echo=True)
Base = declarative_base()
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Define a user preferences model.
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    city = Column(String)
    country = Column(String)
    timezone = Column(String)
    language = Column(String, default="ar")  # Add language field
    athkar_preferences = Column(String)  # JSON string representing selected athkar and frequency mode
    quran_settings = Column(String)       # JSON string for Quran settings (mode, start, quantity)

# Conversation states
LANGUAGE, MAIN_MENU, ATHKAR, ATHKAR_FREQ, QURAN_CHOICE, QURAN_DETAILS, SLEEP_TIME, CITY_INFO = range(8)

async def get_user_language(user_id: str) -> str:
    """Get user's language from database."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT language FROM users WHERE telegram_id = :tid"), {"tid": user_id}
        )
        user = result.first()
        return user.language if user and user.language else "ar"

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add language column if it doesn't exist
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'ar'"))
