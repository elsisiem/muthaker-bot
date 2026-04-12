from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import tr


def language_row(lang: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(f"🇸🇦 {tr(lang, 'lang_ar')}", callback_data="lang_ar"),
        InlineKeyboardButton(f"🇬🇧 {tr(lang, 'lang_en')}", callback_data="lang_en"),
    ]


def home_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        language_row(lang),
        [InlineKeyboardButton(tr(lang, "mode_personal"), callback_data="mode_personal")],
        [InlineKeyboardButton(tr(lang, "mode_target"), callback_data="mode_target")],
        [InlineKeyboardButton(tr(lang, "manage_targets"), callback_data="targets_manage")],
    ]
    return InlineKeyboardMarkup(rows)


def target_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        language_row(lang),
        [InlineKeyboardButton(tr(lang, "refresh"), callback_data="targets_manage")],
        [InlineKeyboardButton(tr(lang, "send_test"), callback_data="targets_test")],
        [InlineKeyboardButton(tr(lang, "back"), callback_data="home")],
    ])


def remove_target_menu(lang: str, targets: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [language_row(lang)]
    for chat_id, title in targets:
        rows.append([InlineKeyboardButton(f"🗑 {title}", callback_data=f"target_remove_{chat_id}")])
    rows.append([InlineKeyboardButton(tr(lang, "back"), callback_data="targets_manage")])
    return InlineKeyboardMarkup(rows)
