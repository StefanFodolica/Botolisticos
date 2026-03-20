# tests/test_config.py
import pytest


def test_config_loads_all_required_fields(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "/path/to/sa.json")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-123")
    monkeypatch.setenv("ADMIN_USER_IDS", "111,222")

    from config import Config
    cfg = Config.from_env()

    assert cfg.telegram_bot_token == "test-token"
    assert cfg.anthropic_api_key == "test-api-key"
    assert cfg.google_service_account_json == "/path/to/sa.json"
    assert cfg.google_sheet_id == "sheet-123"
    assert cfg.admin_user_ids == [111, 222]


def test_config_raises_on_missing_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "/path")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet")
    monkeypatch.setenv("ADMIN_USER_IDS", "111")

    from config import Config
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Config.from_env()


def test_config_single_admin_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "/p")
    monkeypatch.setenv("GOOGLE_SHEET_ID", "s")
    monkeypatch.setenv("ADMIN_USER_IDS", "999")

    from config import Config
    cfg = Config.from_env()
    assert cfg.admin_user_ids == [999]
