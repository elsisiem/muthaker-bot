from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    KeyboardButtonRequestChat, ReplyKeyboardMarkup,
)

from .i18n import tr


LANGUAGE_CODES = ("ar", "en", "es", "fr", "tr")


def language_row(lang: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(f"🇸🇦 {tr(lang, 'lang_ar')}", callback_data="lang_ar"),
        InlineKeyboardButton(f"🇬🇧 {tr(lang, 'lang_en')}", callback_data="lang_en"),
        InlineKeyboardButton(f"🇪🇸 {tr(lang, 'lang_es')}", callback_data="lang_es"),
        InlineKeyboardButton(f"🇫🇷 {tr(lang, 'lang_fr')}", callback_data="lang_fr"),
        InlineKeyboardButton(f"🇹🇷 {tr(lang, 'lang_tr')}", callback_data="lang_tr"),
    ]


def persistent_language_row(lang: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(tr(lang, "lang_button"), callback_data="open_lang_menu")]


def settings_footer(lang: str, back_callback: str) -> list[list[InlineKeyboardButton]]:
    return [[
        InlineKeyboardButton(tr(lang, "cfg_timezone"), callback_data="cfg_personal_timezone"),
        InlineKeyboardButton(tr(lang, "lang_button"), callback_data="open_lang_menu"),
        InlineKeyboardButton(tr(lang, "back"), callback_data=back_callback),
    ]]


def home_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "mode_personal"), callback_data="mode_personal")],
        [InlineKeyboardButton(tr(lang, "mode_community"), callback_data="mode_community")],
        [
            InlineKeyboardButton(tr(lang, "cfg_timezone"), callback_data="cfg_personal_timezone"),
            InlineKeyboardButton(tr(lang, "lang_button"), callback_data="open_lang_menu"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def language_menu(lang: str, show_back: bool = True) -> InlineKeyboardMarkup:
    rows = [
        language_row(lang)[:3],
        language_row(lang)[3:],
    ]
    if show_back:
        rows.extend(settings_footer(lang, "home"))
    return InlineKeyboardMarkup(rows)


def personal_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "setup_reminders"), callback_data="cfg_personal_setup")],
        [InlineKeyboardButton(tr(lang, "cfg_prayer"), callback_data="cfg_personal_prayer")],
        [InlineKeyboardButton(tr(lang, "show_settings"), callback_data="cfg_personal_show")],
        *settings_footer(lang, "home"),
    ])


def community_connect_menu(lang: str) -> InlineKeyboardMarkup:
    """Native Telegram pickers must be requested separately for groups and channels."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr(lang, "add_group"), callback_data="targets_refresh_group"),
            InlineKeyboardButton(tr(lang, "add_channel"), callback_data="targets_refresh_channel"),
        ],
        [InlineKeyboardButton(tr(lang, "manage_targets"), callback_data="targets_manage")],
        [InlineKeyboardButton(tr(lang, "refresh_targets"), callback_data="targets_refresh")],
        *settings_footer(lang, "home"),
    ])


def community_menu(lang: str, target) -> InlineKeyboardMarkup:
    def state(enabled: bool) -> str:
        return "✅" if enabled else "⬜"

    rows = [
        [
            InlineKeyboardButton(f"{state(target.morning_athkar_enabled)} {tr(lang, 'community_morning')}", callback_data="community_toggle_morning"),
            InlineKeyboardButton(f"{state(target.night_athkar_enabled)} {tr(lang, 'community_night')}", callback_data="community_toggle_night"),
        ],
        [
            InlineKeyboardButton(f"{state(target.monday_fasting_enabled)} {tr(lang, 'community_monday')}", callback_data="community_toggle_monday"),
            InlineKeyboardButton(f"{state(target.thursday_fasting_enabled)} {tr(lang, 'community_thursday')}", callback_data="community_toggle_thursday"),
        ],
        [
            InlineKeyboardButton(tr(lang, "community_prayer_times"), callback_data="community_prayer_times"),
            InlineKeyboardButton(tr(lang, "community_change_city"), callback_data="community_change_city"),
        ],
        [InlineKeyboardButton(tr(lang, "send_test"), callback_data="targets_test")],
        [
            InlineKeyboardButton(tr(lang, "manage_targets"), callback_data="targets_manage"),
            InlineKeyboardButton(tr(lang, "refresh_targets"), callback_data="targets_refresh"),
        ],
        *settings_footer(lang, "mode_community"),
    ]
    return InlineKeyboardMarkup(rows)


# Kept as compatibility shims for already-open Telegram messages from earlier releases.
def group_menu(lang: str) -> InlineKeyboardMarkup:
    return community_connect_menu(lang)


def channel_menu(lang: str) -> InlineKeyboardMarkup:
    return community_connect_menu(lang)


def remove_target_menu(lang: str, targets: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat_id, title in targets:
        rows.append([InlineKeyboardButton(f"🗑 {title}", callback_data=f"target_remove_{chat_id}")])
    rows.extend(settings_footer(lang, "home"))
    return InlineKeyboardMarkup(rows)


def athkar_select_menu(lang: str, items: list[tuple[str, str, bool]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for athkar_id, label, selected in items:
        prefix = "✓ " if selected else "○ "
        rows.append([InlineKeyboardButton(f"{prefix}{label}", callback_data=f"athkar_toggle_{athkar_id}")])
    rows.append([
        InlineKeyboardButton(tr(lang, "choose_all"), callback_data="athkar_select_all"),
        InlineKeyboardButton(tr(lang, "clear_all"), callback_data="athkar_clear_all"),
    ])
    rows.append([InlineKeyboardButton(tr(lang, "save_continue"), callback_data="athkar_save")])
    rows.append([InlineKeyboardButton(tr(lang, "close"), callback_data="close_home")])
    return InlineKeyboardMarkup(rows)


def schedule_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "strategy_interval"), callback_data="schedule_strategy_interval")],
        [InlineKeyboardButton(tr(lang, "strategy_goal"), callback_data="schedule_strategy_goal")],
    ]
    rows.extend(settings_footer(lang, "mode_personal"))
    return InlineKeyboardMarkup(rows)


def interval_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "interval_5"), callback_data="schedule_every_5")],
        [InlineKeyboardButton(tr(lang, "interval_30"), callback_data="schedule_every_30")],
        [InlineKeyboardButton(tr(lang, "interval_60"), callback_data="schedule_hourly")],
        [InlineKeyboardButton(tr(lang, "interval_custom"), callback_data="schedule_custom")],
    ]
    rows.extend(settings_footer(lang, "cfg_personal_schedule"))
    return InlineKeyboardMarkup(rows)


def goal_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "goal_100"), callback_data="schedule_goal_100")],
        [InlineKeyboardButton(tr(lang, "goal_200"), callback_data="schedule_goal_200")],
        [InlineKeyboardButton(tr(lang, "goal_300"), callback_data="schedule_goal_300")],
        [InlineKeyboardButton(tr(lang, "goal_custom"), callback_data="schedule_goal_custom")],
    ]
    rows.extend(settings_footer(lang, "cfg_personal_schedule"))
    return InlineKeyboardMarkup(rows)


def delivery_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "delivery_rotating"), callback_data="delivery_rotating")],
        [InlineKeyboardButton(tr(lang, "delivery_batch"), callback_data="delivery_batch")],
    ]
    rows.extend(settings_footer(lang, "mode_personal"))
    return InlineKeyboardMarkup(rows)


def quiet_hours_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "quiet_normal"), callback_data="quiet_normal")],
        [InlineKeyboardButton(tr(lang, "quiet_early"), callback_data="quiet_early")],
        [InlineKeyboardButton(tr(lang, "quiet_night_owl"), callback_data="quiet_night_owl")],
        [InlineKeyboardButton(tr(lang, "quiet_none"), callback_data="quiet_none")],
        [InlineKeyboardButton(tr(lang, "close"), callback_data="close_home")],
    ])


def setup_complete_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "edit_setup"), callback_data="cfg_personal_setup")],
        [InlineKeyboardButton(tr(lang, "start_over"), callback_data="cfg_personal_setup")],
        [InlineKeyboardButton(tr(lang, "close"), callback_data="close_home")],
    ])


def target_picker_menu(lang: str, targets) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{'📣' if target.chat_type == 'channel' else '👥'} {target.chat_title or target.chat_id}", callback_data=f"target_select_{target.chat_id}")]
        for target in targets
    ]
    rows.append([
        InlineKeyboardButton(tr(lang, "add_group"), callback_data="targets_refresh_group"),
        InlineKeyboardButton(tr(lang, "add_channel"), callback_data="targets_refresh_channel"),
    ])
    rows.append([InlineKeyboardButton(tr(lang, "manage_targets"), callback_data="targets_manage")])
    rows.append([InlineKeyboardButton(tr(lang, "refresh_targets"), callback_data="targets_refresh")])
    rows.extend(settings_footer(lang, "mode_community"))
    return InlineKeyboardMarkup(rows)


def target_request_keyboard(lang: str, mode: str) -> ReplyKeyboardMarkup:
    is_channel = mode == "channel"
    request = KeyboardButtonRequestChat(
        request_id=1 if is_channel else 2,
        chat_is_channel=is_channel,
        bot_is_member=True,
    )
    return ReplyKeyboardMarkup(
        [[KeyboardButton(tr(lang, "choose_channel" if is_channel else "choose_group"), request_chat=request)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def location_request_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(tr(lang, "btn_share_location"), request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
        input_field_placeholder=tr(lang, "prayer_city_prompt"),
    )
