"""Measure an SVG image against its budgets, and render one to a raster file. Neither calls a model."""

from io import BytesIO
from pathlib import Path, PurePosixPath

from PIL import Image

from image_design.capabilities.svg_image import measure
from image_design.schemas import DEFAULT_SVG_CANVAS, IMAGE_FORMATS, SVG_SUFFIX, ImageDesignError, SvgBudgets, SvgCheck
from image_design.shared.images import pictures
from image_design.shared.images.requests import invalid
from image_design.shared.images.store import directories, find_image, image_name, require_image

# The raster formats an SVG is exported to; a .gif would be a one-frame animation.
EXPORT_FORMATS = {suffix: IMAGE_FORMATS[suffix] for suffix in (".png", ".jpg", ".webp")}
JPEG_QUALITY = 95


def check_svg_image(name: str, workspace: Path | None = None) -> SvgCheck:
    """Measure the SVG in the image's file against its budgets: those of its last drawing, else its own size."""
    root, data = directories(workspace)
    kept, path = _svg(root, data, name)
    image = find_image(root, data, kept)
    content = path.read_bytes()
    budgets = image.record.budgets if image is not None else None
    if budgets is None:
        own = pictures.describe(content)
        budgets = SvgBudgets(canvas=(own.width, own.height) if own is not None else DEFAULT_SVG_CANVAS)
    return SvgCheck(name=kept, path=path, budgets=budgets, **measure.measure(content)._asdict())


def export_svg_image(
    name: str,
    output: Path,
    scale: float = 1,
    version: str | None = None,
    workspace: Path | None = None,
) -> Path:
    """Render the image's SVG, or one of its versions, to a .png, .jpg, or .webp at `scale` times its size."""
    root, data = directories(workspace)
    suffix = output.suffix.lower()
    if suffix not in EXPORT_FORMATS:
        raise invalid(
            f"{output} does not end in a format to export to. End it in one of: {', '.join(EXPORT_FORMATS)}.", name
        )
    if not scale > 0:
        raise invalid(f"scale is {scale}. Pass more than 0, such as 2 for twice the canvas size.", name)
    if version is None:
        _, source = _svg(root, data, name)
    else:
        image = require_image(root, data, name)
        source = image.folder / image.version(version).file
        if source.suffix.lower() != SVG_SUFFIX:
            raise invalid(f"Version {version} of {image.name} is not an SVG, so there is nothing to render.", name)
    rendered = pictures.svg_png(source.read_bytes(), source.parent, scale)
    output.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".png":
        output.write_bytes(rendered)
        return output.resolve()
    with Image.open(BytesIO(rendered)) as opened:
        picture = opened.convert("RGBA")
    if suffix == ".jpg":
        # A JPEG has no transparency, so what is see-through shows white, as on a page.
        flat = Image.new("RGB", picture.size, "white")
        flat.paste(picture, mask=picture.getchannel("A"))
        flat.save(output, format="JPEG", quality=JPEG_QUALITY)
    else:
        picture.save(output, format="WEBP", lossless=True)
    return output.resolve()


def _svg(root: Path, data: Path, name: str) -> tuple[str, Path]:
    """The name and file of the SVG image named `name`, which need not be one the tool keeps data for."""
    kept = image_name(name, root, data)
    if PurePosixPath(kept).suffix.lower() != SVG_SUFFIX:
        raise invalid(f"{name!r} is not an SVG. Name an image that ends in .svg.", name)
    path = root / kept
    if not path.is_file():
        raise ImageDesignError(
            f"There is no file {path}. Name an SVG image in {root}, or pass the --workspace it is in.",
            "no-such-image",
            name,
        )
    return kept, path
