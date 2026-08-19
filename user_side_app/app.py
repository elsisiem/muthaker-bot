import logging

from aiohttp import web
from telegram import BotCommand
from telegram.ext import Application, CallbackQueryHandler, ChatMemberHandler, CommandHandler, MessageHandler, filters
from telegram.error import BadRequest

from .config import TOKEN
from .db import init_db
from .handlers import (
    auto_register_target,
    choose_channel_mode,
    choose_community_mode,
    choose_goal_scope,
    choose_group_mode,
    choose_personal_mode,
    close_to_home,
    confirm_reset,
    begin_personal_setup,
    begin_edit_setup,
    finish_edit_setup,
    begin_custom_athkar,
    execute_reset,
    clear_all_athkar,
    handle_location_input,
    handle_text_input,
    go_home,
    link_target,
    manage_targets,
    open_delivery_menu,
    open_goal_scope_menu,
    open_language_menu,
    open_personal_athkar,
    open_quiet_hours_menu,
    open_schedule_menu,
    remove_target_callback,
    request_target_discovery,
    select_target,
    handle_chat_shared,
    save_athkar,
    send_test_to_targets,
    select_all_athkar,
    set_delivery,
    set_language,
    set_quiet_hours,
    set_schedule,
    set_goal_value,
    set_advanced_goal,
    edit_settings_command,
    help_command,
    reset_command,
    communities_command,
    morning_evening_command,
    settings_command,
    start,
    show_personal_settings,
    toggle_athkar,
    toggle_community_post,
    toggle_prayer,
    choose_morning_evening_offset,
    set_morning_evening_offset,
    change_community_city,
    choose_community_post_schedule,
    community_back,
    begin_community_post,
    delete_community_post,
    handle_community_photo,
    open_community_posts,
    set_community_post_anchor,
    show_community_prayer_times,
    begin_timezone_setup,
    version,
)
from .scheduler import start_user_reminder_scheduler, stop_user_reminder_scheduler

logger = logging.getLogger(__name__)

application = Application.builder().token(TOKEN).build()


async def log_error(update, context):
    if isinstance(context.error, BadRequest) and "Message is not modified" in str(context.error):
        logger.debug("Ignored no-op Telegram message edit")
        return
    logger.error("Unhandled bot update error", exc_info=context.error)

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("settings", settings_command))
application.add_handler(CommandHandler("view_settings", settings_command))
application.add_handler(CommandHandler("edit_setting", edit_settings_command))
application.add_handler(CommandHandler("edit_settings", edit_settings_command))
application.add_handler(CommandHandler("morning_evening", morning_evening_command))
application.add_handler(CommandHandler("groups", communities_command))
application.add_handler(CommandHandler("reset", reset_command))
application.add_handler(CommandHandler("link", link_target))
application.add_handler(CommandHandler("version", version))
application.add_handler(ChatMemberHandler(auto_register_target, ChatMemberHandler.MY_CHAT_MEMBER))

application.add_handler(CallbackQueryHandler(set_language, pattern="^lang_[a-z]{2}$"))
application.add_handler(CallbackQueryHandler(open_language_menu, pattern="^open_lang_menu$"))
application.add_handler(CallbackQueryHandler(go_home, pattern="^home$"))
application.add_handler(CallbackQueryHandler(close_to_home, pattern="^close_home$"))
application.add_handler(CallbackQueryHandler(confirm_reset, pattern="^reset_confirm$"))
application.add_handler(CallbackQueryHandler(execute_reset, pattern="^reset_execute$"))
application.add_handler(CallbackQueryHandler(choose_personal_mode, pattern="^mode_personal$"))
application.add_handler(CallbackQueryHandler(begin_personal_setup, pattern="^cfg_personal_setup$"))
application.add_handler(CallbackQueryHandler(begin_edit_setup, pattern="^cfg_personal_edit$"))
application.add_handler(CallbackQueryHandler(finish_edit_setup, pattern="^edit_done$"))
application.add_handler(CallbackQueryHandler(choose_group_mode, pattern="^mode_group$"))
application.add_handler(CallbackQueryHandler(choose_channel_mode, pattern="^mode_channel$"))
application.add_handler(CallbackQueryHandler(choose_community_mode, pattern="^mode_community$"))
# Previously sent group/channel cards now reopen the real unified flow instead
# of leading to the old placeholder screen.
application.add_handler(CallbackQueryHandler(choose_community_mode, pattern="^cfg_(group|channel)_"))
application.add_handler(CallbackQueryHandler(open_personal_athkar, pattern="^cfg_personal_athkar$"))
application.add_handler(CallbackQueryHandler(toggle_athkar, pattern="^athkar_toggle_"))
application.add_handler(CallbackQueryHandler(select_all_athkar, pattern="^athkar_select_all$"))
application.add_handler(CallbackQueryHandler(clear_all_athkar, pattern="^athkar_clear_all$"))
application.add_handler(CallbackQueryHandler(begin_custom_athkar, pattern="^athkar_custom_add$"))
application.add_handler(CallbackQueryHandler(save_athkar, pattern="^athkar_save$"))
application.add_handler(CallbackQueryHandler(open_schedule_menu, pattern="^cfg_personal_schedule$"))
application.add_handler(CallbackQueryHandler(open_goal_scope_menu, pattern="^cfg_personal_goal_scope$"))
application.add_handler(CallbackQueryHandler(set_schedule, pattern="^schedule_"))
application.add_handler(CallbackQueryHandler(choose_goal_scope, pattern="^goal_scope_"))
application.add_handler(CallbackQueryHandler(set_goal_value, pattern="^goal_(total|each)_"))
application.add_handler(CallbackQueryHandler(set_advanced_goal, pattern="^goal_adv_"))
application.add_handler(CallbackQueryHandler(open_delivery_menu, pattern="^cfg_personal_delivery$"))
application.add_handler(CallbackQueryHandler(set_delivery, pattern="^delivery_(rotating|batch|random|complete|sequential)$"))
application.add_handler(CallbackQueryHandler(toggle_prayer, pattern="^cfg_personal_prayer$"))
application.add_handler(CallbackQueryHandler(choose_morning_evening_offset, pattern="^morning_evening_choose_(morning|evening)$"))
application.add_handler(CallbackQueryHandler(set_morning_evening_offset, pattern="^morning_evening_offset_(10|20|30|custom)$"))
application.add_handler(CallbackQueryHandler(open_quiet_hours_menu, pattern="^cfg_personal_quiet$"))
application.add_handler(CallbackQueryHandler(begin_timezone_setup, pattern="^cfg_personal_timezone$"))
application.add_handler(CallbackQueryHandler(
    set_quiet_hours,
    pattern="^quiet_(normal|early|night_owl|none|fajr_isha|sleep_10_fajr|sleep_11_fajr|sleep_12_fajr|sleep_1_fajr|custom)$",
))
application.add_handler(CallbackQueryHandler(show_personal_settings, pattern="^cfg_personal_show$"))
application.add_handler(CallbackQueryHandler(manage_targets, pattern="^targets_manage_group$|^targets_manage_channel$|^targets_manage$"))
application.add_handler(CallbackQueryHandler(send_test_to_targets, pattern="^targets_test$"))
application.add_handler(CallbackQueryHandler(request_target_discovery, pattern="^targets_refresh(?:_group|_channel)?$"))
application.add_handler(CallbackQueryHandler(remove_target_callback, pattern="^target_remove_"))
application.add_handler(CallbackQueryHandler(select_target, pattern="^target_select_"))
application.add_handler(CallbackQueryHandler(toggle_community_post, pattern="^community_toggle_"))
application.add_handler(CallbackQueryHandler(change_community_city, pattern="^community_change_city$"))
application.add_handler(CallbackQueryHandler(show_community_prayer_times, pattern="^community_prayer_times$"))
application.add_handler(CallbackQueryHandler(open_community_posts, pattern="^community_posts$"))
application.add_handler(CallbackQueryHandler(begin_community_post, pattern="^community_post_add_"))
application.add_handler(CallbackQueryHandler(choose_community_post_schedule, pattern="^community_post_schedule_"))
application.add_handler(CallbackQueryHandler(set_community_post_anchor, pattern="^community_post_anchor_"))
application.add_handler(CallbackQueryHandler(delete_community_post, pattern="^community_post_delete_"))
application.add_handler(CallbackQueryHandler(community_back, pattern="^community_back$"))
application.add_handler(MessageHandler(filters.StatusUpdate.CHAT_SHARED, handle_chat_shared))
application.add_handler(MessageHandler(filters.LOCATION, handle_location_input))
application.add_handler(MessageHandler(filters.PHOTO, handle_community_photo))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
application.add_error_handler(log_error)


async def configure_command_menu():
    """Publish a compact Arabic command menu through Telegram's Bot API."""
    await application.bot.set_my_commands([
        BotCommand("start", "البدء"),
        BotCommand("view_settings", "عرض الإعدادات"),
        BotCommand("edit_settings", "تعديل الإعدادات"),
        BotCommand("morning_evening", "أذكار الصباح والمساء"),
        BotCommand("groups", "المجموعات والقنوات"),
        BotCommand("reset", "البدء من جديد"),
        BotCommand("help", "المساعدة"),
    ])


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
    "configure_command_menu",
]
