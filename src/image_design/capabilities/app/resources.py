"""The image files the app's view reads: an image's file, a version kept for it, and a small copy of either."""

import base64
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote

from mcp.types import BlobResourceContents

from image_design.capabilities.app.tools import (
    FILE,
    IMAGE_FILE_PREFIX,
    IMAGE_THUMBNAIL_PREFIX,
    IMAGE_VERSION_PREFIX,
    RUN_PREVIEW_PREFIX,
)
from image_design.schemas import ImageActivity, ImageDesignError, ImageListing, ImageSummary
from image_design.shared.images import pictures

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}
THUMBNAIL_TYPE = "image/webp"
# Twice the largest a thumbnail shows, for screens of twice the pixel density.
THUMBNAIL_EDGE = 256
THUMBNAILS_KEPT = 512

_thumbnails: dict[tuple[str, int, int], bytes] = {}


def is_image_resource(uri: str) -> bool:
    return uri.startswith((IMAGE_FILE_PREFIX, IMAGE_VERSION_PREFIX, IMAGE_THUMBNAIL_PREFIX))


def is_preview_resource(uri: str) -> bool:
    return uri.startswith(RUN_PREVIEW_PREFIX)


def read_preview_resource(
    uri: str, listing: ImageListing, activity: Callable[[str], ImageActivity]
) -> BlobResourceContents:
    """The in-progress image of a run that the view asked for at `uri`, as base64.

    Only a file one of the image's `preview` events names is read, so no other path can be reached through this.
    """
    run_id, _, rest = uri.removeprefix(RUN_PREVIEW_PREFIX).partition("/")
    index, _, name = rest.partition("/")
    image = _image(listing, unquote(name))
    for event in activity(image.name).events:
        if event.kind == "preview" and event.run_id == run_id and str(event.data.get("index")) == index:
            return _contents(uri, image, Path(event.data["path"]), small=False)
    raise ImageDesignError(
        f"Run {run_id!r} on {image.name} has no preview {index!r}. Its activity has the previews of each run.",
        "no-such-preview",
        image.name,
    )


def read_image_resource(uri: str, listing: ImageListing) -> BlobResourceContents:
    """What the view asked for at `uri`, as base64.

    Only a file `listing` names is read, an image's own or one of its versions, so no other path can be reached
    through this.
    """
    if uri.startswith(IMAGE_FILE_PREFIX):
        image = _image(listing, unquote(uri.removeprefix(IMAGE_FILE_PREFIX)))
        return _contents(uri, image, image.path, small=False)
    small = uri.startswith(IMAGE_THUMBNAIL_PREFIX)
    version, _, name = uri.removeprefix(IMAGE_THUMBNAIL_PREFIX if small else IMAGE_VERSION_PREFIX).partition("/")
    image = _image(listing, unquote(name))
    if small and version == FILE:
        return _contents(uri, image, image.path, small)
    for kept in image.versions:
        if kept.id == version:
            return _contents(uri, image, kept.file, small)
    known = ", ".join(kept.id for kept in image.versions) or "none"
    raise ImageDesignError(
        f"Image {image.name} has no version {version!r}. Its versions: {known}.", "no-such-version", image.name
    )


def _image(listing: ImageListing, name: str) -> ImageSummary:
    for image in listing.images:
        if image.name == name:
            return image
    known = ", ".join(image.name for image in listing.images) or "none"
    raise ImageDesignError(
        f"There is no image named {name!r} in {listing.directory}. The images there: {known}.", "no-such-image", name
    )


def _contents(uri: str, image: ImageSummary, path: Path, small: bool) -> BlobResourceContents:
    try:
        content = _thumbnail(path) if small else path.read_bytes()
    except OSError as error:
        raise ImageDesignError(
            f"{path} could not be read: {error}. List the images again, since it may have been moved or deleted.",
            "no-such-file",
            image.name,
        ) from None
    mime_type = THUMBNAIL_TYPE if small else IMAGE_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return BlobResourceContents(uri=uri, mime_type=mime_type, blob=base64.b64encode(content).decode("ascii"))


def _thumbnail(path: Path) -> bytes:
    """A small copy of the image at `path`, remembered by the file's size and when it was written, since a view
    asks for every image in a directory each time it opens."""
    status = path.stat()
    key = (str(path), status.st_mtime_ns, status.st_size)
    if key not in _thumbnails:
        small = pictures.thumbnail(path, THUMBNAIL_EDGE)
        if len(_thumbnails) >= THUMBNAILS_KEPT:
            _thumbnails.clear()
        _thumbnails[key] = small
    return _thumbnails[key]
