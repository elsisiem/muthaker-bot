import logging

from aiohttp import web
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from .config import TOKEN
from .db import init_db
from .handlers import (
    config_placeholder,
    choose_channel_mode,
    choose_group_mode,
    choose_personal_mode,
    go_home,
    link_target,
    manage_targets,
    open_language_menu,
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
application.add_handler(CallbackQueryHandler(open_language_menu, pattern="^open_lang_menu$"))
application.add_handler(CallbackQueryHandler(go_home, pattern="^home$"))
application.add_handler(CallbackQueryHandler(choose_personal_mode, pattern="^mode_personal$"))
application.add_handler(CallbackQueryHandler(choose_group_mode, pattern="^mode_group$"))
application.add_handler(CallbackQueryHandler(choose_channel_mode, pattern="^mode_channel$"))
application.add_handler(CallbackQueryHandler(manage_targets, pattern="^targets_manage_group$|^targets_manage_channel$|^targets_manage$"))
application.add_handler(CallbackQueryHandler(send_test_to_targets, pattern="^targets_test$"))
application.add_handler(CallbackQueryHandler(remove_target_callback, pattern="^target_remove_"))
application.add_handler(CallbackQueryHandler(config_placeholder, pattern="^cfg_"))


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
