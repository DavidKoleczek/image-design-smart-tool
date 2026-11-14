"""What the tool reads from image files, how it converts them for sending, and the sizes the image models accept."""

from io import BytesIO
import math
from pathlib import Path
from typing import NamedTuple

from PIL import Image, UnidentifiedImageError
import resvg_py

from image_design.schemas import ImageDesignError

# The formats, as Pillow names them, that the image services take as they are, and the suffix each is sent with. Any
# other image is sent as a PNG.
SENT_AS_IS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
SVG_SUFFIXES = (".svg", ".svgz")
# Content is taken for an SVG when its root element starts this early, past any XML declaration and comments.
SVG_MARKER = b"<svg"
SVG_SNIFF_BYTES = 4096
# The sizes the GPT Image 2.6 models accept for a still image, from
# https://developers.openai.com/api/docs/guides/image-generation. An animation only needs multiples of 16.
SIZE_STEP = 16
MAX_EDGE = 3840
MAX_RATIO = 3
MIN_PIXELS = 655_360
MAX_PIXELS = 8_294_400
THUMBNAIL_QUALITY = 80


class Picture(NamedTuple):
    """What the tool needs to know of an image file."""

    format: str  # as Pillow names it, such as PNG or GIF
    width: int
    height: int
    frames: int
    alpha: bool
    frame_ms: int | None = None  # how long the first frame shows, for an animation


def describe(content: bytes) -> Picture | None:
    """What `content` is as an image, or None when it is not one Pillow can read or resvg can render.

    An SVG's size is the size resvg renders it at.
    """
    try:
        with Image.open(BytesIO(content)) as image:
            return Picture(
                format=image.format or "",
                width=image.width,
                height=image.height,
                frames=getattr(image, "n_frames", 1),
                alpha="A" in image.getbands() or "transparency" in image.info,
                frame_ms=image.info.get("duration"),
            )
    except (UnidentifiedImageError, OSError):
        pass
    if SVG_MARKER not in content[:SVG_SNIFF_BYTES]:
        return None
    try:
        rendered = svg_png(content)
    except ImageDesignError:
        return None
    with Image.open(BytesIO(rendered)) as image:
        return Picture(format="SVG", width=image.width, height=image.height, frames=1, alpha=True)


def svg_png(content: bytes, resources: Path | None = None, zoom: float | None = None) -> bytes:
    """An SVG rendered with resvg as a PNG, at `zoom` times its own size.

    `resources` is where the files it refers to by relative path are; none are found without it.
    """
    try:
        return resvg_py.svg_to_bytes(
            svg_string=content.decode("utf-8"),
            resources_dir=str(resources) if resources is not None else None,
            zoom=zoom,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ImageDesignError(f"The SVG could not be rendered: {error}.") from None


def read(path: Path) -> Picture:
    """What the image at `path` is, raising when it is not a file Pillow can read."""
    if not path.is_file():
        raise ImageDesignError(f"{path} is not a file. Pass the path of an image that exists.", "no-such-file")
    picture = describe(path.read_bytes())
    if picture is None:
        raise ImageDesignError(
            f"{path} is not an image the tool can read. Pass an image file, such as a PNG, JPEG, WebP, GIF, or SVG."
        )
    return picture


def frame_png(path: Path, index: int = 0) -> bytes:
    """One frame of the image at `path`, as a PNG; the image itself for a still one."""
    with Image.open(path) as image:
        image.seek(index)
        frame = image.convert("RGBA")
    buffer = BytesIO()
    frame.save(buffer, format="PNG")
    return buffer.getvalue()


def sendable(path: Path) -> tuple[bytes, str]:
    """The image at `path` in a format the image services take, and the suffix to send it with.

    A PNG, JPEG, or WebP is sent as it is, whatever its file is named. Any other image is sent as `png` makes it.
    """
    if path.suffix.lower() not in SVG_SUFFIXES and (format := read(path).format) in SENT_AS_IS:
        return path.read_bytes(), SENT_AS_IS[format]
    return png(path), ".png"


def png(path: Path) -> bytes:
    """The image at `path` as a PNG with transparency, at its own size.

    An SVG is rendered with resvg. Any other image Pillow reads gives its first frame.
    """
    if path.suffix.lower() not in SVG_SUFFIXES:
        read(path)
        return frame_png(path)
    if not path.is_file():
        raise ImageDesignError(f"{path} is not a file. Pass the path of an image that exists.", "no-such-file")
    try:
        return resvg_py.svg_to_bytes(svg_path=str(path), resources_dir=str(path.parent))
    except ValueError as error:
        raise ImageDesignError(f"{path} is an SVG that could not be rendered: {error}. Fix the SVG.") from None


def thumbnail(path: Path, edge: int) -> bytes:
    """The image at `path` as a WebP that fits a square `edge` pixels on a side; the first frame of an animation.

    An SVG is rendered at that size rather than shrunk, so a small drawing stays sharp.
    """
    try:
        if path.suffix.lower() in SVG_SUFFIXES:
            picture = read(path)
            zoom = edge / max(picture.width, picture.height)
            source = BytesIO(svg_png(path.read_bytes(), path.parent, zoom))
        else:
            source = BytesIO(path.read_bytes())
        with Image.open(source) as image:
            small = image.convert("RGBA")
        small.thumbnail((edge, edge))
        buffer = BytesIO()
        small.save(buffer, format="WEBP", quality=THUMBNAIL_QUALITY)
    except (UnidentifiedImageError, OSError) as error:
        raise ImageDesignError(f"{path} could not be read as an image: {error}.") from None
    return buffer.getvalue()


def transparent(content: bytes) -> bool:
    """Whether any pixel of the image is transparent, even partly."""
    with Image.open(BytesIO(content)) as image:
        lowest, _ = image.convert("RGBA").getchannel("A").getextrema()
    return isinstance(lowest, int | float) and lowest < 255


def size_problem(width: int, height: int, animated: bool) -> str | None:
    """Why the image models would refuse to make an image this size, or None when they accept it."""
    if width % SIZE_STEP or height % SIZE_STEP or width <= 0 or height <= 0:
        return f"the width and height must be multiples of {SIZE_STEP}"
    if animated:
        return None
    if max(width, height) > MAX_EDGE:
        return f"neither edge can be longer than {MAX_EDGE}"
    if max(width, height) > MAX_RATIO * min(width, height):
        return f"the longer edge can be at most {MAX_RATIO} times the shorter"
    if not MIN_PIXELS <= width * height <= MAX_PIXELS:
        return f"it must have between {MIN_PIXELS:,} and {MAX_PIXELS:,} pixels"
    return None


def nearest_size(width: int, height: int) -> tuple[int, int]:
    """The still image size the image models accept that is closest in shape and area to `width` by `height`."""
    if size_problem(width, height, animated=False) is None:
        return width, height
    ratio = min(max(width / height, 1 / MAX_RATIO), MAX_RATIO)
    pixels = min(max(width * height, MIN_PIXELS), MAX_PIXELS)
    exact_width = math.sqrt(pixels * ratio)
    exact_height = exact_width / ratio
    scale = min(1.0, MAX_EDGE / max(exact_width, exact_height))
    fitted_width = max(SIZE_STEP, round(exact_width * scale / SIZE_STEP) * SIZE_STEP)
    fitted_height = max(SIZE_STEP, round(exact_height * scale / SIZE_STEP) * SIZE_STEP)
    # Rounding to the step can cross a limit by one step, so walk back inside.
    while size_problem(fitted_width, fitted_height, animated=False) is not None:
        if fitted_width * fitted_height < MIN_PIXELS:
            if fitted_width <= fitted_height:
                fitted_width += SIZE_STEP
            else:
                fitted_height += SIZE_STEP
        elif fitted_width >= fitted_height:
            fitted_width -= SIZE_STEP
        else:
            fitted_height -= SIZE_STEP
    return fitted_width, fitted_height
