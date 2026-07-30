from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from i18n import t
from keyboards import main_menu_keyboard
from database import get_session, UserRepository


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user.id, user.username, user.first_name)
        lang = db_user.language or "en"

        if db_user.onboarding_complete:
            await update.message.reply_text(
                t("welcome", lang),
                reply_markup=main_menu_keyboard(lang),
            )
        else:
            context.user_data["onboarding"] = {}
            await update.message.reply_text(
                t("welcome", lang) + "\n\n" + t("select_language", lang),
                reply_markup=main_menu_keyboard(lang),
            )
        session.commit()
    except Exception as e:
        session.rollback()
        await update.message.reply_text(t("general_error", "en"))
    finally:
        session.close()


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user.id, user.username, user.first_name)
        lang = db_user.language or "en"
        await update.message.reply_text(
            t("main_menu", lang),
            reply_markup=main_menu_keyboard(lang),
        )
    finally:
        session.close()


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.settings import show_status
    await show_status(update, context)


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user.id, user.username, user.first_name)
        UserRepository.update(session, db_user, onboarding_complete=False)
        session.commit()
        await update.message.reply_text(t("paused", db_user.language))
    except Exception as e:
        session.rollback()
    finally:
        session.close()


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = get_session()
    try:
        db_user = UserRepository.get_or_create(session, user.id, user.username, user.first_name)
        UserRepository.update(session, db_user, onboarding_complete=True)
        session.commit()
        await update.message.reply_text(t("resumed", db_user.language))
    except Exception as e:
        session.rollback()
    finally:
        session.close()


def register_start_handlers(application):
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("settings", menu_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("help", menu_command))