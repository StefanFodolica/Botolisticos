# config.py
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    anthropic_api_key: str
    google_service_account_json: str
    google_sheet_id: str
    admin_user_ids: list[int]

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
            anthropic_api_key=_require_env("ANTHROPIC_API_KEY"),
            google_service_account_json=_require_env("GOOGLE_SERVICE_ACCOUNT_JSON"),
            google_sheet_id=_require_env("GOOGLE_SHEET_ID"),
            admin_user_ids=[
                int(uid.strip())
                for uid in _require_env("ADMIN_USER_IDS").split(",")
            ],
        )
