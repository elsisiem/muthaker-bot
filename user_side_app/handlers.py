import logging

from telegram import Update
from telegram.ext import ContextTypes

from .db import (
    add_or_update_target,
    get_user_prefs,
    list_targets,
    remove_target,
    upsert_user_prefs,
)
from .i18n import tr
from .keyboards import channel_menu, group_menu, home_menu, language_menu, personal_menu, remove_target_menu

logger = logging.getLogger(__name__)
UI_BUILD = "user-side-v173a"


def get_lang(context: ContextTypes.DEFAULT_TYPE, fallback: str = "ar") -> str:
    return "en" if context.user_data.get("lang") == "en" else fallback


async def send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text_value: str, reply_markup):
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text_value, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text_value, reply_markup=reply_markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    user_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name
    prefs = await get_user_prefs(user_id)

    lang = prefs.language if prefs and prefs.language in ("ar", "en") else "ar"
    context.user_data["lang"] = lang

    await upsert_user_prefs(user_id, first_name, language=lang)

    text_value = f"{tr(lang, 'welcome')}\n\n{tr(lang, 'choose_mode')}\n\n({UI_BUILD})"
    await send_or_edit(update, context, text_value, home_menu(lang))


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(
        text=f"{tr(lang, 'welcome')}\n\n{tr(lang, 'choose_mode')}\n\n({UI_BUILD})",
        reply_markup=home_menu(lang),
    )


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    chat_type = update.effective_chat.type if update.effective_chat else "unknown"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{UI_BUILD}\nchat_type={chat_type}\nmodule=user_side_app.handlers",
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.from_user:
        return

    lang = "en" if query.data == "lang_en" else "ar"
    context.user_data["lang"] = lang

    await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, language=lang)

    await query.edit_message_text(text=f"{tr(lang, 'lang_set')}\n\n{tr(lang, 'choose_mode')}", reply_markup=home_menu(lang))


async def open_language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    await query.edit_message_text(text=tr(lang, "lang_menu"), reply_markup=language_menu(lang))


async def choose_personal_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    if query.from_user:
        await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, mode="personal")
    context.user_data["active_mode"] = "personal"

    await query.edit_message_text(
        text=tr(lang, "personal_menu"),
        reply_markup=personal_menu(lang),
    )


async def choose_group_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    if query.from_user:
        await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, mode="group")
    context.user_data["active_mode"] = "group"

    await query.edit_message_text(
        text=f"{tr(lang, 'group_menu')}\n\n{tr(lang, 'target_setup_group')}",
        reply_markup=group_menu(lang),
    )


async def choose_channel_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)

    if query.from_user:
        await upsert_user_prefs(str(query.from_user.id), query.from_user.first_name, mode="channel")
    context.user_data["active_mode"] = "channel"

    await query.edit_message_text(
        text=f"{tr(lang, 'channel_menu')}\n\n{tr(lang, 'target_setup_channel')}",
        reply_markup=channel_menu(lang),
    )


async def manage_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.from_user:
        return

    lang = get_lang(context)
    mode = context.user_data.get("active_mode", "group")
    targets = await list_targets(str(query.from_user.id))

    if not targets:
        setup_text = tr(lang, "target_setup_channel") if mode == "channel" else tr(lang, "target_setup_group")
        back_menu = channel_menu(lang) if mode == "channel" else group_menu(lang)
        await query.edit_message_text(
            text=f"{setup_text}\n\n{tr(lang, 'target_none')}",
            reply_markup=back_menu,
        )
        return

    lines = [tr(lang, "target_list_title")]
    for t in targets:
        lines.append(f"- {t.chat_title} ({t.chat_type})")

    remove_entries = [(t.chat_id, t.chat_title or t.chat_id) for t in targets]
    await query.edit_message_text(
        text="\n".join(lines),
        reply_markup=remove_target_menu(lang, remove_entries),
    )


async def remove_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.from_user:
        return

    lang = get_lang(context)
    mode = context.user_data.get("active_mode", "group")
    chat_id = query.data.replace("target_remove_", "")
    await remove_target(str(query.from_user.id), chat_id)
    back_menu = channel_menu(lang) if mode == "channel" else group_menu(lang)

    await query.edit_message_text(
        text=tr(lang, "target_unlinked"),
        reply_markup=back_menu,
    )


async def link_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat or not update.message:
        return

    chat = update.effective_chat
    if chat.type not in ("group", "supergroup", "channel"):
        return

    owner_id = str(update.effective_user.id)
    title = chat.title or chat.username or str(chat.id)

    await add_or_update_target(owner_id, str(chat.id), title, chat.type)

    try:
        await update.message.reply_text("✅ Linked to your private setup successfully.")
    except Exception as exc:
        logger.warning("Unable to reply in target chat: %s", exc)


async def send_test_to_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.from_user:
        return

    lang = get_lang(context)
    mode = context.user_data.get("active_mode", "group")
    back_menu = channel_menu(lang) if mode == "channel" else group_menu(lang)
    targets = await list_targets(str(query.from_user.id))
    if not targets:
        await query.edit_message_text(text=tr(lang, "no_target_for_test"), reply_markup=back_menu)
        return

    for t in targets:
        try:
            await context.bot.send_message(chat_id=int(t.chat_id), text="📿 رسالة اختبار من مذكر الاذكار")
        except Exception as exc:
            logger.warning("Failed sending test to %s: %s", t.chat_id, exc)

    await query.edit_message_text(text=tr(lang, "test_sent"), reply_markup=back_menu)


async def config_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = get_lang(context)
    mode = context.user_data.get("active_mode", "personal")
    if mode == "channel":
        back_menu = channel_menu(lang)
    elif mode == "group":
        back_menu = group_menu(lang)
    else:
        back_menu = personal_menu(lang)
    await query.edit_message_text(text=tr(lang, "cfg_comming_soon"), reply_markup=back_menu)
