import logging

from aiohttp import web
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .config import TOKEN
from .db import init_db
from .handlers import (
    config_placeholder,
    choose_channel_mode,
    choose_group_mode,
    choose_personal_mode,
    clear_all_athkar,
    handle_location_input,
    handle_text_input,
    go_home,
    link_target,
    manage_targets,
    open_delivery_menu,
    open_language_menu,
    open_personal_athkar,
    open_schedule_menu,
    remove_target_callback,
    save_athkar,
    send_test_to_targets,
    select_all_athkar,
    set_delivery,
    set_language,
    set_schedule,
    start,
    show_personal_settings,
    toggle_athkar,
    toggle_prayer,
    version,
)
from .scheduler import start_user_reminder_scheduler, stop_user_reminder_scheduler

logger = logging.getLogger(__name__)

application = Application.builder().token(TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("link", link_target))
application.add_handler(CommandHandler("version", version))

application.add_handler(CallbackQueryHandler(set_language, pattern="^lang_(ar|en)$"))
application.add_handler(CallbackQueryHandler(open_language_menu, pattern="^open_lang_menu$"))
application.add_handler(CallbackQueryHandler(go_home, pattern="^home$"))
application.add_handler(CallbackQueryHandler(choose_personal_mode, pattern="^mode_personal$"))
application.add_handler(CallbackQueryHandler(choose_group_mode, pattern="^mode_group$"))
application.add_handler(CallbackQueryHandler(choose_channel_mode, pattern="^mode_channel$"))
application.add_handler(CallbackQueryHandler(open_personal_athkar, pattern="^cfg_personal_athkar$"))
application.add_handler(CallbackQueryHandler(toggle_athkar, pattern="^athkar_toggle_"))
application.add_handler(CallbackQueryHandler(select_all_athkar, pattern="^athkar_select_all$"))
application.add_handler(CallbackQueryHandler(clear_all_athkar, pattern="^athkar_clear_all$"))
application.add_handler(CallbackQueryHandler(save_athkar, pattern="^athkar_save$"))
application.add_handler(CallbackQueryHandler(open_schedule_menu, pattern="^cfg_personal_schedule$"))
application.add_handler(CallbackQueryHandler(set_schedule, pattern="^schedule_"))
application.add_handler(CallbackQueryHandler(open_delivery_menu, pattern="^cfg_personal_delivery$"))
application.add_handler(CallbackQueryHandler(set_delivery, pattern="^delivery_(rotating|batch)$"))
application.add_handler(CallbackQueryHandler(toggle_prayer, pattern="^cfg_personal_prayer$"))
application.add_handler(CallbackQueryHandler(show_personal_settings, pattern="^cfg_personal_show$"))
application.add_handler(CallbackQueryHandler(manage_targets, pattern="^targets_manage_group$|^targets_manage_channel$|^targets_manage$"))
application.add_handler(CallbackQueryHandler(send_test_to_targets, pattern="^targets_test$"))
application.add_handler(CallbackQueryHandler(remove_target_callback, pattern="^target_remove_"))
application.add_handler(CallbackQueryHandler(config_placeholder, pattern="^cfg_"))
application.add_handler(MessageHandler(filters.LOCATION, handle_location_input))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))


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
