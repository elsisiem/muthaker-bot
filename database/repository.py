from datetime import datetime
from sqlalchemy.orm import Session

from .models import User, AthkarSchedule, SleepSettings, PrayerSettings, Chat, ChatSettings, ChatMessage


class UserRepository:
    @staticmethod
    def get_or_create(session: Session, user_id: int, username: str = None, first_name: str = None) -> User:
        user = session.get(User, user_id)
        if not user:
            user = User(id=user_id, username=username, first_name=first_name)
            session.add(user)
            session.flush()
        else:
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
        return user

    @staticmethod
    def update(session: Session, user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        user.updated_at = datetime.utcnow()
        session.flush()
        return user

    @staticmethod
    def get_all_active(session: Session):
        return session.query(User).filter(User.onboarding_complete == True).all()

    @staticmethod
    def delete(session: Session, user_id: int):
        user = session.get(User, user_id)
        if user:
            session.delete(user)
            session.flush()


class ScheduleRepository:
    @staticmethod
    def create(session: Session, user_id: int, **kwargs) -> AthkarSchedule:
        schedule = AthkarSchedule(user_id=user_id, **kwargs)
        session.add(schedule)
        session.flush()
        return schedule

    @staticmethod
    def get_for_user(session: Session, user_id: int):
        return session.query(AthkarSchedule).filter(AthkarSchedule.user_id == user_id).all()

    @staticmethod
    def get_active_for_user(session: Session, user_id: int):
        return session.query(AthkarSchedule).filter(
            AthkarSchedule.user_id == user_id,
            AthkarSchedule.is_active == True,
        ).all()

    @staticmethod
    def get_all_active(session: Session):
        return session.query(AthkarSchedule).join(User).filter(
            AthkarSchedule.is_active == True,
            User.onboarding_complete == True,
        ).all()

    @staticmethod
    def update(session: Session, schedule: AthkarSchedule, **kwargs):
        for key, value in kwargs.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)
        session.flush()
        return schedule

    @staticmethod
    def delete(session: Session, schedule_id: int):
        schedule = session.get(AthkarSchedule, schedule_id)
        if schedule:
            session.delete(schedule)
            session.flush()

    @staticmethod
    def reset_daily_counters(session: Session):
        session.query(AthkarSchedule).update({AthkarSchedule.sent_today: 0})
        session.flush()


class SettingsRepository:
    @staticmethod
    def get_sleep(session: Session, user_id: int) -> SleepSettings:
        settings = session.query(SleepSettings).filter(SleepSettings.user_id == user_id).first()
        if not settings:
            settings = SleepSettings(user_id=user_id)
            session.add(settings)
            session.flush()
        return settings

    @staticmethod
    def update_sleep(session: Session, sleep: SleepSettings, **kwargs):
        for key, value in kwargs.items():
            if hasattr(sleep, key):
                setattr(sleep, key, value)
        session.flush()
        return sleep

    @staticmethod
    def get_prayer(session: Session, user_id: int) -> PrayerSettings:
        settings = session.query(PrayerSettings).filter(PrayerSettings.user_id == user_id).first()
        if not settings:
            settings = PrayerSettings(user_id=user_id)
            session.add(settings)
            session.flush()
        return settings

    @staticmethod
    def update_prayer(session: Session, prayer: PrayerSettings, **kwargs):
        for key, value in kwargs.items():
            if hasattr(prayer, key):
                setattr(prayer, key, value)
        session.flush()
        return prayer


class ChatRepository:
    @staticmethod
    def get_or_create(session: Session, chat_id: int, title: str = None, chat_type: str = "channel", added_by: int = None) -> Chat:
        chat = session.get(Chat, chat_id)
        if not chat:
            chat = Chat(id=chat_id, title=title, chat_type=chat_type, added_by=added_by)
            session.add(chat)
            session.flush()
        else:
            if title:
                chat.title = title
        return chat

    @staticmethod
    def get_all_active(session: Session):
        return session.query(Chat).filter(Chat.is_active == True).all()

    @staticmethod
    def get_all_with_settings(session: Session):
        return session.query(Chat).filter(Chat.is_active == True).all()

    @staticmethod
    def update(session: Session, chat: Chat, **kwargs):
        for key, value in kwargs.items():
            if hasattr(chat, key):
                setattr(chat, key, value)
        chat.updated_at = datetime.utcnow()
        session.flush()
        return chat

    @staticmethod
    def delete(session: Session, chat_id: int):
        chat = session.get(Chat, chat_id)
        if chat:
            session.delete(chat)
            session.flush()

    @staticmethod
    def get_settings(session: Session, chat_id: int) -> ChatSettings:
        settings = session.query(ChatSettings).filter(ChatSettings.chat_id == chat_id).first()
        if not settings:
            settings = ChatSettings(chat_id=chat_id)
            session.add(settings)
            session.flush()
        return settings

    @staticmethod
    def update_settings(session: Session, settings: ChatSettings, **kwargs):
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        session.flush()
        return settings

    @staticmethod
    def add_message(session: Session, chat_id: int, message_id: int, message_type: str):
        msg = ChatMessage(chat_id=chat_id, message_id=message_id, message_type=message_type)
        session.add(msg)
        session.flush()
        return msg

    @staticmethod
    def get_messages_by_type(session: Session, chat_id: int, message_type: str):
        return session.query(ChatMessage).filter(
            ChatMessage.chat_id == chat_id,
            ChatMessage.message_type == message_type,
        ).all()

    @staticmethod
    def delete_messages_by_type(session: Session, chat_id: int, message_type: str):
        session.query(ChatMessage).filter(
            ChatMessage.chat_id == chat_id,
            ChatMessage.message_type == message_type,
        ).delete()
        session.flush()

    @staticmethod
    def is_user_admin_of_chat(application, chat_id: int, user_id: int) -> bool:
        import asyncio
        try:
            member = asyncio.get_event_loop().run_until_complete(
                application.bot.get_chat_member(chat_id, user_id)
            )
            return member.status in ["creator", "administrator"]
        except Exception:
            return False