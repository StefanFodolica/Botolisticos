from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Leg:
    event: str
    selection: str
    odds: float | None
    match_time: str | None


@dataclass
class ParsedBet:
    source: str | None
    bet_type: str | None
    is_live: bool
    legs: list[Leg]
    total_odds: float | None
    extractable: bool


@dataclass
class BetSubmission:
    user_id: int
    username: str
    amount: float
    currency: str
    context: str
    message_timestamp: datetime
    photo_data: list[bytes]
