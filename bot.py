import os
import sys
import logging
import asyncio

from telegram.ext import Application

from config import TELEGRAM_BOT_TOKEN, PORT, WEBHOOK_MODE, HEROKU_APP_NAME
from database import init_db
from handlers import register_all_handlers
from services.dispatcher import start_dispatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _get_webhook_url():
    if HEROKU_APP_NAME:
        return f"https://{HEROKU_APP_NAME}.herokuapp.com/{TELEGRAM_BOT_TOKEN}"
    heroku_app = os.environ.get("HEROKU_APP_NAME", "")
    if heroku_app:
        return f"https://{heroku_app}.herokuapp.com/{TELEGRAM_BOT_TOKEN}"
    return None


async def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set!")
        sys.exit(1)

    logger.info("Initializing database...")
    init_db()

    logger.info("Building bot application...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    register_all_handlers(app)

    await app.initialize()
    await app.start()

    logger.info("Starting athkar dispatcher...")
    dispatcher = await start_dispatcher(app)

    is_webhook = WEBHOOK_MODE or bool(os.environ.get("DYNO"))
    webhook_url = _get_webhook_url()

    if is_webhook and webhook_url:
        logger.info(f"Starting webhook on port {PORT} -> {webhook_url}")
        await app.bot.set_webhook(url=webhook_url)
        await app.updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=webhook_url,
        )
        logger.info("Webhook server running")
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await app.bot.delete_webhook()
    else:
        logger.info("Starting polling mode...")
        await app.updater.start_polling()
        logger.info("Bot is polling...")
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass

    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)