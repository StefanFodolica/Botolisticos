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
