import logging
from datetime import datetime, timedelta, date
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from database import get_session, ChatRepository
from database.models import Chat, ChatSettings
from services.prayer_api import get_user_prayer_times
from config import GITHUB_RAW_BASE

logger = logging.getLogger(__name__)

MORNING_ATHKAR_URL = f"{GITHUB_RAW_BASE}/الأذكار/أذكار_الصباح.jpg"
NIGHT_ATHKAR_URL = f"{GITHUB_RAW_BASE}/الأذكار/أذكار_المساء.jpg"
QURAN_PAGES_URL = f"{GITHUB_RAW_BASE}/المصحف"

_application = None


class ChannelDispatcher:
    def __init__(self, application):
        global _application
        _application = application

    async def dispatch(self):
        session = get_session()
        try:
            active_chats = ChatRepository.get_all_active(session)
            if not active_chats:
                return

            utc_now = datetime.now(pytz.UTC)

            for chat in active_chats:
                try:
                    settings = ChatRepository.get_settings(session, chat.id)
                    if not settings:
                        continue

                    try:
                        chat_tz = pytz.timezone(settings.timezone)
                    except Exception:
                        chat_tz = pytz.timezone("Africa/Cairo")

                    chat_now = utc_now.astimezone(chat_tz)
                    today_str = chat_now.strftime("%Y-%m-%d")

                    prayer_times = await self._get_chat_prayer_times(session, settings, chat_now, chat_tz)
                    if not prayer_times:
                        continue

                    await self._send_morning_athkar(chat, settings, chat_now, prayer_times, session)
                    await self._send_night_athkar(chat, settings, chat_now, prayer_times, session)
                    await self._send_quran_pages(chat, settings, chat_now, prayer_times, session)

                    if settings.status_message_enabled and chat_now.minute == settings.status_message_hour:
                        await self._send_status_message(chat, settings, chat_now, prayer_times, session)

                except Exception as e:
                    logger.error(f"Error dispatching for chat {chat.id}: {e}", exc_info=True)

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Channel dispatcher error: {e}", exc_info=True)
        finally:
            session.close()

    async def _get_chat_prayer_times(self, session: Session, settings: ChatSettings, chat_now: datetime, chat_tz):
        today_str = chat_now.strftime("%Y-%m-%d")

        if settings.cached_prayer_times and settings.cached_prayer_date == today_str:
            return settings.cached_prayer_times

        timings_dict = await get_user_prayer_times(
            settings.city or "Cairo",
            settings.country or "Egypt",
            settings.method or 3,
            settings.timezone or "Africa/Cairo",
        )
        if timings_dict:
            timings = {k: v.strftime("%H:%M") for k, v in timings_dict.items()}
            settings.cached_prayer_times = timings
            settings.cached_prayer_date = today_str
            return timings
        return None

    async def _send_morning_athkar(self, chat: Chat, settings: ChatSettings, chat_now: datetime, prayer_times: dict, session: Session):
        if not settings.morning_athkar_enabled:
            return

        fajr_str = prayer_times.get("Fajr")
        if not fajr_str:
            return

        try:
            hour, minute = map(int, fajr_str.split(":"))
            fajr_time = chat_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            offset = settings.morning_offset_minutes or 35
            target_time = fajr_time + timedelta(minutes=offset)

            diff = abs((chat_now - target_time).total_seconds())
            if diff > 45:
                return

            today_key = f"chat_morning_{chat.id}_{chat_now.strftime('%Y%m%d')}"
            if session.info.get(today_key):
                return
            session.info[today_key] = True

            caption = "#أذكار_الصباح"
            msg = await _application.bot.send_photo(
                chat_id=chat.id,
                photo=MORNING_ATHKAR_URL,
                caption=caption,
            )

            old_msgs = ChatRepository.get_messages_by_type(session, chat.id, "night")
            for old in old_msgs:
                try:
                    await _application.bot.delete_message(chat.id, old.message_id)
                except Exception:
                    pass

            ChatRepository.delete_messages_by_type(session, chat.id, "night")
            ChatRepository.add_message(session, chat.id, msg.message_id, "morning")
            logger.info(f"Sent morning athkar to chat {chat.id}")

        except Exception as e:
            logger.error(f"Failed to send morning athkar to chat {chat.id}: {e}")

    async def _send_night_athkar(self, chat: Chat, settings: ChatSettings, chat_now: datetime, prayer_times: dict, session: Session):
        if not settings.night_athkar_enabled:
            return

        asr_str = prayer_times.get("Asr")
        if not asr_str:
            return

        try:
            hour, minute = map(int, asr_str.split(":"))
            asr_time = chat_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            offset = settings.night_offset_minutes or 30
            target_time = asr_time + timedelta(minutes=offset)

            diff = abs((chat_now - target_time).total_seconds())
            if diff > 45:
                return

            today_key = f"chat_night_{chat.id}_{chat_now.strftime('%Y%m%d')}"
            if session.info.get(today_key):
                return
            session.info[today_key] = True

            caption = "#أذكار_المساء"
            msg = await _application.bot.send_photo(
                chat_id=chat.id,
                photo=NIGHT_ATHKAR_URL,
                caption=caption,
            )

            old_msgs = ChatRepository.get_messages_by_type(session, chat.id, "morning")
            for old in old_msgs:
                try:
                    await _application.bot.delete_message(chat.id, old.message_id)
                except Exception:
                    pass

            ChatRepository.delete_messages_by_type(session, chat.id, "morning")
            ChatRepository.add_message(session, chat.id, msg.message_id, "night")
            logger.info(f"Sent night athkar to chat {chat.id}")

        except Exception as e:
            logger.error(f"Failed to send night athkar to chat {chat.id}: {e}")

    async def _send_quran_pages(self, chat: Chat, settings: ChatSettings, chat_now: datetime, prayer_times: dict, session: Session):
        if not settings.quran_pages_enabled:
            return

        asr_str = prayer_times.get("Asr")
        if not asr_str:
            return

        try:
            hour, minute = map(int, asr_str.split(":"))
            asr_time = chat_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            night_offset = settings.night_offset_minutes or 30
            quran_offset = settings.quran_offset_minutes or 10
            target_time = asr_time + timedelta(minutes=night_offset + quran_offset)

            diff = abs((chat_now - target_time).total_seconds())
            if diff > 45:
                return

            today_key = f"chat_quran_{chat.id}_{chat_now.strftime('%Y%m%d')}"
            if session.info.get(today_key):
                return
            session.info[today_key] = True

            page1, page2 = get_quran_pages_for_date(chat_now.date())
            url1 = f"{QURAN_PAGES_URL}/photo_{page1}.jpg"
            url2 = f"{QURAN_PAGES_URL}/photo_{page2}.jpg"

            from telegram import InputMediaPhoto
            media = [
                InputMediaPhoto(media=url1),
                InputMediaPhoto(media=url2, caption="#ورد_اليوم"),
            ]
            messages = await _application.bot.send_media_group(chat_id=chat.id, media=media)

            for msg in messages:
                ChatRepository.add_message(session, chat.id, msg.message_id, "quran")
            logger.info(f"Sent Quran pages to chat {chat.id}: {page1}-{page2}")

        except Exception as e:
            logger.error(f"Failed to send Quran pages to chat {chat.id}: {e}")

    async def _send_status_message(self, chat: Chat, settings: ChatSettings, chat_now: datetime, prayer_times: dict, session: Session):
        try:
            fajr_t = prayer_times.get("Fajr", "N/A")
            asr_t = prayer_times.get("Asr", "N/A")

            morning_offset = settings.morning_offset_minutes or 35
            night_offset = settings.night_offset_minutes or 30
            quran_offset = settings.quran_offset_minutes or 10

            status_text = (
                "🤖 *Bot Status Report*\n"
                f"─────────────────\n\n"
                f"📅 Date: {chat_now.strftime('%Y-%m-%d')}\n"
                f"🕐 Time: {chat_now.strftime('%H:%M')}\n"
                f"🌍 City: {settings.city}\n\n"
                f"🕌 *Prayer Times Today*\n"
                f"🌅 Fajr: {fajr_t}\n"
                f"☀ Dhuhr: {prayer_times.get('Dhuhr', 'N/A')}\n"
                f"🌤 Asr: {asr_t}\n"
                f"🌇 Maghrib: {prayer_times.get('Maghrib', 'N/A')}\n"
                f"🌙 Isha: {prayer_times.get('Isha', 'N/A')}\n\n"
                f"📋 *Configured Schedule*\n"
                f"   Morning Athkar: {morning_offset} min after Fajr ({'ON' if settings.morning_athkar_enabled else 'OFF'})\n"
                f"   Night Athkar: {night_offset} min after Asr ({'ON' if settings.night_athkar_enabled else 'OFF'})\n"
                f"   Quran Pages: {quran_offset} min after night athkar ({'ON' if settings.quran_pages_enabled else 'OFF'})\n"
            )

            await _application.bot.send_message(
                chat_id=chat.id,
                text=status_text,
                parse_mode="Markdown",
            )
            logger.info(f"Sent status message to chat {chat.id}")
        except Exception as e:
            logger.error(f"Failed to send status message to chat {chat.id}: {e}")


def get_quran_pages_for_date(target_date: date = None) -> tuple:
    if target_date is None:
        target_date = date.today()

    reference_date = date(2025, 5, 27)
    reference_first_page = 2

    days_since_reference = (target_date - reference_date).days
    first_page = reference_first_page + (days_since_reference * 2)

    total_pages = 603
    if first_page > 604:
        cycles = (first_page - 2) // total_pages
        first_page = 2 + ((first_page - 2) % total_pages)
    elif first_page < 2:
        while first_page < 2:
            first_page += total_pages

    second_page = first_page + 1
    if second_page > 604:
        second_page = 2

    return first_page, second_page


async def start_channel_dispatcher(application):
    dispatcher = ChannelDispatcher(application)
    return dispatcher