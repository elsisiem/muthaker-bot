from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, text, select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, index=True)
    first_name = Column(String, nullable=True)
    language = Column(String, default="ar")
    mode = Column(String, default="personal")
    selected_athkar = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PostingTarget(Base):
    __tablename__ = "posting_targets"

    id = Column(Integer, primary_key=True)
    owner_telegram_id = Column(String, index=True)
    chat_id = Column(String, index=True)
    chat_title = Column(String, nullable=True)
    chat_type = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'ar'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'personal'"))


async def get_user_prefs(telegram_id: str) -> UserPreferences | None:
    async with async_session() as session:
        result = await session.execute(select(UserPreferences).where(UserPreferences.telegram_id == telegram_id))
        return result.scalars().first()


async def upsert_user_prefs(telegram_id: str, first_name: str | None, language: str | None = None, mode: str | None = None):
    async with async_session() as session:
        result = await session.execute(select(UserPreferences).where(UserPreferences.telegram_id == telegram_id))
        row = result.scalars().first()
        if row:
            if first_name is not None:
                row.first_name = first_name
            if language is not None:
                row.language = language
            if mode is not None:
                row.mode = mode
            row.updated_at = datetime.utcnow()
        else:
            row = UserPreferences(
                telegram_id=telegram_id,
                first_name=first_name,
                language=language or "ar",
                mode=mode or "personal",
            )
            session.add(row)
        await session.commit()
        return row


async def add_or_update_target(owner_telegram_id: str, chat_id: str, chat_title: str, chat_type: str):
    async with async_session() as session:
        result = await session.execute(
            select(PostingTarget).where(
                PostingTarget.owner_telegram_id == owner_telegram_id,
                PostingTarget.chat_id == chat_id,
            )
        )
        row = result.scalars().first()
        if row:
            row.chat_title = chat_title
            row.chat_type = chat_type
            row.is_active = True
        else:
            row = PostingTarget(
                owner_telegram_id=owner_telegram_id,
                chat_id=chat_id,
                chat_title=chat_title,
                chat_type=chat_type,
                is_active=True,
            )
            session.add(row)
        await session.commit()
        return row


async def list_targets(owner_telegram_id: str) -> list[PostingTarget]:
    async with async_session() as session:
        result = await session.execute(
            select(PostingTarget).where(
                PostingTarget.owner_telegram_id == owner_telegram_id,
                PostingTarget.is_active == True,
            )
        )
        return list(result.scalars().all())


async def remove_target(owner_telegram_id: str, chat_id: str):
    async with async_session() as session:
        await session.execute(
            delete(PostingTarget).where(
                PostingTarget.owner_telegram_id == owner_telegram_id,
                PostingTarget.chat_id == chat_id,
            )
        )
        await session.commit()
