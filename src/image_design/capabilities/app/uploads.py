"""Files that wait for a request to take them: a reference dropped or pasted into the app's view, the mask painted
in it, or one frame of an animation the app sends as a still."""

import base64
import binascii
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile

from image_design.schemas import ImageDesignError

# Where uploads wait for the request that takes them, shared by every app on this machine. Each has a folder of its own
# there, under the view's id for it.
UPLOADS = Path(tempfile.gettempdir()) / "image-design-uploads"
UPLOAD_ID = re.compile(r"[0-9a-f]{16,64}")
# An upload never taken, such as one whose app was killed, is cleared by the next app to start after this long.
LIFETIME_SECONDS = 24 * 60 * 60
# The most one upload can hold, which no image a service takes comes near.
MAX_BYTES = 64 * 1024 * 1024


def receive(upload: str, name: str, offset: int, data: str) -> int:
    """Write a piece of an upload's file at `offset`, and return how much of the file has arrived.

    A piece sent again lands where it did before, so a view that lost an answer can send the piece once more.
    """
    folder = _folder(upload)
    if PurePosixPath(name.replace("\\", "/")).name != name or name in ("", ".", ".."):
        raise ImageDesignError(f"The upload's name {name!r} is not a file's name. Add the file again.", "bad-upload")
    try:
        piece = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ImageDesignError(f"The upload {name} did not arrive as base64. Add the file again.", "bad-upload") from None
    if offset < 0 or offset + len(piece) > MAX_BYTES:
        raise ImageDesignError(
            f"The upload {name} is larger than {MAX_BYTES // (1024 * 1024)} MB. Use a smaller image.", "bad-upload"
        )
    target = folder / name
    try:
        folder.mkdir(parents=True, exist_ok=True)
        held = [path.name for path in folder.iterdir()]
        if held and held != [name]:
            raise ImageDesignError(
                f"The upload {upload} already holds {held[0]}. Send {name} under an id of its own.", "bad-upload"
            )
        with target.open("r+b" if target.exists() else "wb") as file:
            file.seek(offset)
            file.write(piece)
        return target.stat().st_size
    except OSError as error:
        raise ImageDesignError(f"Could not keep the upload {name}: {error}. Add the file again.", "bad-upload") from None


def stage(upload: str, name: str, content: bytes) -> Path:
    """Keep `content` as the file the upload holds, for something the app makes for a request to take, and return
    the file."""
    folder = _folder(upload)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(content)
    except OSError as error:
        raise ImageDesignError(f"Could not keep {name} for the request: {error}. Send it again.", "bad-upload") from None
    return folder / name


def staged(upload: str) -> Path:
    """The file an upload holds."""
    folder = _folder(upload)
    held = list(folder.iterdir()) if folder.is_dir() else []
    if len(held) != 1:
        raise ImageDesignError(
            f"The upload {upload} holds nothing. Uploads are cleared once a request takes them, so add the file again.",
            "bad-upload",
        )
    return held[0]


def clear(upload: str) -> None:
    shutil.rmtree(_folder(upload), ignore_errors=True)


def clear_old(now: float) -> None:
    """Clear the uploads apps left behind, such as one that was killed, once they are past their lifetime at `now`."""
    try:
        folders = list(UPLOADS.iterdir())
    except OSError:
        return
    for folder in folders:
        try:
            old = now - folder.stat().st_mtime > LIFETIME_SECONDS
        except OSError:
            continue
        if old:
            shutil.rmtree(folder, ignore_errors=True)


def _folder(upload: str) -> Path:
    if not UPLOAD_ID.fullmatch(upload):
        raise ImageDesignError(
            f"{upload!r} is not an upload id. Name each upload with 16 to 64 lowercase hex digits.", "bad-upload"
        )
    return UPLOADS / upload
