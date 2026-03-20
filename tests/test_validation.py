# tests/test_validation.py
from datetime import datetime, timedelta
from bot.models import Leg, ParsedBet
from bot.validation import validate_bet


def _make_parsed(
    legs=None, total_odds=None, is_live=False, extractable=True
):
    """Helper to create a ParsedBet for testing."""
    return ParsedBet(
        source="Superbet",
        bet_type="multi" if legs and len(legs) > 1 else "single",
        is_live=is_live,
        legs=legs or [],
        total_odds=total_odds,
        extractable=extractable,
    )


# --- Odds validation ---

def test_valid_odds_multiplication():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
        Leg(event="C - D", selection="C", odds=3.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=6.0)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result is None


def test_odds_mismatch_flags():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
        Leg(event="C - D", selection="C", odds=3.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=10.0)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result == "odds mismatch"


def test_odds_within_tolerance():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
        Leg(event="C - D", selection="C", odds=3.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=6.01)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result is None


def test_odds_check_skipped_when_leg_odds_missing():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
        Leg(event="C - D", selection="C", odds=None, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=10.0)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result is None


def test_odds_check_skipped_when_total_missing():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=None)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result is None


# --- Duplicate detection ---

def test_duplicate_detected():
    legs = [
        Leg(event="A - B", selection="A wins", odds=2.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=2.0)
    now = datetime.now()
    recent = [{
        "user_id": 1,
        "timestamp": now - timedelta(hours=1),
        "legs": [("a - b", "a wins")],
        "total_odds": 2.0,
    }]
    result = validate_bet(parsed, user_id=1, username="test", timestamp=now, recent_bets=recent)
    assert result == "duplicate"


def test_no_duplicate_different_user():
    legs = [
        Leg(event="A - B", selection="A wins", odds=2.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=2.0)
    now = datetime.now()
    recent = [{
        "user_id": 999,
        "timestamp": now - timedelta(hours=1),
        "legs": [("a - b", "a wins")],
        "total_odds": 2.0,
    }]
    result = validate_bet(parsed, user_id=1, username="test", timestamp=now, recent_bets=recent)
    assert result is None


def test_no_duplicate_outside_24h():
    legs = [
        Leg(event="A - B", selection="A wins", odds=2.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=2.0)
    now = datetime.now()
    recent = [{
        "user_id": 1,
        "timestamp": now - timedelta(hours=25),
        "legs": [("a - b", "a wins")],
        "total_odds": 2.0,
    }]
    result = validate_bet(parsed, user_id=1, username="test", timestamp=now, recent_bets=recent)
    assert result is None


# --- Pre-match time check ---

def test_prematch_expired_flags():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time="2026-03-20T14:00"),
    ]
    parsed = _make_parsed(legs=legs, total_odds=2.0, is_live=False)
    msg_time = datetime(2026, 3, 20, 15, 0)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=msg_time, recent_bets=[])
    assert result == "pre-match expired"


def test_prematch_valid_future_match():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time="2026-03-20T18:00"),
    ]
    parsed = _make_parsed(legs=legs, total_odds=2.0, is_live=False)
    msg_time = datetime(2026, 3, 20, 15, 0)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=msg_time, recent_bets=[])
    assert result is None


def test_live_bet_skips_time_check():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time="2026-03-20T14:00"),
    ]
    parsed = _make_parsed(legs=legs, total_odds=2.0, is_live=True)
    msg_time = datetime(2026, 3, 20, 15, 0)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=msg_time, recent_bets=[])
    assert result is None


def test_prematch_no_time_skips_check():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=2.0, is_live=False)
    msg_time = datetime(2026, 3, 20, 15, 0)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=msg_time, recent_bets=[])
    assert result is None


def test_incomplete_bet_flags():
    parsed = _make_parsed(extractable=False)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result == "incomplete"
