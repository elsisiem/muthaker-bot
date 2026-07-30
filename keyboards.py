from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from i18n import t, get_languages_list
from config import ATHKAR_CATEGORIES, SLEEP_PRESETS
from services.timezone_service import get_timezone_choices


def language_keyboard(current_lang: str = None) -> InlineKeyboardMarkup:
    buttons = []
    for code, name in get_languages_list():
        prefix = "✓ " if code == current_lang else ""
        buttons.append([InlineKeyboardButton(f"{prefix}{name}", callback_data=f"lang:{code}")])
    return InlineKeyboardMarkup(buttons)


def timezone_method_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(t("share_location", lang), callback_data="tz:share")],
        [InlineKeyboardButton(t("type_manually", lang), callback_data="tz:manual")],
    ]
    return InlineKeyboardMarkup(buttons)


def confirm_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton(t("yes", lang), callback_data="confirm:yes"),
        InlineKeyboardButton(t("no", lang), callback_data="confirm:no"),
    ]]
    return InlineKeyboardMarkup(buttons)


def timezone_choices_keyboard(page: int = 0, lang: str = "en") -> InlineKeyboardMarkup:
    choices = get_timezone_choices()
    per_page = 6
    start = page * per_page
    page_choices = choices[start:start + per_page]

    buttons = []
    for tz_code, label in page_choices:
        buttons.append([InlineKeyboardButton(label, callback_data=f"tz:select:{tz_code}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Previous", callback_data=f"tz:page:{page - 1}"))
    if start + per_page < len(choices):
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"tz:page:{page + 1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)


def athkar_type_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    buttons = []
    for athkar_key, label in ATHKAR_CATEGORIES.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"athkar:{athkar_key}")])
    return InlineKeyboardMarkup(buttons)


def schedule_mode_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(t("schedule_mode_interval", lang), callback_data="mode:interval")],
        [InlineKeyboardButton(t("schedule_mode_goal", lang), callback_data="mode:goal")],
    ]
    return InlineKeyboardMarkup(buttons)


def interval_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    options = t("interval_options", lang)
    buttons = []
    row = []
    for i, opt in enumerate(options[:6]):
        row.append(InlineKeyboardButton(f"{opt} min" if opt.isdigit() else opt, callback_data=f"interval:{opt}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def goal_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    options = t("goal_options", lang)
    buttons = []
    row = []
    for i, opt in enumerate(options[:4]):
        row.append(InlineKeyboardButton(f"{opt}/day", callback_data=f"goal:{opt}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def sleep_preset_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    buttons = []
    for preset_key, preset_data in SLEEP_PRESETS.items():
        label = preset_data["label"]
        buttons.append([InlineKeyboardButton(label, callback_data=f"sleep:{preset_key}")])
    buttons.append([InlineKeyboardButton(t("custom", lang), callback_data="sleep:custom")])
    return InlineKeyboardMarkup(buttons)


def skip_or_enter_keyboard(skip_callback: str, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(t("skip", lang), callback_data=skip_callback)]]
    return InlineKeyboardMarkup(buttons)


def main_menu_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(t("manage_schedules", lang), callback_data="menu:schedules")],
        [InlineKeyboardButton(t("change_language", lang), callback_data="menu:language")],
        [InlineKeyboardButton(t("change_timezone", lang), callback_data="menu:timezone")],
        [InlineKeyboardButton(t("edit_sleep", lang), callback_data="menu:sleep")],
        [InlineKeyboardButton(t("prayer_settings", lang), callback_data="menu:prayer")],
        [InlineKeyboardButton(t("status", lang), callback_data="menu:status")],
        [InlineKeyboardButton(t("delete_account", lang), callback_data="menu:delete")],
    ]
    return InlineKeyboardMarkup(buttons)


def settings_menu_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return main_menu_keyboard(lang)


def schedule_management_keyboard(schedules: list, lang: str = "en") -> InlineKeyboardMarkup:
    buttons = []
    for sched in schedules:
        from services.athkar_content import format_athkar_schedule_value
        value = format_athkar_schedule_value(sched.mode, sched.interval_minutes, sched.daily_goal)
        status_icon = "🟢" if sched.is_active else "🔴"
        label = f"{status_icon} {sched.athkar_type} - {value}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"sched:toggle:{sched.id}")])
        buttons.append([
            InlineKeyboardButton("Edit", callback_data=f"sched:edit:{sched.id}"),
            InlineKeyboardButton("Delete", callback_data=f"sched:delete:{sched.id}"),
        ])
    buttons.append([InlineKeyboardButton(t("add_schedule", lang), callback_data="sched:add")])
    buttons.append([InlineKeyboardButton(t("back", lang), callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


def prayer_settings_keyboard(prayer, lang: str = "en") -> InlineKeyboardMarkup:
    morning_text = t("morning_enabled", lang).format(offset=prayer.morning_offset_minutes) if prayer and prayer.morning_athkar_enabled else t("morning_disabled", lang)
    night_text = t("night_enabled", lang).format(offset=prayer.night_offset_minutes) if prayer and prayer.night_athkar_enabled else t("night_disabled", lang)

    buttons = [
        [InlineKeyboardButton(f"Morning: {morning_text}", callback_data="prayer:morning_toggle")],
        [InlineKeyboardButton("Set Morning Offset", callback_data="prayer:morning_offset")],
        [InlineKeyboardButton(f"Night: {night_text}", callback_data="prayer:night_toggle")],
        [InlineKeyboardButton("Set Night Offset", callback_data="prayer:night_offset")],
        [InlineKeyboardButton("Change City", callback_data="prayer:city")],
        [InlineKeyboardButton(t("back", lang), callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(buttons)


def back_keyboard(callback_data: str = "menu:main", lang: str = "en") -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(t("back", lang), callback_data=callback_data)]]
    return InlineKeyboardMarkup(buttons)