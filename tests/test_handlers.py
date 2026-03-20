# tests/test_handlers.py
from bot.handlers import parse_bet_command, _parse_miza


def test_parse_simple_amount():
    amount, currency, context = parse_bet_command("50")
    assert amount == 50.0
    assert currency == "RON"
    assert context == ""


def test_parse_amount_with_currency():
    amount, currency, context = parse_bet_command("50 EUR")
    assert amount == 50.0
    assert currency == "EUR"
    assert context == ""


def test_parse_amount_with_context():
    amount, currency, context = parse_bet_command("10 pe NAVI")
    assert amount == 10.0
    assert currency == "RON"
    assert context == "pe NAVI"


def test_parse_amount_with_currency_and_context():
    amount, currency, context = parse_bet_command("25 EUR pe FCSB")
    assert amount == 25.0
    assert currency == "EUR"
    assert context == "pe FCSB"


def test_parse_decimal_amount():
    amount, currency, context = parse_bet_command("12.50")
    assert amount == 12.5
    assert currency == "RON"
    assert context == ""


def test_parse_no_amount():
    result = parse_bet_command("")
    assert result is None


def test_parse_invalid_amount():
    result = parse_bet_command("abc")
    assert result is None


def test_parse_negative_amount():
    result = parse_bet_command("-50")
    assert result is None


def test_approve_extracts_miza_amount():
    assert _parse_miza("50.00 RON") == 50.0
    assert _parse_miza("12.50 EUR") == 12.5
    assert _parse_miza("100 RON") == 100.0


def test_approve_parses_miza_no_currency():
    assert _parse_miza("50.00") == 50.0
