"""The image files the app's view reads: an image's file, a version kept for it, a small copy of either, and the
frames of either."""

import base64
from collections.abc import Callable
from pathlib import Path
import threading
from urllib.parse import unquote

from mcp.types import BlobResourceContents

from image_design.capabilities.app.thumbnails import frame_thumbnail, thumbnail
from image_design.capabilities.app.tools import (
    FILE,
    FRAME_THUMBNAIL_PREFIX,
    IMAGE_FILE_PREFIX,
    IMAGE_FRAME_PREFIX,
    IMAGE_THUMBNAIL_PREFIX,
    IMAGE_VERSION_PREFIX,
    REFERENCE_FILE_PREFIX,
    REFERENCE_PREFIX,
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
FRAME_TYPE = "image/png"
# The animations whose frames stay ready to read: the one in view, and the version it is compared with.
ANIMATIONS_KEPT = 2

_thumbnails: dict[tuple[str, int, int], bytes] = {}


class _Animation:
    """The frames of one image file as the view reads them: one at a time as it plays, and a small copy of each."""

    def __init__(self, path: Path) -> None:
        self.reel = pictures.reel(path)
        self.small: list[bytes] | None = None


_animations: dict[tuple[str, int, int], _Animation] = {}
# Reading a frame moves its reel, so one frame is read at a time.
_animations_lock = threading.Lock()


def is_image_resource(uri: str) -> bool:
    return uri.startswith((IMAGE_FILE_PREFIX, IMAGE_VERSION_PREFIX, IMAGE_THUMBNAIL_PREFIX))


def is_frame_resource(uri: str) -> bool:
    return uri.startswith((IMAGE_FRAME_PREFIX, FRAME_THUMBNAIL_PREFIX))


def is_preview_resource(uri: str) -> bool:
    return uri.startswith(RUN_PREVIEW_PREFIX)


def is_reference_resource(uri: str) -> bool:
    return uri.startswith((REFERENCE_PREFIX, REFERENCE_FILE_PREFIX))


def reference_path(uri: str) -> Path:
    """The path on this machine that the reference at `uri` names."""
    prefix = REFERENCE_FILE_PREFIX if uri.startswith(REFERENCE_FILE_PREFIX) else REFERENCE_PREFIX
    return Path(unquote(uri.removeprefix(prefix)))


def read_reference_resource(uri: str, path: Path) -> BlobResourceContents:
    """The reference at `path` as base64: a small copy of it, or for a reference file as a request sends it. The
    caller checks that the app offers it."""
    try:
        if uri.startswith(REFERENCE_FILE_PREFIX):
            content, suffix = pictures.sendable(path)
            mime_type = IMAGE_TYPES[suffix]
        else:
            content, mime_type = _thumbnail(path), THUMBNAIL_TYPE
    except OSError as error:
        raise ImageDesignError(
            f"{path} could not be read: {error}. It may have been moved or deleted, so add it again from where it is "
            "now.",
            "no-such-file",
        ) from None
    return BlobResourceContents(uri=uri, mime_type=mime_type, blob=base64.b64encode(content).decode("ascii"))


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
    return _contents(uri, image, _kept(image, version, file=small), small)


def read_frame_resource(uri: str, listing: ImageListing) -> BlobResourceContents:
    """The frame the view asked for at `uri`, as a PNG, or as a small WebP, in base64.

    As with an image's file, only a file `listing` names is read.
    """
    small = uri.startswith(FRAME_THUMBNAIL_PREFIX)
    version, _, rest = uri.removeprefix(FRAME_THUMBNAIL_PREFIX if small else IMAGE_FRAME_PREFIX).partition("/")
    index, _, name = rest.partition("/")
    image = _image(listing, unquote(name))
    path = _kept(image, version, file=True)
    try:
        content = _frame(path, int(index) if index.isdigit() else -1, small, image.name)
    except OSError as error:
        raise ImageDesignError(
            f"{path} could not be read: {error}. List the images again, since it may have been moved or deleted.",
            "no-such-file",
            image.name,
        ) from None
    mime_type = THUMBNAIL_TYPE if small else FRAME_TYPE
    return BlobResourceContents(uri=uri, mime_type=mime_type, blob=base64.b64encode(content).decode("ascii"))


def _kept(image: ImageSummary, version: str, file: bool) -> Path:
    """Where the version of the image is kept. With `file`, the version can be the image's file itself."""
    if file and version == FILE:
        return image.path
    for kept in image.versions:
        if kept.id == version:
            return kept.file
    known = ", ".join(kept.id for kept in image.versions) or "none"
    raise ImageDesignError(
        f"Image {image.name} has no version {version!r}. Its versions: {known}.", "no-such-version", image.name
    )


def _frame(path: Path, index: int, small: bool, name: str) -> bytes:
    """One frame of the image at `path`, from frames kept ready by the file's size and when it was written.

    Reaching a frame of an animation decodes each one before it. A kept reel reads the frames of one that plays in
    turn, and the small copies are all made in one pass.
    """
    status = path.stat()
    key = (str(path), status.st_mtime_ns, status.st_size)
    with _animations_lock:
        animation = _animations.get(key)
        if animation is None:
            animation = _Animation(path)
            if len(_animations) >= ANIMATIONS_KEPT:
                del _animations[next(iter(_animations))]
            _animations[key] = animation
        count = animation.reel.count
        if not 0 <= index < count:
            raise ImageDesignError(
                f"{name} has {count} frame(s), so there is no frame at that index. Read a frame from 0 to {count - 1}.",
                "no-such-frame",
                name,
            )
        if not small:
            return animation.reel.png(index)
        if animation.small is None:
            # From a reel of their own, so the frames being read in turn keep their place.
            strip = pictures.Reel(animation.reel.content)
            animation.small = [frame_thumbnail(strip, each, THUMBNAIL_EDGE) for each in range(count)]
        return animation.small[index]


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
        small = thumbnail(path, THUMBNAIL_EDGE)
        if len(_thumbnails) >= THUMBNAILS_KEPT:
            _thumbnails.clear()
        _thumbnails[key] = small
    return _thumbnails[key]
