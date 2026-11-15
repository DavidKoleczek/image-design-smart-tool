"""The small copies of images the app's view shows: in its lists of images and references, and on its timeline."""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from image_design.schemas import ImageDesignError
from image_design.shared.images import pictures

QUALITY = 80


def thumbnail(path: Path, edge: int) -> bytes:
    """The image at `path` as a WebP that fits a square `edge` pixels on a side; the first frame of an animation.

    An SVG is rendered at that size rather than shrunk, so a small drawing stays sharp.
    """
    try:
        if path.suffix.lower() in pictures.SVG_SUFFIXES:
            picture = pictures.read(path)
            zoom = edge / max(picture.width, picture.height)
            source = BytesIO(pictures.svg_png(path.read_bytes(), path.parent, zoom))
        else:
            source = BytesIO(path.read_bytes())
        with Image.open(source) as image:
            # A JPEG decodes at a fraction of its size that still covers the edge, so a folder of photos lists fast.
            image.draft(None, (edge, edge))
            # Turned as its camera recorded, as a browser shows the file itself.
            small = ImageOps.exif_transpose(image).convert("RGBA")
    except (UnidentifiedImageError, OSError) as error:
        raise ImageDesignError(f"{path} could not be read as an image: {error}.") from None
    return _webp(small, edge)


def frame_thumbnail(reel: pictures.Reel, index: int, edge: int) -> bytes:
    """One frame of `reel` as a WebP that fits a square `edge` pixels on a side."""
    return _webp(reel.frame(index), edge)


def _webp(image: Image.Image, edge: int) -> bytes:
    image.thumbnail((edge, edge))
    buffer = BytesIO()
    image.save(buffer, format="WEBP", quality=QUALITY)
    return buffer.getvalue()
