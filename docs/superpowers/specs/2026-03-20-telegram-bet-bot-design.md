# CasaFodo — Telegram Bet Slip Bot Design Spec

## Overview

A Telegram bot for a private betting group that monitors for bet slip screenshots submitted via `/bet [amount]` command, uses Claude Sonnet Vision API to parse bet slip contents (matches, selections, odds), validates the data, and logs everything to Google Sheets. Photos are preserved on Google Drive. An admin approval flow ensures only validated bets reach the main ledger, with automatic balance tracking per user.

## Target Scale

- Current: ~5-10 users
- Target: 10-30 users
- Volume: ~14 bets/day (~425/month)

## Architecture

```
TELEGRAM GROUP
    │
    │  polling (python-telegram-bot)
    ▼
PYTHON BOT (Railway, ~$5/mo)
    ├── main.py         — entry point, polling loop
    ├── handlers.py     — /bet and /approve command handlers
    ├── vision.py       — image resize/compress + Claude Sonnet API
    ├── validation.py   — odds check, duplicate detection
    ├── sheets.py       — Google Sheets CRUD
    ├── drive.py        — Google Drive photo upload
    ├── models.py       — BetSlip, Leg dataclasses
    └── config.py       — env vars loading
    │
    ├──► CLAUDE SONNET API  (image parsing, ~$4-6/mo)
    ├──► GOOGLE SHEETS      (PENDING, MAIN, FLAGGED, BALANCE)
    └──► GOOGLE DRIVE       (daily photo backup)
```

### Key Architecture Decisions

- **Polling, not webhooks** — simplest to deploy, no public URL or HTTPS needed. `application.run_polling()` handles the loop. Latency of 1-2 sec is irrelevant for this use case.
- **No buffer system** — every bet submission requires `/bet [amount]` as a photo caption or as a reply to a photo. Eliminates complexity of tracking unclaimed photos in a chatty group.
- **Single Python process** — no web server, no background workers, no task queues. One process polls Telegram, processes bets synchronously, writes to Sheets/Drive.

## Bet Input Methods

| Scenario | Handling |
|----------|----------|
| Photo(s) with `/bet 50` caption | Process immediately |
| Media group with `/bet 50` on first photo | Collect all photos (~2 sec delay for Telegram to deliver all updates via `media_group_id`), then process as one bet |
| Reply to someone's photo with `/bet 25` | Replier is logged as the bettor |
| `/bet` with no photo context | Bot replies: "Trimite biletul (foto) cu /bet [suma]" |

### Command Parsing

`/bet [amount] [currency?] [optional context]`

- Amount is required, must be a positive number
- Currency is optional, defaults to RON. Other currencies stored as-is, no conversion
- Text after the amount is optional context for non-standard screenshots (e.g., `/bet 10 pe NAVI`)

## Bet Processing Pipeline

When a user sends `/bet 50` with photos:

1. **Handler** — extracts amount, optional currency (default RON), optional context text, all attached photos
2. **Download photos** — fetches from Telegram API at highest resolution
3. **Upload originals to Google Drive** — saved to daily folder (e.g., `2026-03-20/`) as `{username}_{timestamp}.jpg`. Full resolution preserved for evidence.
4. **Resize & compress for Vision API** — scale to ~800px longest side, strip EXIF metadata, re-encode JPEG at 85% quality
5. **Send to Claude Sonnet** — all photos batched in one API request with a structured prompt requesting JSON output
6. **Validate** — odds multiplication check, duplicate check
7. **Write to Google Sheets** — valid → PENDING sheet, invalid → FLAGGED sheet (with reason)
8. **Reply in chat** — valid: "✅ Bilet inregistrat" / flagged: silent / no photo: error message

For reply-to-photo: same flow, but the replier is logged as the bettor and photos come from the replied-to message.

## Vision AI Parsing

### Model & Cost Optimization

- **Model:** Claude Sonnet (via Anthropic API)
- **Image preprocessing:** resize to ~800px longest side, strip EXIF, JPEG 85% quality
- **Batching:** all photos from a single bet sent in one API request
- **Prompt caching:** system prompt cached across requests for reduced token cost
- **Estimated cost:** ~$4-6/month at current volume

### Prompt Design

The Vision prompt asks Sonnet to return structured JSON:

```json
{
  "source": "Superbet",
  "bet_type": "multi",
  "legs": [
    {
      "event": "UTA - FCSB",
      "selection": "FCSB peste 5.5 cornere",
      "odds": 1.85
    },
    {
      "event": "Arsenal - Chelsea",
      "selection": "Peste 7.5 cornere",
      "odds": 1.62
    }
  ],
  "total_odds": 29.29,
  "extractable": true
}
```

### Supported Input Types

- Standard bookmaker bet slips (primarily Superbet)
- Market selection screens
- Bet history views
- Bet builders / same-game multis
- Any sport or esport (football, tennis, CS2, LoL, Valorant, etc.)
- Any language on the slip (Romanian, English, mixed)
- Live bets (allowed, no time validation)

### Non-Standard Sources

Social media screenshots, tournament graphics, and other informal sources: the Vision AI extracts whatever is visible. If insufficient data can be extracted, the bet is flagged with MOTIV "incomplete". The optional context text from the `/bet` command provides additional info (e.g., `/bet 10 pe NAVI`).

## Validation Rules

All validation is silent — failures go to FLAGGED sheet, no message in group chat.

1. **Odds multiplication check** — where per-leg odds are visible, multiply all leg odds and compare to total odds. Tolerance: ±0.02. Mismatch → FLAGGED with MOTIV "odds mismatch".
2. **Duplicate check** — same user + same legs (events + selections) + same odds within 24 hours → FLAGGED with MOTIV "duplicate".
3. **Incomplete extraction** — Vision AI can't extract meaningful event/selection data → FLAGGED with MOTIV "incomplete".

## Google Sheets Structure

One Google Sheets document with 4 sheets.

### PENDING Sheet

Bot writes here. Admin reviews and curates (deletes invalid rows). `/approve` clears it.

| DATA | PARIOR | Meci | PARIU | COTA | MIZA |
|------|--------|------|-------|------|------|

### MAIN Sheet

Approved bets. Same 6 columns + STATUS + CASTIG. Bot writes the 6 columns only. STATUS and CASTIG are manual/formula — bot never touches them.

| DATA | PARIOR | Meci | PARIU | COTA | MIZA | STATUS | CASTIG |
|------|--------|------|-------|------|------|--------|--------|

### FLAGGED Sheet

Silent failures. Same 6 columns + MOTIV (reason for flagging).

| DATA | PARIOR | Meci | PARIU | COTA | MIZA | MOTIV |
|------|--------|------|-------|------|------|-------|

### Column Format

**Single bet:**
```
DATA:   01.03.2026
PARIOR: Georo
Meci:   Dinamo - FC Arges
PARIU:  Karamoko 3+ pe poarta, 1 castiga
COTA:   4.10
MIZA:   50.00 RON
```

**Multi-leg bet** (newlines within Meci and PARIU cells):
```
DATA:   01.03.2026
PARIOR: Foitos
Meci:   UTA - FCSB
        Arsenal - Chelsea
        Dinamo - FC Arges
PARIU:  FCSB peste 5.5 cornere
        Peste 7.5 cornere
        Peste 6.5 cornere
COTA:   29.29
MIZA:   20.00 RON
```

**Informal bet (social media, esports):**
```
DATA:   20.03.2026
PARIOR: Alex
Meci:   IEM Katowice 2026
PARIU:  NAVI to win
COTA:   (blank — admin fills manually)
MIZA:   10.00 RON
```

- COTA is always total/combined odds. Blank if odds aren't visible in the image.
- MIZA includes currency. Default RON. Other currencies stored as-is.
- Date format: DD.MM.YYYY

### BALANCE Sheet

Existing layout (preserved):

| Row | Col A | Col B (User 1) | Col C (User 2) | ... |
|-----|-------|-----------------|-----------------|-----|
| 1 | (Telegram user IDs — hidden mapping row, new) | @tg_id_1 | @tg_id_2 | ... |
| 2 | (empty) | | | |
| 3 | Parior | Daris | Georo | ... |
| 4 | Balance | (formula) | (formula) | ... |
| 5 | Free bets | (manual) | (manual) | ... |
| 6 | TRANZACTII | (merged label row) | | |
| 7+ | | -50 | +100 | ... |

- Row 1: Telegram user IDs for bot mapping (admin populates once per user)
- Row 3: Display names (column headers)
- Row 4: Balance formula (sum of transactions)
- Row 5: Free bets (manually managed)
- Row 7+: Transaction amounts (signed numbers, no descriptions)

The bot finds a user's column by matching their Telegram user ID to Row 1, then appends the stake as a negative number to the next empty cell in that column from Row 7 downward.

## Commands

| Command | Scope | Description |
|---------|-------|-------------|
| `/bet [amount] [currency?] [context?]` | All users | Submit a bet — photo caption or reply to a photo |
| `/approve` | Admin only | Move all PENDING → MAIN, deduct stakes from BALANCE |

Admin identified by Telegram user ID configured in environment variables.

## /approve Flow

1. Read all rows from PENDING sheet
2. Append all rows to MAIN sheet (6 columns only — STATUS and CASTIG left empty for admin)
3. For each row: find PARIOR's column in BALANCE (via Row 1 ID mapping), append negative MIZA amount to next empty cell in that column
4. Clear PENDING sheet

No validation or reformatting — admin has already ensured PENDING contents are correct.

## Bot Chat Behavior

| Scenario | Bot response |
|----------|-------------|
| Valid bet parsed | "✅ Bilet inregistrat" |
| Flagged bet | Silent — writes to FLAGGED sheet only |
| `/bet` with no photo | "Trimite biletul (foto) cu /bet [suma]" |
| `/bet` from unknown user (not in BALANCE Row 1) | "Nu esti inregistrat. Contacteaza adminul." |
| All other messages | Bot stays completely silent |

## Photo Storage (Google Drive)

- Bot downloads every submitted photo at full resolution from Telegram API
- Uploads originals to Google Drive in daily folders (e.g., `2026-03-20/`)
- Naming: `{username}_{timestamp}.jpg`
- Full resolution preserved for evidence
- Compressed copies (800px, 85% JPEG) used only for Vision API, not stored

## Error Handling

Simple approach — one retry, then fail gracefully:

| Failure | Behavior |
|---------|----------|
| Claude API error | Retry once. If still failing, flag bet with MOTIV "API error", reply "Incearca din nou mai tarziu" |
| Google Sheets API error | Retry once. Log error, reply "Eroare temporara, incearca din nou" |
| Google Drive upload fails | Don't block bet processing. Log error, continue with parsing and Sheets write |
| Photo download fails | Reply "Nu am putut descarca poza, trimite din nou" |
| Unhandled exception | Catch at top level, log, don't crash the polling loop |

No retry queues or dead letter systems. If something fails, the user resubmits.

## Tech Stack

- **Language:** Python 3.11+
- **Telegram:** python-telegram-bot (polling mode)
- **Vision AI:** Anthropic SDK — Claude Sonnet, with image preprocessing (Pillow for resize/compress)
- **Google Sheets:** gspread + Google service account
- **Google Drive:** Google Drive API (via google-api-python-client or PyDrive2)
- **Image processing:** Pillow (resize, EXIF strip, JPEG recompress)
- **Hosting:** Railway (Hobby plan, ~$5/mo)
- **Config:** Environment variables (bot token, Anthropic API key, Google service account JSON, sheet ID, Drive folder ID, admin user IDs)

## Project Structure

```
telegram-bet-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Entry point, bot setup, polling
│   ├── handlers.py          # /bet and /approve command handlers
│   ├── vision.py            # Image resize/compress + Claude Sonnet API
│   ├── validation.py        # Odds check, duplicate detection
│   ├── sheets.py            # Google Sheets CRUD (PENDING, MAIN, FLAGGED, BALANCE)
│   ├── drive.py             # Google Drive photo upload (daily folders)
│   └── models.py            # BetSlip, Leg dataclasses
├── config.py                # Environment/config loading
├── requirements.txt
├── .env.example
└── README.md
```

## What the Bot Does NOT Do

- No `/settle` command — results managed manually in sheet
- No time/match validation (live bets allowed)
- No currency conversion
- No cashouts or system bets
- No balance limits (negative balances allowed)
- No user self-registration (admin adds user ID to BALANCE Row 1 manually)
- No group messages for flagged bets
- Does not write to STATUS or CASTIG columns in MAIN sheet
- No web dashboard or UI

## External Account Setup Required

- **Telegram bot token** — create via BotFather (free, 2 minutes)
- **Anthropic API key** — sign up at console.anthropic.com (pay-per-use)
- **Google Cloud service account** — already available (for Sheets + Drive access)
