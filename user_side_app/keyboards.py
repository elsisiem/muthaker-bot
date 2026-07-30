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
    ], *navigation_footer(lang, back_callback)]


def navigation_footer(lang: str, back_callback: str) -> list[list[InlineKeyboardButton]]:
    """Use only navigation controls in compact, single-purpose screens."""
    return [[
        InlineKeyboardButton(tr(lang, "back"), callback_data=back_callback),
        InlineKeyboardButton(tr(lang, "close"), callback_data="close_home"),
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
        # A language picker should only show languages and a way out; repeating
        # language/time-zone controls here is visual noise.
        rows.extend(navigation_footer(lang, "home"))
    return InlineKeyboardMarkup(rows)


def locality_setup_menu(lang: str, back_callback: str = "home") -> InlineKeyboardMarkup:
    """Keep a one-time location request free of unrelated settings controls."""
    return InlineKeyboardMarkup(navigation_footer(lang, back_callback))


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
        return "✅" if enabled else "⚪"

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
        [InlineKeyboardButton(tr(lang, "community_other_posts"), callback_data="community_posts")],
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
        # Keep the selected mark compact; all other actions use normal emoji.
        prefix = "✓ " if selected else "✖️ "
        rows.append([InlineKeyboardButton(f"{prefix}{label}", callback_data=f"athkar_toggle_{athkar_id}")])
    rows.append([
        InlineKeyboardButton(tr(lang, "clear_all"), callback_data="athkar_clear_all"),
        InlineKeyboardButton(tr(lang, "choose_all"), callback_data="athkar_select_all"),
    ])
    rows.append([InlineKeyboardButton(tr(lang, "save_continue"), callback_data="athkar_save")])
    rows.extend(settings_footer(lang, "mode_personal"))
    return InlineKeyboardMarkup(rows)


def schedule_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "strategy_interval"), callback_data="schedule_strategy_interval")],
        [InlineKeyboardButton(tr(lang, "strategy_goal"), callback_data="schedule_strategy_goal")],
    ]
    rows.extend(settings_footer(lang, "cfg_personal_setup"))
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


def goal_scope_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "goal_total"), callback_data="goal_scope_total")],
        [InlineKeyboardButton(tr(lang, "goal_each"), callback_data="goal_scope_each")],
        [InlineKeyboardButton(tr(lang, "goal_advanced"), callback_data="goal_scope_advanced")],
    ]
    rows.extend(settings_footer(lang, "cfg_personal_schedule"))
    return InlineKeyboardMarkup(rows)


def goal_menu(lang: str, scope: str = "total") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "goal_50"), callback_data=f"goal_{scope}_50")],
        [InlineKeyboardButton(tr(lang, "goal_100"), callback_data=f"goal_{scope}_100")],
        [InlineKeyboardButton(tr(lang, "goal_200"), callback_data=f"goal_{scope}_200")],
        [InlineKeyboardButton(tr(lang, "goal_300"), callback_data=f"goal_{scope}_300")],
        [InlineKeyboardButton(tr(lang, "goal_custom"), callback_data=f"goal_{scope}_custom")],
    ]
    rows.extend(settings_footer(lang, "cfg_personal_schedule"))
    return InlineKeyboardMarkup(rows)


def advanced_goal_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton("50", callback_data="goal_adv_50"),
        InlineKeyboardButton("100", callback_data="goal_adv_100"),
        InlineKeyboardButton("200", callback_data="goal_adv_200"),
    ], [InlineKeyboardButton(tr(lang, "goal_custom"), callback_data="goal_adv_custom")]]
    rows.extend(settings_footer(lang, "cfg_personal_schedule"))
    return InlineKeyboardMarkup(rows)


def delivery_menu(lang: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tr(lang, "delivery_rotating"), callback_data="delivery_rotating")],
        [InlineKeyboardButton(tr(lang, "delivery_batch"), callback_data="delivery_batch")],
    ]
    rows.extend(settings_footer(lang, "cfg_personal_schedule"))
    return InlineKeyboardMarkup(rows)


def quiet_hours_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "quiet_none"), callback_data="quiet_none")],
        [InlineKeyboardButton(tr(lang, "quiet_fajr_isha"), callback_data="quiet_fajr_isha")],
        [InlineKeyboardButton(tr(lang, "quiet_sleep_10_fajr"), callback_data="quiet_sleep_10_fajr")],
        [InlineKeyboardButton(tr(lang, "quiet_sleep_11_fajr"), callback_data="quiet_sleep_11_fajr")],
        [InlineKeyboardButton(tr(lang, "quiet_sleep_12_fajr"), callback_data="quiet_sleep_12_fajr")],
        [InlineKeyboardButton(tr(lang, "quiet_custom"), callback_data="quiet_custom")],
        *settings_footer(lang, "cfg_personal_delivery"),
    ])


def setup_complete_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "edit_setup"), callback_data="cfg_personal_setup")],
        [InlineKeyboardButton(tr(lang, "start_over"), callback_data="cfg_personal_setup")],
        *settings_footer(lang, "mode_personal"),
    ])


def target_picker_menu(lang: str, targets) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(target.chat_title or target.chat_id, callback_data=f"target_select_{target.chat_id}")]
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


def community_posts_menu(lang: str, posts) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for post in posts:
        if post.content_type == "photo":
            label = tr(lang, "post_photo")
        elif post.content_type == "personal_athkar":
            label = tr(lang, "post_personal_athkar")
        else:
            label = (post.text_content or tr(lang, "post_message"))[:28]
        rows.append([InlineKeyboardButton(f"{tr(lang, 'delete')} {label}", callback_data=f"community_post_delete_{post.id}")])
    rows.extend([
        [
            InlineKeyboardButton(tr(lang, "post_add_message"), callback_data="community_post_add_text"),
            InlineKeyboardButton(tr(lang, "post_add_image"), callback_data="community_post_add_photo"),
        ],
        [InlineKeyboardButton(tr(lang, "post_add_personal_athkar"), callback_data="community_post_add_personal")],
        [InlineKeyboardButton(tr(lang, "back"), callback_data="community_back")],
    ])
    return InlineKeyboardMarkup(rows)


def post_schedule_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang, "post_schedule_clock"), callback_data="community_post_schedule_clock")],
        [InlineKeyboardButton(tr(lang, "post_schedule_prayer"), callback_data="community_post_schedule_prayer")],
        [InlineKeyboardButton(tr(lang, "post_schedule_interval"), callback_data="community_post_schedule_interval")],
        [InlineKeyboardButton(tr(lang, "back"), callback_data="community_back")],
    ])


def post_prayer_anchor_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr(lang, "prayer_fajr"), callback_data="community_post_anchor_Fajr"),
            InlineKeyboardButton(tr(lang, "prayer_dhuhr"), callback_data="community_post_anchor_Dhuhr"),
        ],
        [
            InlineKeyboardButton(tr(lang, "prayer_asr"), callback_data="community_post_anchor_Asr"),
            InlineKeyboardButton(tr(lang, "prayer_maghrib"), callback_data="community_post_anchor_Maghrib"),
        ],
        [InlineKeyboardButton(tr(lang, "prayer_isha"), callback_data="community_post_anchor_Isha")],
        [InlineKeyboardButton(tr(lang, "back"), callback_data="community_posts")],
    ])


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
