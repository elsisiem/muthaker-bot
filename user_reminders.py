"""
Sends personalized Athkar reminders to users based on their preferences.
Runs alongside the channel scheduler to send DM reminders.
"""

import os
import logging
import asyncio
import json
from datetime import datetime, timedelta
import pytz
import random

from telegram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from user_side import UserPreferences, engine, async_session, ATHKAR_OPTIONS

logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = Bot(TOKEN)
CAIRO_TZ = pytz.timezone("Africa/Cairo")

# ============================================================================
# REMINDER SENDING LOGIC
# ============================================================================

async def get_all_active_users():
    """Get all active users from database"""
    async with async_session() as session:
        result = await session.execute(
            select(UserPreferences).where(UserPreferences.is_active == True)
        )
        return result.scalars().all()

async def should_send_reminder(user: UserPreferences) -> bool:
    """Check if it's time to send reminder to this user"""
    user_tz = pytz.timezone(user.timezone)
    now = datetime.now(user_tz)

    frequency = user.frequency

    # Parse frequency
    if frequency.startswith("custom_"):
        times_per_day = int(frequency.split("_")[1])
        # Send reminders evenly distributed across the day
        interval_hours = 24 / times_per_day
        hour = now.hour

        # Check if current hour is close to a scheduled time
        for i in range(times_per_day):
            scheduled_hour = i * interval_hours
            if abs(hour - scheduled_hour) < 1:  # Within 1 hour window
                return True
        return False

    elif frequency == "1x_daily":
        # 6:00 AM
        return now.hour == 6 and now.minute < 5

    elif frequency == "2x_daily":
        # 6:00 AM and 7:00 PM
        return (now.hour == 6 or now.hour == 19) and now.minute < 5

    elif frequency == "3x_daily":
        # 6:00 AM, 1:00 PM, 7:00 PM
        return (now.hour in [6, 13, 19]) and now.minute < 5

    return False

async def get_user_athkar_text(user: UserPreferences, lang: str = "ar") -> str:
    """Get formatted Athkar text for the user"""
    if not user.selected_athkar:
        return None

    selected_ids = json.loads(user.selected_athkar)
    selected_athkar = [a for a in ATHKAR_OPTIONS if a["id"] in selected_ids]

    if not selected_athkar:
        return None

    # Pick a random Athkar or rotate through them
    athkar = random.choice(selected_athkar)

    text = f"{athkar['emoji']} <b>{athkar['ar']}</b>\n\n"
    text += f"<i>{athkar['text_ar']}</i>\n\n"
    text += "🌙 ذكر الله في كل وقت 🌙"

    return text

async def send_user_reminder(user: UserPreferences):
    """Send a reminder to a single user"""
    try:
        if not user.selected_athkar:
            logger.warning(f"User {user.telegram_id} has no selected Athkar")
            return False

        text = await get_user_athkar_text(user, user.language)
        if not text:
            return False

        await bot.send_message(
            chat_id=user.telegram_id,
            text=text,
            parse_mode="HTML"
        )
        logger.info(f"✅ Reminder sent to user {user.telegram_id}")
        return True

    except Exception as e:
        logger.error(f"❌ Error sending reminder to user {user.telegram_id}: {e}")
        return False

async def send_all_reminders():
    """Check all users and send reminders if due"""
    try:
        users = await get_all_active_users()
        logger.info(f"📋 Checking {len(users)} active users for reminders...")

        count = 0
        for user in users:
            if await should_send_reminder(user):
                if await send_user_reminder(user):
                    count += 1

        if count > 0:
            logger.info(f"📬 Sent {count} user reminders")

    except Exception as e:
        logger.error(f"Error in send_all_reminders: {e}", exc_info=True)

async def user_reminder_loop():
    """Main loop for user reminders - runs every minute"""
    logger.info("🔔 User reminder scheduler started")

    while True:
        try:
            await send_all_reminders()
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in user_reminder_loop: {e}", exc_info=True)
            await asyncio.sleep(60)

# ============================================================================
# STARTUP
# ============================================================================

async def init_user_reminders():
    """Initialize user reminders"""
    logger.info("Initializing user reminders...")
    return asyncio.create_task(user_reminder_loop())
