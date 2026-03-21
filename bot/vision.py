from __future__ import annotations

import base64
import io
import json
import logging

import anthropic
from PIL import Image

from bot.models import Leg, ParsedBet

logger = logging.getLogger(__name__)

MAX_DIMENSION = 800
JPEG_QUALITY = 85

SYSTEM_PROMPT = """You are a bet slip parser for Romanian betting apps (Superbet, Betano, Unibet, etc.). Analyze the provided bet slip image(s) and extract structured data.

Return ONLY valid JSON with this exact schema:
{
  "source": "bookmaker name or null",
  "bet_type": "single" | "multi" | "system" | null,
  "is_live": true | false,
  "legs": [
    {
      "event": "Team A - Team B",
      "selection": "the picked outcome (e.g. 1, X, 2, Over 2.5, Handicap -1.5, Team A winner)",
      "odds": 1.85 or null,
      "match_time": "YYYY-MM-DDTHH:MM" or null
    }
  ],
  "total_odds": 2.99 or null,
  "extractable": true | false
}

CRITICAL RULES for parsing Romanian bet slips:
- "event" MUST be the actual match/game (the teams or players), formatted as "Team A - Team B". Do NOT put the league, tournament, or sport name here. Romanian slips typically show the sport/league on one line and the teams on separate lines below it.
- "selection" is the specific bet placed — look for labels like "Câștigător", "Rezultat final", "Total goluri", "Handicap", etc. The selection is usually shown at the bottom of each leg alongside the odds. Include the chosen outcome (e.g. "Câștigător Parivision", "1", "Over 2.5").
- "is_live" should be true if the slip shows "LIVE", "In-Play", or similar.
- "match_time" should be the scheduled start time if visible. Use format YYYY-MM-DDTHH:MM. Interpret times as Romania time (Europe/Bucharest). If relative (e.g., "Astăzi, 20:35" or "maine"), resolve relative to today.
- "odds" per leg should be null if not individually visible.
- "total_odds" is the combined/total odds shown on the slip (often labeled "Cotă totală"). Null if not visible.
- For multi-leg bets, list each leg separately.
- Ignore any stake amount shown on the slip.
- Set "extractable" to false only if you cannot identify ANY event or selection from the image.
- Return ONLY the JSON object, no markdown fencing, no explanation."""


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
