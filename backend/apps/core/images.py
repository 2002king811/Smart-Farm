"""Safe image uploads: JPG, PNG or WebP up to 10 MB, re-encoded (which drops EXIF, including
GPS location) and resized."""

from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


def process_image(upload, max_size: int = 400) -> ContentFile:  # type: ignore[no-untyped-def]
    if hasattr(upload, "seek"):
        upload.seek(0)
    if upload.size > MAX_BYTES:
        raise ValidationError({"file": ["The image must be 10 MB or smaller."]})
    try:
        image: Image.Image = Image.open(upload)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError({"file": ["Upload a JPG, PNG or WebP image."]}) from exc
    fmt = image.format
    if fmt not in ALLOWED:
        raise ValidationError({"file": ["Upload a JPG, PNG or WebP image."]})
    image = ImageOps.exif_transpose(image)  # keep the right way up once EXIF is gone
    image.thumbnail((max_size, max_size))
    if fmt == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    out = BytesIO()
    image.save(out, format=fmt, quality=88)  # no exif= argument: metadata is not copied
    return ContentFile(out.getvalue(), name=f"image.{ALLOWED[fmt]}")
