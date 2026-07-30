from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, JSON, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    language = Column(String(10), default="en")
    timezone = Column(String(50), default="UTC")
    onboarding_complete = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    schedules = relationship("AthkarSchedule", back_populates="user", cascade="all, delete-orphan")
    sleep_settings = relationship("SleepSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    prayer_settings = relationship("PrayerSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class AthkarSchedule(Base):
    __tablename__ = "athkar_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"))
    athkar_type = Column(String(50), default="mixed")
    mode = Column(String(20), default="interval")
    interval_minutes = Column(Integer, nullable=True)
    daily_goal = Column(Integer, nullable=True)
    sent_today = Column(Integer, default=0)
    last_sent_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="schedules")


class SleepSettings(Base):
    __tablename__ = "sleep_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    sleep_start_hour = Column(Integer, default=23)
    sleep_start_minute = Column(Integer, default=0)
    sleep_end_hour = Column(Integer, default=5)
    sleep_end_minute = Column(Integer, default=0)
    is_enabled = Column(Boolean, default=True)

    user = relationship("User", back_populates="sleep_settings")


class PrayerSettings(Base):
    __tablename__ = "prayer_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    city = Column(String(100), default="Makkah")
    country = Column(String(100), default="Saudi Arabia")
    method = Column(Integer, default=4)
    morning_athkar_enabled = Column(Boolean, default=True)
    night_athkar_enabled = Column(Boolean, default=True)
    morning_offset_minutes = Column(Integer, default=30)
    night_offset_minutes = Column(Integer, default=30)
    cached_prayer_times = Column(JSON, nullable=True)
    cached_prayer_date = Column(String(20), nullable=True)

    user = relationship("User", back_populates="prayer_settings")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(BigInteger, primary_key=True)
    title = Column(String(200), nullable=True)
    chat_type = Column(String(20), default="channel")
    is_active = Column(Boolean, default=True)
    added_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    settings = relationship("ChatSettings", back_populates="chat", uselist=False, cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="chat", cascade="all, delete-orphan")


class ChatSettings(Base):
    __tablename__ = "chat_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), unique=True)
    city = Column(String(100), default="Cairo")
    country = Column(String(100), default="Egypt")
    method = Column(Integer, default=3)
    timezone = Column(String(50), default="Africa/Cairo")
    morning_athkar_enabled = Column(Boolean, default=True)
    night_athkar_enabled = Column(Boolean, default=True)
    morning_offset_minutes = Column(Integer, default=35)
    night_offset_minutes = Column(Integer, default=30)
    quran_pages_enabled = Column(Boolean, default=True)
    quran_offset_minutes = Column(Integer, default=10)
    status_message_enabled = Column(Boolean, default=True)
    status_message_hour = Column(Integer, default=0)
    cached_prayer_times = Column(JSON, nullable=True)
    cached_prayer_date = Column(String(20), nullable=True)

    chat = relationship("Chat", back_populates="settings")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, ForeignKey("chats.id", ondelete="CASCADE"))
    message_id = Column(BigInteger)
    message_type = Column(String(20))

    chat = relationship("Chat", back_populates="messages")