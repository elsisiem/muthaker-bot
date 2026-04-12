"""Compatibility shim for user-side bot exports.

The implementation now lives under the `user_side_app` package.
"""

from user_side_app import (
    application,
    web_app,
    init_db,
    start_user_reminder_scheduler,
    stop_user_reminder_scheduler,
)

__all__ = [
    "application",
    "web_app",
    "init_db",
    "start_user_reminder_scheduler",
    "stop_user_reminder_scheduler",
]