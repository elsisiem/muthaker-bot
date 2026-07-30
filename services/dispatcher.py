import logging
from datetime import datetime, timedelta, date
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from database import get_session, UserRepository, ScheduleRepository, SettingsRepository, ChatRepository
from database.models import User, AthkarSchedule, PrayerSettings
from services.prayer_api import get_user_prayer_times
from services.athkar_content import get_random_athkar, format_athkar_schedule_value
from services.channel_dispatcher import ChannelDispatcher
from config import (
    MORNING_ATHKAR_URL, NIGHT_ATHKAR_URL,
    DEFAULT_MORNING_OFFSET, DEFAULT_NIGHT_OFFSET,
)

logger = logging.getLogger(__name__)

_application = None
_channel_dispatcher = None


class AthkarDispatcher:
    def __init__(self, application):
        global _application
        _application = application

    async def dispatch(self):
        await self._dispatch_users()
        await self._dispatch_channels()

    async def _dispatch_users(self):
        session = get_session()
        try:
            active_users = UserRepository.get_all_active(session)
            if not active_users:
                return

            utc_now = datetime.now(pytz.UTC)

            for user in active_users:
                try:
                    user_tz = pytz.timezone(user.timezone)
                except Exception:
                    user_tz = pytz.UTC

                user_now = utc_now.astimezone(user_tz)

                if self._is_sleep_time(session, user.id, user_now):
                    continue

                await self._process_schedules(session, user, user_now, user_tz)
                await self._process_morning_night_athkar(session, user, user_now, user_tz)

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"User dispatch error: {e}", exc_info=True)
        finally:
            session.close()

    async def _dispatch_channels(self):
        global _channel_dispatcher
        if _channel_dispatcher:
            await _channel_dispatcher.dispatch()

    def _is_sleep_time(self, session: Session, user_id: int, user_now: datetime) -> bool:
        sleep = SettingsRepository.get_sleep(session, user_id)
        if not sleep or not sleep.is_enabled:
            return False

        current_minutes = user_now.hour * 60 + user_now.minute
        start_minutes = sleep.sleep_start_hour * 60 + sleep.sleep_start_minute
        end_minutes = sleep.sleep_end_hour * 60 + sleep.sleep_end_minute

        if start_minutes <= end_minutes:
            return start_minutes <= current_minutes <= end_minutes
        else:
            return current_minutes >= start_minutes or current_minutes <= end_minutes

    async def _process_schedules(self, session: Session, user: User, user_now: datetime, user_tz):
        schedules = ScheduleRepository.get_active_for_user(session, user.id)

        for schedule in schedules:
            if schedule.mode == "goal" and schedule.daily_goal:
                wake_minutes = self._get_wake_minutes(session, user.id)
                if wake_minutes > 0:
                    effective_interval = wake_minutes / schedule.daily_goal
                else:
                    effective_interval = schedule.interval_minutes or 15
            elif schedule.mode == "interval" and schedule.interval_minutes:
                effective_interval = schedule.interval_minutes
            else:
                continue

            if schedule.last_sent_at:
                last_sent = schedule.last_sent_at.replace(tzinfo=user_tz)
                if last_sent.tzinfo is None:
                    last_sent = user_tz.localize(last_sent)
                elapsed = (user_now - last_sent).total_seconds()
                if elapsed < (effective_interval * 60):
                    continue

            athkar_text = get_random_athkar(schedule.athkar_type)
            try:
                await _application.bot.send_message(
                    chat_id=user.id,
                    text=athkar_text,
                )
                schedule.last_sent_at = user_now.replace(tzinfo=None)
                schedule.sent_today = (schedule.sent_today or 0) + 1
            except Exception as e:
                logger.warning(f"Failed to send athkar to user {user.id}: {e}")

    async def _process_morning_night_athkar(self, session: Session, user: User, user_now: datetime, user_tz):
        prayer = SettingsRepository.get_prayer(session, user.id)
        if not prayer:
            return

        today_str = user_now.strftime("%Y-%m-%d")

        if prayer.cached_prayer_times and prayer.cached_prayer_date == today_str:
            timings = prayer.cached_prayer_times
        else:
            timings_dict = await get_user_prayer_times(
                prayer.city, prayer.country, prayer.method, user.timezone
            )
            if timings_dict:
                timings = {k: v.strftime("%H:%M") for k, v in timings_dict.items()}
                prayer.cached_prayer_times = timings
                prayer.cached_prayer_date = today_str
            else:
                return

        if prayer.morning_athkar_enabled:
            await self._maybe_send_morning(session, user, user_now, timings, prayer)

        if prayer.night_athkar_enabled:
            await self._maybe_send_night(session, user, user_now, timings, prayer)

    async def _maybe_send_morning(self, session: Session, user: User, user_now: datetime, timings: dict, prayer: PrayerSettings):
        fajr_str = timings.get("Fajr")
        if not fajr_str:
            return

        try:
            hour, minute = map(int, fajr_str.split(":"))
            fajr_time = user_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            offset = prayer.morning_offset_minutes or DEFAULT_MORNING_OFFSET
            target_time = fajr_time + timedelta(minutes=offset)

            diff = abs((user_now - target_time).total_seconds())
            if diff <= 45:
                today_key = f"morning_sent_{user_now.strftime('%Y%m%d')}"
                if session.info.get(today_key):
                    return
                session.info[today_key] = True

                try:
                    await _application.bot.send_photo(
                        chat_id=user.id,
                        photo=MORNING_ATHKAR_URL,
                        caption="#أذكار_الصباح",
                    )
                except Exception as e:
                    logger.warning(f"Failed to send morning athkar to user {user.id}: {e}")
        except (ValueError, AttributeError):
            pass

    async def _maybe_send_night(self, session: Session, user: User, user_now: datetime, timings: dict, prayer: PrayerSettings):
        asr_str = timings.get("Asr")
        if not asr_str:
            return

        try:
            hour, minute = map(int, asr_str.split(":"))
            asr_time = user_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            offset = prayer.night_offset_minutes or DEFAULT_NIGHT_OFFSET
            target_time = asr_time + timedelta(minutes=offset)

            diff = abs((user_now - target_time).total_seconds())
            if diff <= 45:
                today_key = f"night_sent_{user_now.strftime('%Y%m%d')}"
                if session.info.get(today_key):
                    return
                session.info[today_key] = True

                try:
                    await _application.bot.send_photo(
                        chat_id=user.id,
                        photo=NIGHT_ATHKAR_URL,
                        caption="#أذكار_المساء",
                    )
                except Exception as e:
                    logger.warning(f"Failed to send night athkar to user {user.id}: {e}")
        except (ValueError, AttributeError):
            pass

    def _get_wake_minutes(self, session: Session, user_id: int) -> int:
        sleep = SettingsRepository.get_sleep(session, user_id)
        if not sleep or not sleep.is_enabled:
            return 24 * 60

        start_minutes = sleep.sleep_start_hour * 60 + sleep.sleep_start_minute
        end_minutes = sleep.sleep_end_hour * 60 + sleep.sleep_end_minute

        if start_minutes <= end_minutes:
            sleep_duration = end_minutes - start_minutes
        else:
            sleep_duration = (24 * 60 - start_minutes) + end_minutes

        return max(60, (24 * 60) - sleep_duration)


async def start_dispatcher(application):
    global _channel_dispatcher

    dispatcher = AthkarDispatcher(application)
    _channel_dispatcher = await ChannelDispatcher.__new__(ChannelDispatcher)
    _channel_dispatcher.__init__(application)

    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler(timezone=pytz.UTC)
    scheduler.add_job(dispatcher.dispatch, "interval", minutes=1, id="athkar_dispatcher")
    scheduler.add_job(
        lambda: _reset_daily_counters(),
        "cron",
        hour=0,
        minute=1,
        id="daily_reset",
    )
    scheduler.start()
    logger.info("Dispatcher started (users + channels)")
    return dispatcher


def _reset_daily_counters():
    session = get_session()
    try:
        ScheduleRepository.reset_daily_counters(session)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to reset daily counters: {e}")
    finally:
        session.close()