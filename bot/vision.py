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

PRIORITY: If a bet cart/slip is visible at the bottom of the screen (showing "Cotă totală", "Miza", "Pariază acum", etc.), use it as your PRIMARY source. The bet cart is the most accurate summary — it lists each selected bet with match name, market, selection, and odds. Extract legs ONLY from the bet cart and ignore the matches list above it.

If there is NO bet cart (e.g. a confirmed/placed bet slip or a dedicated slip view), then extract from the slip directly.

For each leg:
- "event" = the match (teams/players) formatted as "Team A - Team B". NEVER put league/tournament/sport names here.
- "selection" MUST include the FULL market name AND the chosen outcome together. Examples:
  - "Total cornere Sub 9.5" (not just "Sub 9.5")
  - "Total goluri AC Milan Peste 2.5" (not just "Peste 2.5")
  - "Final 1" (not just "1")
  - "Câștigător Parivision"
  - "Handicap -1.5"
  The market name provides essential context — "Sub 9.5" alone is meaningless without knowing it refers to corners, goals, cards, etc.
- "odds" = the numeric odds for this leg. In the bet cart, odds are shown next to each selection. For Bet Builder bets, individual leg odds may not be visible — set to null.

Other rules:
- For Bet Builder / Same Game Multi bets: create a SEPARATE leg for each selection, all sharing the same event. Set bet_type to "system".
- For regular multi bets across different matches: one leg per match.
- "total_odds" = the combined odds (labeled "Cotă totală" or "Cotă"). For single bets, this equals the leg odds.
- "is_live" = true if the slip shows "LIVE", "In-Play", "Repriza", or a running match clock.
- "match_time" = scheduled start time if visible (format YYYY-MM-DDTHH:MM, Romania time). Resolve relative dates ("Astăzi", "maine") relative to today.
- Ignore any stake/miza amount shown on the slip.
- Set "extractable" to false only if you cannot identify ANY event or selection.
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
