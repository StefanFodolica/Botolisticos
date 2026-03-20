# CasaFodo Telegram Bet Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that parses bet slip screenshots via Claude Sonnet Vision, validates them, logs to Google Sheets, and supports admin approval flow with balance tracking.

**Architecture:** Single Python process using polling mode. Photos are resized/compressed locally before sending to Claude Sonnet. All state lives in Google Sheets (PENDING, MAIN, FLAGGED, BALANCE). No web server, no database, no background workers.

**Tech Stack:** Python 3.11+, python-telegram-bot, anthropic SDK, gspread, Pillow

**Spec:** `docs/superpowers/specs/2026-03-20-telegram-bet-bot-design.md`

---

## File Structure

```
bot/
├── __init__.py              # Empty
├── main.py                  # Entry point: builds Application, registers handlers, runs polling
├── handlers.py              # /bet and /approve command handlers, media group collector
├── vision.py                # Image resize/compress + Claude Sonnet API call + JSON parsing
├── validation.py            # Odds check, duplicate check, pre-match time check
├── sheets.py                # Google Sheets CRUD (PENDING, MAIN, FLAGGED, BALANCE)
└── models.py                # BetSlip, Leg, ParsedBet dataclasses
config.py                    # Loads env vars, exposes typed config object
tests/
├── __init__.py              # Empty
├── test_models.py           # Unit tests for data models
├── test_config.py           # Config loading tests
├── test_vision.py           # Image processing + API response parsing tests
├── test_validation.py       # All validation rule tests
├── test_sheets.py           # Sheets CRUD tests (mocked gspread)
└── test_handlers.py         # Command handler tests (mocked telegram + deps)
requirements.txt             # All dependencies pinned
.env.example                 # Template with all required env vars
```

---

### Task 1: Project Scaffolding & Config

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`
- Create: `bot/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create requirements.txt**

```
python-telegram-bot==21.10
anthropic==0.49.0
gspread==6.1.4
google-auth==2.38.0
Pillow==11.1.0
python-dotenv==1.0.1
pytest==8.3.4
```

- [ ] **Step 2: Create .env.example**

```
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
ANTHROPIC_API_KEY=your-anthropic-api-key
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service-account.json
GOOGLE_SHEET_ID=your-google-sheet-id
ADMIN_USER_IDS=123456789,987654321
```

- [ ] **Step 3: Create empty bot/__init__.py and tests/__init__.py**

Both files are empty.

- [ ] **Step 4: Write failing test for config**

```python
# tests/test_config.py
import os
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
```

- [ ] **Step 5: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 6: Implement config.py**

```python
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
```

- [ ] **Step 7: Run tests and verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .env.example config.py bot/__init__.py tests/__init__.py tests/test_config.py
git commit -m "feat: project scaffolding and config loading"
```

---

### Task 2: Data Models

**Files:**
- Create: `bot/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for data models**

```python
# tests/test_models.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.models'`

- [ ] **Step 3: Implement models.py**

```python
# bot/models.py
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
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_models.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add bot/models.py tests/test_models.py
git commit -m "feat: add data models (Leg, ParsedBet, BetSubmission)"
```

---

### Task 3: Image Processing

**Files:**
- Create: `bot/vision.py` (image processing part only — API call comes in Task 4)
- Create: `tests/test_vision.py`

- [ ] **Step 1: Write failing tests for image processing**

```python
# tests/test_vision.py
import io
from PIL import Image
from bot.vision import prepare_image_for_api


def _make_test_image(width: int, height: int) -> bytes:
    """Create a test JPEG image of given dimensions."""
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_large_image_resized_to_800px():
    raw = _make_test_image(2000, 1500)
    result = prepare_image_for_api(raw)
    img = Image.open(io.BytesIO(result))
    assert max(img.size) == 800
    assert img.size == (800, 600)


def test_small_image_not_upscaled():
    raw = _make_test_image(400, 300)
    result = prepare_image_for_api(raw)
    img = Image.open(io.BytesIO(result))
    assert img.size == (400, 300)


def test_tall_image_resized_by_height():
    raw = _make_test_image(600, 1200)
    result = prepare_image_for_api(raw)
    img = Image.open(io.BytesIO(result))
    assert max(img.size) == 800
    assert img.size == (400, 800)


def test_output_is_jpeg():
    raw = _make_test_image(1000, 1000)
    result = prepare_image_for_api(raw)
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"


def test_exif_stripped():
    raw = _make_test_image(1000, 1000)
    result = prepare_image_for_api(raw)
    img = Image.open(io.BytesIO(result))
    exif = img.getexif()
    assert len(exif) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vision.py -v -k "not test_exif"`
Expected: FAIL — `ImportError: cannot import name 'prepare_image_for_api'`

- [ ] **Step 3: Implement image processing in vision.py**

```python
# bot/vision.py
from __future__ import annotations

import io

from PIL import Image

MAX_DIMENSION = 800
JPEG_QUALITY = 85


def prepare_image_for_api(raw_bytes: bytes) -> bytes:
    """Resize, strip EXIF, and compress image for Vision API."""
    img = Image.open(io.BytesIO(raw_bytes))

    # Strip EXIF by copying pixel data to a new image
    img = img.convert("RGB")

    # Resize if larger than MAX_DIMENSION
    w, h = img.size
    if max(w, h) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(w, h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_vision.py -v -k "not test_exif"`
Expected: 4 passed

- [ ] **Step 5: Run all tests including EXIF**

Run: `python -m pytest tests/test_vision.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add bot/vision.py tests/test_vision.py
git commit -m "feat: image preprocessing (resize, EXIF strip, JPEG compress)"
```

---

### Task 4: Vision AI Parsing (Claude Sonnet)

**Files:**
- Modify: `bot/vision.py` — add `parse_bet_slip()` function
- Modify: `tests/test_vision.py` — add API response parsing tests

- [ ] **Step 1: Write failing tests for bet slip parsing**

Add to `tests/test_vision.py`:

```python
import json
from unittest.mock import MagicMock, patch
from bot.vision import parse_bet_slip, _build_vision_messages, _parse_response_json
from bot.models import ParsedBet


def test_parse_response_json_valid():
    raw_json = json.dumps({
        "source": "Superbet",
        "bet_type": "multi",
        "is_live": False,
        "legs": [
            {"event": "UTA - FCSB", "selection": "FCSB", "odds": 1.85, "match_time": "2026-03-21T18:00"},
            {"event": "Arsenal - Chelsea", "selection": "Peste 7.5", "odds": 1.62, "match_time": None},
        ],
        "total_odds": 2.997,
        "extractable": True,
    })
    result = _parse_response_json(raw_json)
    assert isinstance(result, ParsedBet)
    assert result.source == "Superbet"
    assert len(result.legs) == 2
    assert result.legs[0].odds == 1.85
    assert result.total_odds == 2.997
    assert result.is_live is False


def test_parse_response_json_not_extractable():
    raw_json = json.dumps({
        "source": None,
        "bet_type": None,
        "is_live": False,
        "legs": [],
        "total_odds": None,
        "extractable": False,
    })
    result = _parse_response_json(raw_json)
    assert result.extractable is False
    assert result.legs == []


def test_parse_response_json_live_bet():
    raw_json = json.dumps({
        "source": "Superbet",
        "bet_type": "single",
        "is_live": True,
        "legs": [
            {"event": "Dinamo - FCSB", "selection": "FCSB", "odds": 2.10, "match_time": None},
        ],
        "total_odds": 2.10,
        "extractable": True,
    })
    result = _parse_response_json(raw_json)
    assert result.is_live is True


def test_build_vision_messages_single_photo():
    photos = [b"fake-image-data"]
    context = ""
    messages = _build_vision_messages(photos, context)
    # Should have one message with image content block + text prompt
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content_blocks = messages[0]["content"]
    # At least one image block and one text block
    types = [b["type"] for b in content_blocks]
    assert "image" in types
    assert "text" in types


def test_build_vision_messages_multiple_photos():
    photos = [b"img1", b"img2", b"img3"]
    context = ""
    messages = _build_vision_messages(photos, context)
    content_blocks = messages[0]["content"]
    image_blocks = [b for b in content_blocks if b["type"] == "image"]
    assert len(image_blocks) == 3


def test_build_vision_messages_with_context():
    photos = [b"img"]
    context = "pe NAVI"
    messages = _build_vision_messages(photos, context)
    text_blocks = [b for b in messages[0]["content"] if b["type"] == "text"]
    combined_text = " ".join(b["text"] for b in text_blocks)
    assert "pe NAVI" in combined_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vision.py -v -k "parse_response or build_vision"`
Expected: FAIL — `ImportError: cannot import name 'parse_bet_slip'`

- [ ] **Step 3: Implement Vision API functions in vision.py**

Add to `bot/vision.py`:

```python
import base64
import json
import logging

import anthropic

from bot.models import Leg, ParsedBet

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a bet slip parser. Analyze the provided bet slip image(s) and extract structured data.

Return ONLY valid JSON with this exact schema:
{
  "source": "bookmaker name or null",
  "bet_type": "single" | "multi" | "system" | null,
  "is_live": true | false,
  "legs": [
    {
      "event": "Team A - Team B" or "Tournament Name",
      "selection": "the picked outcome",
      "odds": 1.85 or null,
      "match_time": "YYYY-MM-DDTHH:MM" or null
    }
  ],
  "total_odds": 2.99 or null,
  "extractable": true | false
}

Rules:
- Set "extractable" to false only if you cannot identify ANY event or selection from the image.
- "is_live" should be true if the slip shows indicators like "LIVE", "In-Play", or similar.
- "match_time" should be the scheduled kick-off/start time if visible on the slip. Use format YYYY-MM-DDTHH:MM. Interpret times as Romania time (Europe/Bucharest). If a date is relative (e.g., "maine"), resolve it relative to today.
- "odds" per leg should be null if not individually visible.
- "total_odds" is the combined/total odds shown on the slip. Null if not visible.
- For multi-leg bets, list each leg separately.
- Ignore any stake amount shown on the slip — the stake comes from the user's command.
- Return ONLY the JSON object, no markdown fencing, no explanation."""


def _build_vision_messages(
    prepared_photos: list[bytes], context: str
) -> list[dict]:
    """Build the messages array for the Anthropic API call."""
    content_blocks = []

    for photo in prepared_photos:
        b64 = base64.b64encode(photo).decode("utf-8")
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })

    from datetime import date
    today = date.today().isoformat()
    prompt_text = f"Today's date is {today}. Parse this bet slip and return the JSON."
    if context:
        prompt_text += f"\n\nAdditional context from the user: {context}"

    content_blocks.append({"type": "text", "text": prompt_text})

    return [{"role": "user", "content": content_blocks}]


def _parse_response_json(raw_text: str) -> ParsedBet:
    """Parse the JSON string from Sonnet into a ParsedBet."""
    # Strip markdown fencing if present
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    data = json.loads(text)

    legs = [
        Leg(
            event=leg["event"],
            selection=leg["selection"],
            odds=leg.get("odds"),
            match_time=leg.get("match_time"),
        )
        for leg in data.get("legs", [])
    ]

    return ParsedBet(
        source=data.get("source"),
        bet_type=data.get("bet_type"),
        is_live=data.get("is_live", False),
        legs=legs,
        total_odds=data.get("total_odds"),
        extractable=data.get("extractable", False),
    )


def parse_bet_slip(
    api_key: str,
    raw_photos: list[bytes],
    context: str = "",
) -> ParsedBet:
    """Send photos to Claude Sonnet Vision API and return parsed bet data."""
    prepared = [prepare_image_for_api(photo) for photo in raw_photos]
    messages = _build_vision_messages(prepared, context)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=messages,
    )

    raw_text = response.content[0].text
    return _parse_response_json(raw_text)
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_vision.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add bot/vision.py tests/test_vision.py
git commit -m "feat: Vision API integration (Sonnet bet slip parsing)"
```

---

### Task 5: Validation Logic

**Files:**
- Create: `bot/validation.py`
- Create: `tests/test_validation.py`

- [ ] **Step 1: Write failing tests for odds validation**

```python
# tests/test_validation.py
from datetime import datetime
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
    assert result is None  # None means valid


def test_odds_mismatch_flags():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
        Leg(event="C - D", selection="C", odds=3.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=10.0)  # should be 6.0
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result == "odds mismatch"


def test_odds_within_tolerance():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
        Leg(event="C - D", selection="C", odds=3.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=6.01)  # within 0.02
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result is None


def test_odds_check_skipped_when_leg_odds_missing():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
        Leg(event="C - D", selection="C", odds=None, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=10.0)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result is None  # can't check, so pass


def test_odds_check_skipped_when_total_missing():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time=None),
    ]
    parsed = _make_parsed(legs=legs, total_odds=None)
    result = validate_bet(parsed, user_id=1, username="test", timestamp=datetime.now(), recent_bets=[])
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_validation.py -v -k "odds"`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement odds validation**

```python
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
    # 1. Extractable check
    if not parsed.extractable:
        return "incomplete"

    # 2. Odds multiplication check
    reason = _check_odds(parsed)
    if reason:
        return reason

    # 3. Duplicate check
    reason = _check_duplicate(parsed, user_id, timestamp, recent_bets)
    if reason:
        return reason

    # 4. Pre-match time check
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
    """Check for duplicate: same user, same legs+odds, within 24h."""
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
    """Return sorted list of (event, selection) for comparison."""
    return sorted(
        (leg.event.strip().lower(), leg.selection.strip().lower())
        for leg in parsed.legs
    )


def _check_prematch_time(parsed: ParsedBet, message_time: datetime) -> str | None:
    """Flag pre-match bets where match time has already passed."""
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
```

- [ ] **Step 4: Run odds tests and verify they pass**

Run: `python -m pytest tests/test_validation.py -v -k "odds"`
Expected: 5 passed

- [ ] **Step 5: Add duplicate detection tests**

Add to `tests/test_validation.py`:

```python
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
        "user_id": 999,  # different user
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
        "timestamp": now - timedelta(hours=25),  # outside window
        "legs": [("a - b", "a wins")],
        "total_odds": 2.0,
    }]
    result = validate_bet(parsed, user_id=1, username="test", timestamp=now, recent_bets=recent)
    assert result is None
```

- [ ] **Step 6: Run duplicate tests**

Run: `python -m pytest tests/test_validation.py -v -k "duplicate"`
Expected: 3 passed

- [ ] **Step 7: Add pre-match time check tests**

Add to `tests/test_validation.py`:

```python
from datetime import timedelta

# --- Pre-match time check ---

def test_prematch_expired_flags():
    legs = [
        Leg(event="A - B", selection="A", odds=2.0, match_time="2026-03-20T14:00"),
    ]
    parsed = _make_parsed(legs=legs, total_odds=2.0, is_live=False)
    # Message sent at 15:00, match was at 14:00
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
```

- [ ] **Step 8: Run all validation tests**

Run: `python -m pytest tests/test_validation.py -v`
Expected: All 14 passed

- [ ] **Step 9: Commit**

```bash
git add bot/validation.py tests/test_validation.py
git commit -m "feat: validation rules (odds, duplicates, pre-match time)"
```

---

### Task 6: Google Sheets Integration

**Files:**
- Create: `bot/sheets.py`
- Create: `tests/test_sheets.py`

- [ ] **Step 1: Write failing tests for sheets module**

```python
# tests/test_sheets.py
from unittest.mock import MagicMock, patch, call
from datetime import datetime
from bot.sheets import SheetsClient


def _make_mock_client():
    """Create a SheetsClient with mocked gspread."""
    with patch("bot.sheets.gspread.service_account_from_dict") as mock_sa:
        mock_gc = MagicMock()
        mock_sa.return_value = mock_gc
        mock_spreadsheet = MagicMock()
        mock_gc.open_by_key.return_value = mock_spreadsheet

        mock_pending = MagicMock()
        mock_main = MagicMock()
        mock_flagged = MagicMock()
        mock_balance = MagicMock()

        def get_worksheet(name):
            return {
                "PENDING": mock_pending,
                "MAIN": mock_main,
                "FLAGGED": mock_flagged,
                "BALANCE": mock_balance,
            }[name]

        mock_spreadsheet.worksheet = get_worksheet

        client = SheetsClient(
            service_account_info={"type": "service_account"},
            sheet_id="test-sheet-id",
        )
        return client, mock_pending, mock_main, mock_flagged, mock_balance


def test_write_to_pending():
    client, mock_pending, _, _, _ = _make_mock_client()
    client.write_pending(
        date="20.03.2026",
        ora="14:32",
        parior="Georo",
        meci="Dinamo - FC Arges",
        pariu="Karamoko 3+",
        cota="4.10",
        miza="50.00 RON",
    )
    mock_pending.append_row.assert_called_once_with(
        ["20.03.2026", "14:32", "Georo", "Dinamo - FC Arges", "Karamoko 3+", "4.10", "50.00 RON"],
        value_input_option="USER_ENTERED",
    )


def test_write_to_flagged():
    client, _, _, mock_flagged, _ = _make_mock_client()
    client.write_flagged(
        date="20.03.2026",
        ora="14:32",
        parior="Georo",
        meci="Dinamo - FC Arges",
        pariu="Karamoko 3+",
        cota="4.10",
        miza="50.00 RON",
        motiv="odds mismatch",
    )
    mock_flagged.append_row.assert_called_once_with(
        ["20.03.2026", "14:32", "Georo", "Dinamo - FC Arges", "Karamoko 3+", "4.10", "50.00 RON", "odds mismatch"],
        value_input_option="USER_ENTERED",
    )


def test_get_all_pending():
    client, mock_pending, _, _, _ = _make_mock_client()
    mock_pending.get_all_values.return_value = [
        ["DATA", "ORA", "PARIOR", "Meci", "PARIU", "COTA", "MIZA"],  # header
        ["20.03.2026", "14:32", "Georo", "Dinamo - FC Arges", "Karamoko 3+", "4.10", "50.00 RON"],
    ]
    rows = client.get_all_pending()
    assert len(rows) == 1
    assert rows[0] == ["20.03.2026", "14:32", "Georo", "Dinamo - FC Arges", "Karamoko 3+", "4.10", "50.00 RON"]


def test_approve_moves_to_main_and_clears():
    client, mock_pending, mock_main, _, _ = _make_mock_client()
    mock_pending.get_all_values.return_value = [
        ["DATA", "ORA", "PARIOR", "Meci", "PARIU", "COTA", "MIZA"],
        ["20.03.2026", "14:32", "Georo", "Match", "Bet", "4.10", "50.00 RON"],
        ["20.03.2026", "15:00", "Daris", "Match2", "Bet2", "2.00", "25.00 RON"],
    ]

    rows = client.get_all_pending()
    for row in rows:
        client.write_main(row)

    assert mock_main.append_row.call_count == 2


def test_clear_pending():
    client, mock_pending, _, _, _ = _make_mock_client()
    mock_pending.get_all_values.return_value = [
        ["DATA", "ORA", "PARIOR", "Meci", "PARIU", "COTA", "MIZA"],
        ["20.03.2026", "14:32", "Georo", "Match", "Bet", "4.10", "50.00 RON"],
    ]
    client.clear_pending()
    # Should delete data rows but preserve header
    mock_pending.delete_rows.assert_called_once_with(2, 2)


def test_find_user_column_in_balance():
    client, _, _, _, mock_balance = _make_mock_client()
    # Row 1 has telegram user IDs
    mock_balance.row_values.return_value = ["", "111", "222", "333"]
    col = client.find_user_column(user_id=222)
    assert col == 3  # 1-indexed, column C


def test_find_user_column_not_found():
    client, _, _, _, mock_balance = _make_mock_client()
    mock_balance.row_values.return_value = ["", "111", "222"]
    col = client.find_user_column(user_id=999)
    assert col is None


def test_append_balance_transaction():
    client, _, _, _, mock_balance = _make_mock_client()
    mock_balance.row_values.return_value = ["", "111", "222"]
    # Column 2 values from row 7 downward
    mock_balance.col_values.return_value = ["111", "", "Daris", "-928", "0", "TRANZACTII", "-50", "-100", ""]
    client.append_balance_transaction(col=2, amount=-25.0)
    # Next empty cell after row 7 data: row 9 (values list index 8 is empty, that's row 9)
    mock_balance.update_cell.assert_called_once_with(9, 2, -25.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sheets.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement sheets.py**

```python
# bot/sheets.py
from __future__ import annotations

import json
import logging

import gspread

logger = logging.getLogger(__name__)

BALANCE_ID_ROW = 1
BALANCE_TRANSACTIONS_START_ROW = 7


class SheetsClient:
    def __init__(self, service_account_info: dict, sheet_id: str):
        gc = gspread.service_account_from_dict(service_account_info)
        spreadsheet = gc.open_by_key(sheet_id)
        self._pending = spreadsheet.worksheet("PENDING")
        self._main = spreadsheet.worksheet("MAIN")
        self._flagged = spreadsheet.worksheet("FLAGGED")
        self._balance = spreadsheet.worksheet("BALANCE")

    def write_pending(
        self, date: str, ora: str, parior: str, meci: str, pariu: str, cota: str, miza: str
    ) -> None:
        self._pending.append_row(
            [date, ora, parior, meci, pariu, cota, miza],
            value_input_option="USER_ENTERED",
        )

    def write_flagged(
        self, date: str, ora: str, parior: str, meci: str, pariu: str, cota: str, miza: str, motiv: str
    ) -> None:
        self._flagged.append_row(
            [date, ora, parior, meci, pariu, cota, miza, motiv],
            value_input_option="USER_ENTERED",
        )

    def write_main(self, row: list[str]) -> None:
        self._main.append_row(row, value_input_option="USER_ENTERED")

    def get_all_pending(self) -> list[list[str]]:
        all_rows = self._pending.get_all_values()
        if len(all_rows) <= 1:
            return []
        return all_rows[1:]  # skip header

    def clear_pending(self) -> None:
        all_rows = self._pending.get_all_values()
        if len(all_rows) <= 1:
            return
        self._pending.delete_rows(2, len(all_rows))

    def find_user_column(self, user_id: int) -> int | None:
        id_row = self._balance.row_values(BALANCE_ID_ROW)
        user_id_str = str(user_id)
        for i, cell_val in enumerate(id_row):
            if cell_val.strip() == user_id_str:
                return i + 1  # 1-indexed
        return None

    def append_balance_transaction(self, col: int, amount: float) -> None:
        col_values = self._balance.col_values(col)
        # Find first empty cell from TRANSACTIONS_START_ROW onward
        row = BALANCE_TRANSACTIONS_START_ROW
        for i in range(BALANCE_TRANSACTIONS_START_ROW - 1, len(col_values)):
            if col_values[i].strip() == "":
                row = i + 1  # 1-indexed
                break
        else:
            row = len(col_values) + 1
        self._balance.update_cell(row, col, amount)

    def find_column_by_name(self, parior_name: str) -> int | None:
        """Find a user's column by display name in BALANCE row 3."""
        name_row = self._balance.row_values(3)
        for i, name in enumerate(name_row):
            if name.strip().lower() == parior_name.strip().lower():
                return i + 1  # 1-indexed
        return None

    def get_recent_bets_for_duplicate_check(self) -> list[dict]:
        """Read recent PENDING + MAIN rows for duplicate detection."""
        rows = []
        for sheet in [self._pending, self._main]:
            all_rows = sheet.get_all_values()
            if len(all_rows) <= 1:
                continue
            for row in all_rows[1:]:
                if len(row) >= 7:
                    rows.append({
                        "date": row[0],
                        "parior": row[2],
                        "meci": row[3],
                        "pariu": row[4],
                        "total_odds": row[5],
                    })
        return rows

    def get_parior_name_for_user(self, user_id: int) -> str | None:
        """Get the display name from BALANCE row 3 for a user ID."""
        col = self.find_user_column(user_id)
        if col is None:
            return None
        name_row = self._balance.row_values(3)
        if col - 1 < len(name_row):
            return name_row[col - 1]
        return None
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_sheets.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add bot/sheets.py tests/test_sheets.py
git commit -m "feat: Google Sheets integration (PENDING, MAIN, FLAGGED, BALANCE)"
```

---

### Task 7: /bet Command Handler

**Files:**
- Create: `bot/handlers.py`
- Create: `tests/test_handlers.py`

- [ ] **Step 1: Write failing tests for command parsing**

```python
# tests/test_handlers.py
from bot.handlers import parse_bet_command


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handlers.py -v -k "parse"`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement command parsing**

```python
# bot/handlers.py
from __future__ import annotations

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

    # First part must be a positive number
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
            # Everything after amount is context
            context = " ".join(parts[1:])

    return amount, currency, context
```

- [ ] **Step 4: Run parsing tests and verify they pass**

Run: `python -m pytest tests/test_handlers.py -v -k "parse"`
Expected: 8 passed

- [ ] **Step 5: Write the full /bet handler**

Add to `bot/handlers.py`:

```python
async def handle_bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /bet command — parse photos, validate, write to sheets."""
    message = update.effective_message
    user = update.effective_user
    bot_data = context.bot_data
    sheets: SheetsClient = bot_data["sheets"]
    api_key: str = bot_data["anthropic_api_key"]
    admin_ids: list[int] = bot_data["admin_user_ids"]

    # Check user is registered
    user_col = sheets.find_user_column(user.id)
    if user_col is None:
        await message.reply_text("Nu esti inregistrat. Contacteaza adminul.")
        return

    # Parse command arguments
    cmd_text = message.text or message.caption or ""
    # Strip the /bet prefix
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
            photo_file = await message.photo[-1].get_file()  # highest res
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
        # Retry once
        try:
            parsed_bet = parse_bet_slip(api_key, photos, bet_context)
        except Exception as e2:
            logger.error(f"Vision API retry failed for user {user.id}: {e2}")
            sheets.write_flagged(
                date=msg_time.strftime("%d.%m.%Y"),
                ora=msg_time.strftime("%H:%M"),
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
    ora_str = msg_time.strftime("%H:%M")
    miza_str = f"{amount:.2f} {currency}"

    if parsed_bet.extractable:
        meci = "\n".join(leg.event for leg in parsed_bet.legs)
        pariu = "\n".join(leg.selection for leg in parsed_bet.legs)
        cota = str(parsed_bet.total_odds) if parsed_bet.total_odds else ""
    else:
        meci = ""
        pariu = ""
        cota = ""

    if motiv:
        # Flagged — silent write
        sheets.write_flagged(
            date=date_str, ora=ora_str, parior=parior_name,
            meci=meci, pariu=pariu, cota=cota, miza=miza_str, motiv=motiv,
        )
    else:
        # Valid — write to PENDING
        sheets.write_pending(
            date=date_str, ora=ora_str, parior=parior_name,
            meci=meci, pariu=pariu, cota=cota, miza=miza_str,
        )
        await message.reply_text("✅ Bilet inregistrat")


def _build_recent_bets_list(sheets: SheetsClient, user_id: int) -> list[dict]:
    """Build the recent_bets structure needed by validation.validate_bet()."""
    raw_rows = sheets.get_recent_bets_for_duplicate_check()
    parior_name = sheets.get_parior_name_for_user(user_id)  # fetch once
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
```

- [ ] **Step 6: Write the media group handler**

Add to `bot/handlers.py`:

```python
import asyncio

# Track media groups being collected: media_group_id -> list of photo bytes
_media_group_photos: dict[str, list[bytes]] = {}
_media_group_locks: dict[str, asyncio.Event] = {}


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

    # Schedule processing after a delay (wait for all photos to arrive)
    if group_id not in _media_group_locks:
        _media_group_locks[group_id] = asyncio.Event()
        # The first photo in the group triggers delayed processing
        context.job_queue.run_once(
            _process_media_group,
            when=2.0,  # 2 second delay
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
    _media_group_locks.pop(group_id, None)

    if not photos:
        return

    # Inject collected photos into the update and delegate to handle_bet
    # Store photos in bot_data temporarily
    context.bot_data[f"media_group_photos_{group_id}"] = photos
    await handle_bet(update, context)
```

- [ ] **Step 7: Run all handler tests**

Run: `python -m pytest tests/test_handlers.py -v`
Expected: All passed

- [ ] **Step 8: Commit**

```bash
git add bot/handlers.py tests/test_handlers.py
git commit -m "feat: /bet command handler with media group support"
```

---

### Task 8: /approve Command Handler

**Files:**
- Modify: `bot/handlers.py` — add `handle_approve()`
- Modify: `tests/test_handlers.py` — add approve tests

- [ ] **Step 1: Write failing tests for /approve**

Add to `tests/test_handlers.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from bot.handlers import _do_approve


def test_approve_extracts_miza_amount():
    from bot.handlers import _parse_miza
    assert _parse_miza("50.00 RON") == 50.0
    assert _parse_miza("12.50 EUR") == 12.5
    assert _parse_miza("100 RON") == 100.0


def test_approve_parses_miza_no_currency():
    from bot.handlers import _parse_miza
    assert _parse_miza("50.00") == 50.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_handlers.py -v -k "approve or miza"`
Expected: FAIL

- [ ] **Step 3: Implement /approve handler**

Add to `bot/handlers.py`:

```python
def _parse_miza(miza_str: str) -> float:
    """Extract numeric amount from MIZA string like '50.00 RON'."""
    parts = miza_str.strip().split()
    return float(parts[0])


async def handle_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /approve command — move PENDING to MAIN, update BALANCE."""
    user = update.effective_user
    message = update.effective_message
    admin_ids: list[int] = context.bot_data["admin_user_ids"]

    if user.id not in admin_ids:
        return  # silently ignore non-admins

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
            # Write to MAIN
            sheets.write_main(row)

            # Update BALANCE: find user column by parior name
            parior_name = row[2]  # PARIOR is column index 2 (0=DATA, 1=ORA, 2=PARIOR)
            miza_str = row[6]  # MIZA is column index 6

            # Find user column by display name
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

    # Clear PENDING
    try:
        sheets.clear_pending()
    except Exception as e:
        logger.error(f"Error clearing PENDING: {e}")
        errors.append(f"Eroare la stergerea PENDING: {str(e)}")

    reply = f"✅ {moved} bilete aprobate."
    if errors:
        reply += "\n\n⚠️ Probleme:\n" + "\n".join(errors)

    await message.reply_text(reply)
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `python -m pytest tests/test_handlers.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add bot/handlers.py tests/test_handlers.py
git commit -m "feat: /approve command handler with balance updates"
```

---

### Task 9: Main Entry Point

**Files:**
- Create: `bot/main.py`

- [ ] **Step 1: Implement main.py**

```python
# bot/main.py
from __future__ import annotations

import json
import logging

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

    # Load Google service account
    with open(cfg.google_service_account_json) as f:
        sa_info = json.load(f)

    sheets = SheetsClient(service_account_info=sa_info, sheet_id=cfg.google_sheet_id)

    app = ApplicationBuilder().token(cfg.telegram_bot_token).build()

    # Store shared deps in bot_data
    app.bot_data["sheets"] = sheets
    app.bot_data["anthropic_api_key"] = cfg.anthropic_api_key
    app.bot_data["admin_user_ids"] = cfg.admin_user_ids

    # Register handlers
    # /bet command with photo caption
    app.add_handler(CommandHandler("bet", handle_bet))

    # /approve command (admin only)
    app.add_handler(CommandHandler("approve", handle_approve))

    # Media group photos (for batched photo handling)
    app.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.GROUPS,
        handle_media_group_photo,
    ))

    logger.info("Bot starting in polling mode...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax and imports are correct**

Run: `python -c "import bot.main"`
Expected: No import errors (will fail on missing env vars at runtime, which is expected)

- [ ] **Step 3: Commit**

```bash
git add bot/main.py
git commit -m "feat: main entry point with polling setup"
```

---

### Task 10: Integration Testing & Deployment Setup

**Files:**
- Create: `Procfile` (for Railway)
- Create: `.gitignore`
- Modify: `requirements.txt` if needed

- [ ] **Step 1: Create .gitignore**

```
__pycache__/
*.pyc
.env
*.json
!.env.example
.venv/
.superpowers/
docs/
```

Note: `*.json` ignores service account JSON files. The `!.env.example` ensures the template is tracked.

- [ ] **Step 2: Create Procfile for Railway**

```
worker: python -m bot.main
```

Railway uses `Procfile` to know how to run your app. The `worker` process type means it runs continuously (no web port needed).

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add Procfile .gitignore
git commit -m "feat: Railway deployment config and gitignore"
```

- [ ] **Step 5: Final integration smoke test**

Create a `.env` file with real credentials and test manually:

```bash
cp .env.example .env
# Edit .env with real values
python -m bot.main
```

Send a `/bet 10` with a photo in the Telegram group. Verify:
1. Bot replies "✅ Bilet inregistrat"
2. Row appears in PENDING sheet
3. No errors in console

- [ ] **Step 6: Test /approve flow**

Send `/approve` from the admin account. Verify:
1. PENDING rows moved to MAIN
2. BALANCE column updated with negative stake
3. PENDING sheet cleared
4. Bot replies with count

- [ ] **Step 7: Commit any fixes from integration testing**

```bash
git add -A
git commit -m "fix: integration test fixes"
```

---

## Deployment Checklist

After all tasks are complete:

1. Create a GitHub repository
2. Push code to GitHub
3. Sign up for Railway (railway.app) and connect the GitHub repo
4. Set environment variables in Railway dashboard:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_SERVICE_ACCOUNT_JSON` (path or paste JSON content — may need to adjust config.py to handle inline JSON)
   - `GOOGLE_SHEET_ID`
   - `ADMIN_USER_IDS`
5. Deploy — Railway auto-builds and runs the Procfile
6. Verify bot responds in Telegram group
