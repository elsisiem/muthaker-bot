import logging

from aiohttp import web
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from .config import TOKEN
from .db import init_db
from .handlers import (
    choose_personal_mode,
    choose_target_mode,
    go_home,
    link_target,
    manage_targets,
    remove_target_callback,
    send_test_to_targets,
    set_language,
    start,
)
from .scheduler import start_user_reminder_scheduler, stop_user_reminder_scheduler

logger = logging.getLogger(__name__)

application = Application.builder().token(TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("link", link_target))

application.add_handler(CallbackQueryHandler(set_language, pattern="^lang_(ar|en)$"))
application.add_handler(CallbackQueryHandler(go_home, pattern="^home$"))
application.add_handler(CallbackQueryHandler(choose_personal_mode, pattern="^mode_personal$"))
application.add_handler(CallbackQueryHandler(choose_target_mode, pattern="^mode_target$"))
application.add_handler(CallbackQueryHandler(manage_targets, pattern="^targets_manage$"))
application.add_handler(CallbackQueryHandler(send_test_to_targets, pattern="^targets_test$"))
application.add_handler(CallbackQueryHandler(remove_target_callback, pattern="^target_remove_"))


async def handle_root(request):
    return web.Response(text="User side bot is running")


web_app = web.Application()
web_app.router.add_get("/", handle_root)

__all__ = [
    "application",
    "web_app",
    "init_db",
    "start_user_reminder_scheduler",
    "stop_user_reminder_scheduler",
]
