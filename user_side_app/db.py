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
    custom_athkar = Column(Text, nullable=True)
    frequency = Column(String, default="every_30_min")
    custom_frequency_minutes = Column(Integer, nullable=True)
    daily_goal_count = Column(Integer, nullable=True)
    daily_goal_per_athkar = Column(Text, nullable=True)
    delivery_mode = Column(String, default="rotating")
    prayer_athkar_enabled = Column(Boolean, default=False)
    # Keep the two offsets independent: morning and evening may be scheduled
    # at different intervals after Fajr and Asr.
    morning_athkar_offset_minutes = Column(Integer, default=30)
    evening_athkar_offset_minutes = Column(Integer, default=30)
    prayer_city = Column(String, nullable=True)
    timezone = Column(String, default="Africa/Cairo")
    quiet_hours_preset = Column(String, default="normal")
    quiet_start_hour = Column(Integer, default=23)
    quiet_end_hour = Column(Integer, default=6)
    quiet_start_minute = Column(Integer, default=0)
    quiet_end_minute = Column(Integer, default=0)
    # JSON list of custom quiet periods, for example [[1320, 300], [780, 840]].
    # The original single-period columns remain as a backwards-compatible
    # first period for older installs and goal-spacing calculations.
    quiet_periods = Column(Text, nullable=True)
    onboarding_complete = Column(Boolean, default=False)
    timezone_confirmed = Column(Boolean, default=False)
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
    city = Column(String, nullable=True)
    timezone = Column(String, default="Africa/Cairo")
    prayer_method = Column(Integer, default=3)
    morning_athkar_enabled = Column(Boolean, default=True)
    night_athkar_enabled = Column(Boolean, default=True)
    monday_fasting_enabled = Column(Boolean, default=True)
    thursday_fasting_enabled = Column(Boolean, default=True)
    last_morning_sent_date = Column(String, nullable=True)
    last_night_sent_date = Column(String, nullable=True)
    last_monday_sent_date = Column(String, nullable=True)
    last_thursday_sent_date = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CommunityPost(Base):
    """A user-created recurring post for one linked group or channel."""
    __tablename__ = "community_posts"

    id = Column(Integer, primary_key=True)
    owner_telegram_id = Column(String, index=True, nullable=False)
    target_chat_id = Column(String, index=True, nullable=False)
    content_type = Column(String, nullable=False)  # text, photo, personal_athkar
    text_content = Column(Text, nullable=True)
    photo_file_id = Column(String, nullable=True)
    caption = Column(Text, nullable=True)
    schedule_type = Column(String, nullable=False)  # clock, prayer, interval
    time_of_day = Column(String, nullable=True)  # HH:MM in the target timezone
    prayer_name = Column(String, nullable=True)
    prayer_offset_minutes = Column(Integer, default=0)
    interval_minutes = Column(Integer, nullable=True)
    last_sent_key = Column(String, nullable=True)
    last_sent_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS language VARCHAR DEFAULT 'ar'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'personal'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS frequency VARCHAR DEFAULT 'every_30_min'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS custom_frequency_minutes INTEGER"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS daily_goal_count INTEGER"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS daily_goal_per_athkar TEXT"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS custom_athkar TEXT"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS delivery_mode VARCHAR DEFAULT 'rotating'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS prayer_athkar_enabled BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS morning_athkar_offset_minutes INTEGER DEFAULT 30"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS evening_athkar_offset_minutes INTEGER DEFAULT 30"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS prayer_city VARCHAR"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS timezone VARCHAR DEFAULT 'Africa/Cairo'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS quiet_hours_preset VARCHAR DEFAULT 'normal'"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS quiet_start_hour INTEGER DEFAULT 23"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS quiet_end_hour INTEGER DEFAULT 6"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS quiet_start_minute INTEGER DEFAULT 0"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS quiet_end_minute INTEGER DEFAULT 0"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS quiet_periods TEXT"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS onboarding_complete BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE user_preferences ADD COLUMN IF NOT EXISTS timezone_confirmed BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS city VARCHAR"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS timezone VARCHAR DEFAULT 'Africa/Cairo'"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS prayer_method INTEGER DEFAULT 3"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS morning_athkar_enabled BOOLEAN DEFAULT TRUE"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS night_athkar_enabled BOOLEAN DEFAULT TRUE"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS monday_fasting_enabled BOOLEAN DEFAULT TRUE"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS thursday_fasting_enabled BOOLEAN DEFAULT TRUE"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS last_morning_sent_date VARCHAR"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS last_night_sent_date VARCHAR"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS last_monday_sent_date VARCHAR"))
        await conn.execute(text("ALTER TABLE posting_targets ADD COLUMN IF NOT EXISTS last_thursday_sent_date VARCHAR"))


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


async def update_user_settings(
    telegram_id: str,
    *,
    selected_athkar: str | None = None,
    custom_athkar: str | None = None,
    frequency: str | None = None,
    custom_frequency_minutes: int | None = None,
    daily_goal_count: int | None = None,
    daily_goal_per_athkar: str | None = None,
    delivery_mode: str | None = None,
    prayer_athkar_enabled: bool | None = None,
    morning_athkar_offset_minutes: int | None = None,
    evening_athkar_offset_minutes: int | None = None,
    prayer_city: str | None = None,
    timezone: str | None = None,
    quiet_hours_preset: str | None = None,
    quiet_start_hour: int | None = None,
    quiet_end_hour: int | None = None,
    quiet_start_minute: int | None = None,
    quiet_end_minute: int | None = None,
    quiet_periods: str | None = None,
    onboarding_complete: bool | None = None,
    timezone_confirmed: bool | None = None,
):
    async with async_session() as session:
        result = await session.execute(select(UserPreferences).where(UserPreferences.telegram_id == telegram_id))
        row = result.scalars().first()
        if not row:
            return None

        if selected_athkar is not None:
            row.selected_athkar = selected_athkar
        if custom_athkar is not None:
            row.custom_athkar = custom_athkar
        if frequency is not None:
            row.frequency = frequency
        if custom_frequency_minutes is not None or frequency == "custom_interval":
            row.custom_frequency_minutes = custom_frequency_minutes
        if daily_goal_count is not None or frequency == "goal_per_day":
            row.daily_goal_count = daily_goal_count
        if daily_goal_per_athkar is not None or frequency == "goal_per_athkar":
            row.daily_goal_per_athkar = daily_goal_per_athkar
        if delivery_mode is not None:
            row.delivery_mode = delivery_mode
        if prayer_athkar_enabled is not None:
            row.prayer_athkar_enabled = prayer_athkar_enabled
        if morning_athkar_offset_minutes is not None:
            row.morning_athkar_offset_minutes = morning_athkar_offset_minutes
        if evening_athkar_offset_minutes is not None:
            row.evening_athkar_offset_minutes = evening_athkar_offset_minutes
        if prayer_city is not None:
            row.prayer_city = prayer_city
        if timezone is not None:
            row.timezone = timezone
        if quiet_hours_preset is not None:
            row.quiet_hours_preset = quiet_hours_preset
        if quiet_start_hour is not None:
            row.quiet_start_hour = quiet_start_hour
        if quiet_end_hour is not None:
            row.quiet_end_hour = quiet_end_hour
        if quiet_start_minute is not None:
            row.quiet_start_minute = quiet_start_minute
        if quiet_end_minute is not None:
            row.quiet_end_minute = quiet_end_minute
        if quiet_periods is not None:
            row.quiet_periods = quiet_periods
        if onboarding_complete is not None:
            row.onboarding_complete = onboarding_complete
        if timezone_confirmed is not None:
            row.timezone_confirmed = timezone_confirmed

        row.updated_at = datetime.utcnow()
        await session.commit()
        return row


async def list_active_users() -> list[UserPreferences]:
    async with async_session() as session:
        result = await session.execute(select(UserPreferences).where(UserPreferences.is_active == True))
        return list(result.scalars().all())


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


async def list_targets(owner_telegram_id: str, chat_type: str | None = None) -> list[PostingTarget]:
    async with async_session() as session:
        statement = select(PostingTarget).where(
            PostingTarget.owner_telegram_id == owner_telegram_id,
            PostingTarget.is_active == True,
        )
        if chat_type == "group":
            statement = statement.where(PostingTarget.chat_type.in_(("group", "supergroup")))
        elif chat_type:
            statement = statement.where(PostingTarget.chat_type == chat_type)
        result = await session.execute(statement.order_by(PostingTarget.created_at.desc()))
        return list(result.scalars().all())


async def get_target(owner_telegram_id: str, chat_id: str) -> PostingTarget | None:
    async with async_session() as session:
        result = await session.execute(
            select(PostingTarget).where(
                PostingTarget.owner_telegram_id == owner_telegram_id,
                PostingTarget.chat_id == chat_id,
                PostingTarget.is_active == True,
            )
        )
        return result.scalars().first()


async def update_target_settings(owner_telegram_id: str, chat_id: str, **settings) -> PostingTarget | None:
    """Persist the settings for one linked group or channel only."""
    allowed = {
        "city", "timezone", "prayer_method", "morning_athkar_enabled",
        "night_athkar_enabled", "monday_fasting_enabled", "thursday_fasting_enabled",
        "last_morning_sent_date", "last_night_sent_date", "last_monday_sent_date",
        "last_thursday_sent_date",
    }
    async with async_session() as session:
        result = await session.execute(
            select(PostingTarget).where(
                PostingTarget.owner_telegram_id == owner_telegram_id,
                PostingTarget.chat_id == chat_id,
            )
        )
        row = result.scalars().first()
        if not row:
            return None
        for key, value in settings.items():
            if key in allowed:
                setattr(row, key, value)
        await session.commit()
        return row


async def reset_user_preferences(telegram_id: str):
    """Clear all user-owned setup while retaining the account record itself."""
    async with async_session() as session:
        result = await session.execute(select(UserPreferences).where(UserPreferences.telegram_id == telegram_id))
        row = result.scalars().first()
        if not row:
            return None
        await session.execute(delete(CommunityPost).where(CommunityPost.owner_telegram_id == telegram_id))
        await session.execute(delete(PostingTarget).where(PostingTarget.owner_telegram_id == telegram_id))
        row.language = "ar"
        row.mode = "personal"
        row.selected_athkar = "[]"
        row.custom_athkar = "[]"
        row.frequency = "every_30_min"
        row.custom_frequency_minutes = None
        row.daily_goal_count = None
        row.daily_goal_per_athkar = None
        row.delivery_mode = "sequential"
        row.prayer_athkar_enabled = False
        row.morning_athkar_offset_minutes = 30
        row.evening_athkar_offset_minutes = 30
        row.prayer_city = None
        row.timezone = "Africa/Cairo"
        row.quiet_hours_preset = "normal"
        row.quiet_start_hour = 23
        row.quiet_end_hour = 6
        row.quiet_start_minute = 0
        row.quiet_end_minute = 0
        row.quiet_periods = None
        row.onboarding_complete = False
        row.timezone_confirmed = False
        row.updated_at = datetime.utcnow()
        await session.commit()
        return row


async def list_schedulable_targets() -> list[PostingTarget]:
    """Targets with a configured city are ready for the community dispatcher."""
    async with async_session() as session:
        result = await session.execute(
            select(PostingTarget).where(
                PostingTarget.is_active == True,
                PostingTarget.city.is_not(None),
            )
        )
        return list(result.scalars().all())


async def create_community_post(
    owner_telegram_id: str,
    target_chat_id: str,
    *,
    content_type: str,
    text_content: str | None = None,
    photo_file_id: str | None = None,
    caption: str | None = None,
    schedule_type: str,
    time_of_day: str | None = None,
    prayer_name: str | None = None,
    prayer_offset_minutes: int = 0,
    interval_minutes: int | None = None,
) -> CommunityPost:
    async with async_session() as session:
        row = CommunityPost(
            owner_telegram_id=owner_telegram_id,
            target_chat_id=target_chat_id,
            content_type=content_type,
            text_content=text_content,
            photo_file_id=photo_file_id,
            caption=caption,
            schedule_type=schedule_type,
            time_of_day=time_of_day,
            prayer_name=prayer_name,
            prayer_offset_minutes=prayer_offset_minutes,
            interval_minutes=interval_minutes,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def list_community_posts(owner_telegram_id: str, target_chat_id: str) -> list[CommunityPost]:
    async with async_session() as session:
        result = await session.execute(
            select(CommunityPost).where(
                CommunityPost.owner_telegram_id == owner_telegram_id,
                CommunityPost.target_chat_id == target_chat_id,
                CommunityPost.is_active == True,
            ).order_by(CommunityPost.created_at.desc())
        )
        return list(result.scalars().all())


async def list_active_community_posts() -> list[CommunityPost]:
    async with async_session() as session:
        result = await session.execute(select(CommunityPost).where(CommunityPost.is_active == True))
        return list(result.scalars().all())


async def mark_community_post_sent(post_id: int, *, sent_key: str | None = None, sent_at: datetime | None = None) -> None:
    async with async_session() as session:
        result = await session.execute(select(CommunityPost).where(CommunityPost.id == post_id))
        row = result.scalars().first()
        if not row:
            return
        if sent_key is not None:
            row.last_sent_key = sent_key
        if sent_at is not None:
            row.last_sent_at = sent_at
        await session.commit()


async def remove_community_post(owner_telegram_id: str, post_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(CommunityPost).where(
                CommunityPost.id == post_id,
                CommunityPost.owner_telegram_id == owner_telegram_id,
            )
        )
        row = result.scalars().first()
        if not row:
            return False
        row.is_active = False
        await session.commit()
        return True


async def remove_target(owner_telegram_id: str, chat_id: str):
    async with async_session() as session:
        await session.execute(
            delete(PostingTarget).where(
                PostingTarget.owner_telegram_id == owner_telegram_id,
                PostingTarget.chat_id == chat_id,
            )
        )
        await session.commit()
