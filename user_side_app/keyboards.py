from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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
