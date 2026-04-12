from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from .i18n import tr


def language_row(lang: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(f"🇸🇦 {tr(lang, 'lang_ar')}", callback_data="lang_ar"),
        InlineKeyboardButton(f"🇬🇧 {tr(lang, 'lang_en')}", callback_data="lang_en"),
    ]


def persistent_language_row(lang: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(tr(lang, "lang_button"), callback_data="open_lang_menu")]


def home_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "mode_personal"), callback_data="mode_personal")],
        [InlineKeyboardButton(tr(lang, "mode_group"), callback_data="mode_group")],
        [InlineKeyboardButton(tr(lang, "mode_channel"), callback_data="mode_channel")],
        persistent_language_row(lang),
    ]
    return InlineKeyboardMarkup(rows)


def language_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        language_row(lang),
        [InlineKeyboardButton(tr(lang, "back"), callback_data="home")],
    ])


def personal_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "cfg_athkar"), callback_data="cfg_personal_athkar")],
        [InlineKeyboardButton(tr(lang, "cfg_schedule"), callback_data="cfg_personal_schedule")],
        [InlineKeyboardButton(tr(lang, "cfg_delivery"), callback_data="cfg_personal_delivery")],
        [InlineKeyboardButton(tr(lang, "cfg_prayer"), callback_data="cfg_personal_prayer")],
        [InlineKeyboardButton(tr(lang, "show_settings"), callback_data="cfg_personal_show")],
        persistent_language_row(lang),
        [InlineKeyboardButton(tr(lang, "back"), callback_data="home")],
    ])


def group_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "cfg_targets"), callback_data="targets_manage_group")],
        [InlineKeyboardButton(tr(lang, "cfg_athkar"), callback_data="cfg_group_athkar")],
        [InlineKeyboardButton(tr(lang, "cfg_schedule"), callback_data="cfg_group_schedule")],
        [InlineKeyboardButton(tr(lang, "send_test"), callback_data="targets_test")],
        persistent_language_row(lang),
        [InlineKeyboardButton(tr(lang, "back"), callback_data="home")],
    ])


def channel_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "cfg_targets"), callback_data="targets_manage_channel")],
        [InlineKeyboardButton(tr(lang, "cfg_athkar"), callback_data="cfg_channel_athkar")],
        [InlineKeyboardButton(tr(lang, "cfg_schedule"), callback_data="cfg_channel_schedule")],
        [InlineKeyboardButton(tr(lang, "send_test"), callback_data="targets_test")],
        persistent_language_row(lang),
        [InlineKeyboardButton(tr(lang, "back"), callback_data="home")],
    ])


def remove_target_menu(lang: str, targets: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chat_id, title in targets:
        rows.append([InlineKeyboardButton(f"🗑 {title}", callback_data=f"target_remove_{chat_id}")])
    rows.append(persistent_language_row(lang))
    rows.append([InlineKeyboardButton(tr(lang, "back"), callback_data="home")])
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
    rows.append([InlineKeyboardButton(tr(lang, "save"), callback_data="athkar_save")])
    rows.append(persistent_language_row(lang))
    rows.append([InlineKeyboardButton(tr(lang, "back"), callback_data="mode_personal")])
    return InlineKeyboardMarkup(rows)


def schedule_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "interval_5"), callback_data="schedule_every_5")],
        [InlineKeyboardButton(tr(lang, "interval_30"), callback_data="schedule_every_30")],
        [InlineKeyboardButton(tr(lang, "interval_60"), callback_data="schedule_hourly")],
        [InlineKeyboardButton(tr(lang, "interval_custom"), callback_data="schedule_custom")],
    ]
    rows.append(persistent_language_row(lang))
    rows.append([InlineKeyboardButton(tr(lang, "back"), callback_data="mode_personal")])
    return InlineKeyboardMarkup(rows)


def delivery_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "delivery_rotating"), callback_data="delivery_rotating")],
        [InlineKeyboardButton(tr(lang, "delivery_batch"), callback_data="delivery_batch")],
    ]
    rows.append(persistent_language_row(lang))
    rows.append([InlineKeyboardButton(tr(lang, "back"), callback_data="mode_personal")])
    return InlineKeyboardMarkup(rows)


def location_request_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(tr(lang, "btn_share_location"), request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        selective=True,
    )
