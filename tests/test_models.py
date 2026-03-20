from bot.models import Leg, ParsedBet, BetSubmission


def test_leg_creation():
    leg = Leg(
        event="UTA - FCSB",
        selection="FCSB peste 5.5 cornere",
        odds=1.85,
        match_time="2026-03-21T18:00",
    )
    assert leg.event == "UTA - FCSB"
    assert leg.odds == 1.85
    assert leg.match_time == "2026-03-21T18:00"


def test_leg_without_match_time():
    leg = Leg(event="IEM Katowice", selection="NAVI to win", odds=None, match_time=None)
    assert leg.odds is None
    assert leg.match_time is None


def test_parsed_bet_creation():
    legs = [
        Leg(event="UTA - FCSB", selection="FCSB", odds=1.85, match_time=None),
        Leg(event="Arsenal - Chelsea", selection="Peste 7.5", odds=1.62, match_time=None),
    ]
    parsed = ParsedBet(
        source="Superbet",
        bet_type="multi",
        is_live=False,
        legs=legs,
        total_odds=29.29,
        extractable=True,
    )
    assert parsed.source == "Superbet"
    assert len(parsed.legs) == 2
    assert parsed.is_live is False


def test_parsed_bet_not_extractable():
    parsed = ParsedBet(
        source=None,
        bet_type=None,
        is_live=False,
        legs=[],
        total_odds=None,
        extractable=False,
    )
    assert parsed.extractable is False


def test_bet_submission_creation():
    from datetime import datetime

    sub = BetSubmission(
        user_id=12345,
        username="Georo",
        amount=50.0,
        currency="RON",
        context="",
        message_timestamp=datetime(2026, 3, 20, 14, 32),
        photo_data=[b"fake-image-bytes"],
    )
    assert sub.user_id == 12345
    assert sub.amount == 50.0
    assert sub.currency == "RON"


def test_bet_submission_default_currency():
    from datetime import datetime

    sub = BetSubmission(
        user_id=12345,
        username="Georo",
        amount=50.0,
        currency="RON",
        context="pe NAVI",
        message_timestamp=datetime(2026, 3, 20, 14, 32),
        photo_data=[],
    )
    assert sub.context == "pe NAVI"
