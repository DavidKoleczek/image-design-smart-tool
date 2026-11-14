"""Bring an image file from anywhere on the machine into an image directory, kept from the start."""

from pathlib import Path, PurePosixPath
import secrets
import shutil

from image_design.capabilities.manage_images.names import settled
from image_design.schemas import ImageDesignError, ImageSummary
from image_design.shared.images import pictures
from image_design.shared.images.store import directories, find_image, image_name, new_image, release_lock, take_lock

# The formats, as Pillow names them, that an image keeps as the file has them, and the extension each is kept under.
# An MPO is the JPEG many cameras write. Any other image is kept as a PNG.
KEPT_AS_IS = {"PNG": ".png", "JPEG": ".jpg", "MPO": ".jpg", "WEBP": ".webp", "GIF": ".gif", "SVG": ".svg"}
CONVERTED_SUFFIX = ".png"


def import_image(
    path: Path,
    name: str | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary:
    """Bring the image file at `path` into the directory as a new image, with the file as its first version.

    The image has the file's own name at the top of the directory when `name` is None, the file's name in a folder
    when `name` ends in a slash, and `name` otherwise. A file already in the directory under that name stays where it
    is and is kept from then on. A name that is taken is refused, or with `numbered` becomes the first free one of
    `name (2)`, `name (3)`, and on.
    """
    root, data = directories(directory, data_directory)
    content, suffix = _content(path)
    folder = name is None or name.replace("\\", "/").endswith("/")
    new = image_name(f"{name or ''}{path.stem}{suffix}" if folder else str(name), root, data)
    if PurePosixPath(new).suffix.lower() != suffix:
        raise ImageDesignError(
            f"{name!r} ends in {PurePosixPath(new).suffix} and {path.name} comes in as a {suffix}. End the name in "
            f"{suffix}, or end it in a slash to name only the folder.",
            "invalid-name",
            new,
        )
    target = root / new
    in_place = target.is_file() and target.samefile(path) and find_image(root, data, new) is None
    if not in_place:
        new = settled(root, data, new, None, numbered, path.name)
    holder = f"import-{secrets.token_hex(3)}"
    lock = take_lock(data, new, holder)
    try:
        image = new_image(root, data, new)
        try:
            if not in_place:
                image.path.parent.mkdir(parents=True, exist_ok=True)
                image.path.write_bytes(content)
            image.keep_hand_changes()
        except OSError as error:
            shutil.rmtree(image.folder, ignore_errors=True)
            raise ImageDesignError(
                f"{path} could not be brought in as {image.path}: {error}. Check that {root} and {data} can be "
                "written.",
                None,
                new,
            ) from None
    finally:
        release_lock(lock, holder)
    return image.summary()


def _content(path: Path) -> tuple[bytes, str]:
    """What the image keeps of the file at `path`, and the extension it is kept under."""
    if not path.is_file():
        raise ImageDesignError(f"{path} is not a file. Pass the path of an image file.", "no-such-file")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ImageDesignError(f"{path} could not be read: {error}. Check that it can be opened.") from None
    picture = pictures.describe(content)
    if picture is None:
        raise ImageDesignError(
            f"{path} is not an image the tool can read, so it was not brought in. Pass a PNG, JPEG, WebP, GIF, or SVG, "
            "or another still image such as a BMP or TIFF, which is kept as a PNG.",
            "not-an-image",
        )
    if picture.format in KEPT_AS_IS:
        return content, KEPT_AS_IS[picture.format]
    return pictures.frame_png(path), CONVERTED_SUFFIX
