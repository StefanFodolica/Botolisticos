# bot/validation.py
from __future__ import annotations

import math
from datetime import datetime, timedelta

from bot.models import ParsedBet

ODDS_TOLERANCE = 0.02


def validate_bet(
    parsed: ParsedBet,
    user_id: int,
    username: str,
    timestamp: datetime,
    recent_bets: list[dict],
) -> str | None:
    """Validate a parsed bet. Returns None if valid, or a MOTIV string if flagged."""
    if not parsed.extractable:
        return "incomplete"

    reason = _check_odds(parsed)
    if reason:
        return reason

    reason = _check_duplicate(parsed, user_id, timestamp, recent_bets)
    if reason:
        return reason

    reason = _check_prematch_time(parsed, timestamp)
    if reason:
        return reason

    return None


def _check_odds(parsed: ParsedBet) -> str | None:
    if parsed.total_odds is None:
        return None
    if not parsed.legs:
        return None
    if any(leg.odds is None for leg in parsed.legs):
        return None

    calculated = math.prod(leg.odds for leg in parsed.legs)
    if abs(calculated - parsed.total_odds) > ODDS_TOLERANCE:
        return "odds mismatch"
    return None


def _check_duplicate(
    parsed: ParsedBet,
    user_id: int,
    timestamp: datetime,
    recent_bets: list[dict],
) -> str | None:
    cutoff = timestamp - timedelta(hours=24)
    current_legs = _normalize_legs(parsed)
    current_odds = parsed.total_odds

    for bet in recent_bets:
        if bet["user_id"] != user_id:
            continue
        if bet["timestamp"] < cutoff:
            continue
        if bet["legs"] == current_legs and bet["total_odds"] == current_odds:
            return "duplicate"

    return None


def _normalize_legs(parsed: ParsedBet) -> list[tuple[str, str]]:
    return sorted(
        ((leg.event or "").strip().lower(), (leg.selection or "").strip().lower())
        for leg in parsed.legs
    )


def _check_prematch_time(parsed: ParsedBet, message_time: datetime) -> str | None:
    if parsed.is_live:
        return None

    for leg in parsed.legs:
        if leg.match_time is None:
            continue
        try:
            match_dt = datetime.fromisoformat(leg.match_time)
            if match_dt < message_time:
                return "pre-match expired"
        except (ValueError, TypeError):
            continue

    return None
