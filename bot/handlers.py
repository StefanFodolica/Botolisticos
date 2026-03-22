# bot/handlers.py
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from bot.models import BetSubmission, ParsedBet
from bot.sheets import SheetsClient
from bot.validation import validate_bet, _normalize_legs
from bot.vision import parse_bet_slip

logger = logging.getLogger(__name__)

ROMANIA_TZ = ZoneInfo("Europe/Bucharest")
KNOWN_CURRENCIES = {"RON", "EUR", "USD", "GBP", "LEI"}


def parse_bet_command(text: str) -> tuple[float, str, str] | None:
    """Parse '/bet' arguments: amount [currency] [context].

    Returns (amount, currency, context) or None if invalid.
    """
    text = text.strip()
    if not text:
        return None

    parts = text.split(None, 2)

    try:
        amount = float(parts[0])
    except ValueError:
        return None

    if amount <= 0:
        return None

    currency = "RON"
    context = ""

    if len(parts) >= 2:
        if parts[1].upper() in KNOWN_CURRENCIES:
            currency = parts[1].upper()
            context = parts[2] if len(parts) >= 3 else ""
        else:
            context = " ".join(parts[1:])

    return amount, currency, context


def _parse_miza(miza_str: str) -> float:
    """Extract numeric amount from MIZA string like '50.00 RON'."""
    parts = miza_str.strip().split()
    return float(parts[0])


async def handle_bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /bet command — parse photos, validate, write to sheets."""
    message = update.effective_message
    user = update.effective_user
    bot_data = context.bot_data
    sheets: SheetsClient = bot_data["sheets"]
    api_key: str = bot_data["anthropic_api_key"]

    # Check user is registered
    user_col = sheets.find_user_column(user.id)
    if user_col is None:
        await message.reply_text("Nu esti inregistrat. Contacteaza adminul.")
        return

    # Parse command arguments
    cmd_text = message.text or message.caption or ""
    if cmd_text.startswith("/bet"):
        cmd_text = cmd_text[4:].strip()

    parsed_cmd = parse_bet_command(cmd_text)
    if parsed_cmd is None:
        await message.reply_text("Trimite biletul (foto) cu /bet [suma]")
        return

    amount, currency, bet_context = parsed_cmd

    # Collect photos — check media group cache first, then single photo, then reply
    photos = []
    media_group_key = f"media_group_photos_{message.media_group_id}" if message.media_group_id else None

    try:
        if media_group_key and media_group_key in context.bot_data:
            photos = context.bot_data.pop(media_group_key)
        elif message.photo:
            photo_file = await message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            photos.append(bytes(photo_bytes))
        elif message.reply_to_message and message.reply_to_message.photo:
            reply_msg = message.reply_to_message
            photo_file = await reply_msg.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            photos.append(bytes(photo_bytes))
    except Exception as e:
        logger.error(f"Photo download failed for user {user.id}: {e}")
        await message.reply_text("Nu am putut descarca poza, trimite din nou")
        return

    if not photos:
        await message.reply_text("Trimite biletul (foto) cu /bet [suma]")
        return

    # Get message timestamp in Romania time
    msg_time = message.date.astimezone(ROMANIA_TZ)

    # Get display name
    parior_name = sheets.get_parior_name_for_user(user.id)
    if not parior_name:
        parior_name = user.first_name or user.username or str(user.id)

    # Parse bet slip via Vision API
    try:
        parsed_bet = parse_bet_slip(api_key, photos, bet_context)
    except Exception as e:
        logger.error(f"Vision API error for user {user.id}: {e}")
        try:
            parsed_bet = parse_bet_slip(api_key, photos, bet_context)
        except Exception as e2:
            logger.error(f"Vision API retry failed for user {user.id}: {e2}")
            sheets.write_flagged(
                date=msg_time.strftime("%d.%m.%Y"),
                parior=parior_name,
                meci="",
                pariu="",
                cota="",
                miza=f"{amount:.2f} {currency}",
                motiv="API error",
            )
            await message.reply_text("Incearca din nou mai tarziu")
            return

    # Build recent bets list for duplicate check
    recent_bets = _build_recent_bets_list(sheets, user.id)

    # Validate
    motiv = validate_bet(
        parsed=parsed_bet,
        user_id=user.id,
        username=parior_name,
        timestamp=msg_time.replace(tzinfo=None),
        recent_bets=recent_bets,
    )

    # Format sheet data
    date_str = msg_time.strftime("%d.%m.%Y")
    miza_str = f"{amount:.2f}"

    if parsed_bet.extractable:
        meci = "\n".join(leg.event for leg in parsed_bet.legs)
        pariu = "\n".join(leg.selection for leg in parsed_bet.legs)
        cota = str(parsed_bet.total_odds) if parsed_bet.total_odds else ""
    else:
        meci = ""
        pariu = ""
        cota = ""

    if motiv:
        sheets.write_flagged(
            date=date_str, parior=parior_name,
            meci=meci, pariu=pariu, cota=cota, miza=miza_str, motiv=motiv,
        )
    else:
        sheets.write_pending(
            date=date_str, parior=parior_name,
            meci=meci, pariu=pariu, cota=cota, miza=miza_str,
        )
        await message.reply_text("✅ Bilet inregistrat")


def _build_recent_bets_list(sheets: SheetsClient, user_id: int) -> list[dict]:
    """Build the recent_bets structure needed by validation.validate_bet()."""
    raw_rows = sheets.get_recent_bets_for_duplicate_check()
    parior_name = sheets.get_parior_name_for_user(user_id)
    result = []
    for row in raw_rows:
        try:
            legs = [
                (event.strip().lower(), selection.strip().lower())
                for event, selection in zip(
                    row["meci"].split("\n"),
                    row["pariu"].split("\n"),
                )
            ]
            total_odds = float(row["total_odds"]) if row["total_odds"] else None
            dt = datetime.strptime(row["date"], "%d.%m.%Y")
            result.append({
                "user_id": user_id if row["parior"] == parior_name else -1,
                "timestamp": dt,
                "legs": sorted(legs),
                "total_odds": total_odds,
            })
        except (ValueError, KeyError):
            continue
    return result


# --- Media group handling ---

_media_group_photos: dict[str, list[bytes]] = {}
_media_group_captions: dict[str, str] = {}
_media_group_started: set[str] = set()


async def handle_media_group_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect photos from a media group, process when all arrive."""
    message = update.effective_message
    if not message.media_group_id or not message.photo:
        return

    group_id = message.media_group_id

    if group_id not in _media_group_photos:
        _media_group_photos[group_id] = []

    photo_file = await message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    _media_group_photos[group_id].append(bytes(photo_bytes))

    # Store caption if this photo has one (only first photo in group has caption)
    caption = message.caption or ""
    if caption and group_id not in _media_group_captions:
        _media_group_captions[group_id] = caption

    if group_id not in _media_group_started:
        _media_group_started.add(group_id)
        context.job_queue.run_once(
            _process_media_group,
            when=2.0,
            data={
                "group_id": group_id,
                "update": update,
            },
            name=f"media_group_{group_id}",
        )


async def _process_media_group(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a collected media group after the delay."""
    job_data = context.job.data
    group_id = job_data["group_id"]
    update = job_data["update"]

    photos = _media_group_photos.pop(group_id, [])
    caption = _media_group_captions.pop(group_id, "")
    _media_group_started.discard(group_id)

    if not photos:
        return

    # Only process if caption has /bet command
    if not caption or not caption.startswith("/bet"):
        return

    context.bot_data[f"media_group_photos_{group_id}"] = photos
    await handle_bet(update, context)


async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /approve command — move PENDING to MAIN, update BALANCE."""
    user = update.effective_user
    message = update.effective_message
    admin_ids: list[int] = context.bot_data["admin_user_ids"]

    if user.id not in admin_ids:
        return

    sheets: SheetsClient = context.bot_data["sheets"]

    try:
        pending_rows = sheets.get_all_pending()
    except Exception as e:
        logger.error(f"Sheets error in /approve: {e}")
        await message.reply_text("Eroare temporara, incearca din nou")
        return

    if not pending_rows:
        await message.reply_text("Nu sunt bilete in PENDING.")
        return

    errors = []
    moved = 0

    for row in pending_rows:
        try:
            sheets.write_main(row)

            parior_name = row[1]
            miza_str = row[5]

            col = sheets.find_column_by_name(parior_name)

            if col is not None:
                amount = _parse_miza(miza_str)
                sheets.append_balance_transaction(col, -amount)
            else:
                errors.append(f"Nu am gasit coloana pentru {parior_name}")

            moved += 1
        except Exception as e:
            logger.error(f"Error approving row {row}: {e}")
            errors.append(f"Eroare la {row[2]}: {str(e)}")

    try:
        sheets.clear_pending()
    except Exception as e:
        logger.error(f"Error clearing PENDING: {e}")
        errors.append(f"Eroare la stergerea PENDING: {str(e)}")

    reply = f"✅ {moved} bilete aprobate."
    if errors:
        reply += "\n\n⚠️ Probleme:\n" + "\n".join(errors)

    await message.reply_text(reply)
