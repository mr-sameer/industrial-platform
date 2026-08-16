"""
Image resizing/optimization — Module 3B. Pillow-based, synchronous (CPU-
bound; callers run this in FastAPI's threadpool via `run_in_threadpool`,
never on the event loop directly — see app.services.branding_service).
"""

import io

from PIL import Image

LOGO_THUMBNAIL_SIZE = (256, 256)
COVER_RESPONSIVE_WIDTHS = (640, 1280, 1920)
_JPEG_QUALITY = 85


def _reencode(img: Image.Image, content_type: str) -> bytes:
    buffer = io.BytesIO()
    fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[content_type]
    save_kwargs = {"quality": _JPEG_QUALITY, "optimize": True} if fmt in ("JPEG", "WEBP") else {}
    if fmt == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")  # JPEG has no alpha channel
    img.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def make_thumbnail(
    data: bytes, content_type: str, size: tuple[int, int] = LOGO_THUMBNAIL_SIZE
) -> bytes:
    """Produces a square, center-cropped thumbnail — used for the logo."""
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB") if content_type == "image/jpeg" else img.convert("RGBA")
        # Center-crop to square before resizing, so the thumbnail isn't stretched.
        width, height = img.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize(size, Image.Resampling.LANCZOS)
        return _reencode(img, content_type)


def make_responsive_variant(data: bytes, content_type: str, target_width: int) -> bytes:
    """Produces a width-capped variant (aspect ratio preserved) — used for the cover image."""
    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB") if content_type == "image/jpeg" else img.convert("RGBA")
        width, height = img.size
        if width <= target_width:
            return _reencode(img, content_type)  # never upscale
        new_height = round(height * (target_width / width))
        img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
        return _reencode(img, content_type)
