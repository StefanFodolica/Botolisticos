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
