# bot/main.py
from __future__ import annotations

import json
import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from config import Config
from bot.handlers import handle_bet, handle_approve, handle_media_group_photo
from bot.sheets import SheetsClient

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    cfg = Config.from_env()

    # Load Google service account (file path locally, raw JSON on Railway)
    raw = cfg.google_service_account_json
    if raw.strip().startswith("{"):
        sa_info = json.loads(raw)
    else:
        with open(raw) as f:
            sa_info = json.load(f)

    sheets = SheetsClient(service_account_info=sa_info, sheet_id=cfg.google_sheet_id)

    app = ApplicationBuilder().token(cfg.telegram_bot_token).build()

    # Store shared deps in bot_data
    app.bot_data["sheets"] = sheets
    app.bot_data["anthropic_api_key"] = cfg.anthropic_api_key
    app.bot_data["admin_user_ids"] = cfg.admin_user_ids

    # Register handlers
    app.add_handler(CommandHandler("bet", handle_bet))
    app.add_handler(CommandHandler("approve", handle_approve))
    # Handle /bet sent as a photo caption (e.g., photo with "/bet 50")
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.CaptionRegex(r"^/bet\b"),
        handle_bet,
    ))
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.GROUPS,
        handle_media_group_photo,
    ))

    # Debug: log ALL incoming updates
    async def debug_log(update: Update, context) -> None:
        logger.info(f"DEBUG update received: {update}")

    app.add_handler(MessageHandler(filters.ALL, debug_log), group=99)

    logger.info("Bot starting in polling mode...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
