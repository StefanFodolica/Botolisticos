import io
import json
from unittest.mock import MagicMock, patch
from PIL import Image
from bot.vision import parse_bet_slip, _build_vision_messages, _parse_response_json, prepare_image_for_api
from bot.models import ParsedBet


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
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content_blocks = messages[0]["content"]
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
