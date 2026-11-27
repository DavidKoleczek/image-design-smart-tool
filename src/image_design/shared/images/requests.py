"""What every method does with a request before it sends it: check what it was given, and claim the image."""

from collections.abc import Generator
import contextlib
from pathlib import Path
import shutil
from typing import Any, NamedTuple

from pydantic import BaseModel, ValidationError

from image_design.schemas import ImageDesignError
from image_design.shared.images import pictures
from image_design.shared.images.store import CRASHED, StoredImage, alive, find_image, new_image, release_lock, take_lock

REFERENCE_PREFIX = "reference-"


class Reference(NamedTuple):
    """An image sent with a request, already in a format the image services take."""

    content: bytes
    suffix: str


def validated[Request: BaseModel](request_type: type[Request], **fields: Any) -> Request:
    """A `request_type` made from `fields`, raising ImageDesignError naming the first field that does not fit."""
    try:
        return request_type(**fields)
    except ValidationError as error:
        problem = error.errors()[0]
        where = ".".join(str(part) for part in problem["loc"])
        raise invalid(f"{where}: {problem['msg']}.", fields.get("name")) from None


def invalid(message: str, image: str | None) -> ImageDesignError:
    return ImageDesignError(message, "invalid-request", image)


def references(paths: list[Path]) -> list[Reference]:
    """Each image in `paths` converted for sending, raising for one that is not an image the tool can read."""
    return [Reference(*pictures.sendable(path)) for path in paths]


def write_references(sent: list[Reference], inputs: Path) -> list[Path]:
    """Write each reference into `inputs`, numbered in the order they are sent."""
    return [
        write(inputs / f"{REFERENCE_PREFIX}{number}{each.suffix}", each.content) for number, each in enumerate(sent, 1)
    ]


@contextlib.contextmanager
def claimed(root: Path, data: Path, name: str, run_id: str) -> Generator[tuple[StoredImage, Path]]:
    """The image named `name`, claimed for the run `run_id`, and the lock that claims it.

    The run started in the block owns the lock from then on. When the block raises instead, the lock is released, the
    run's folder removed, and an image nothing was ever kept for forgotten.
    """
    lock = take_lock(data, name, run_id)
    image: StoredImage | None = None
    try:
        image = find_image(root, data, name) or new_image(root, data, name)
        _end_crashed_runs(image)
        image.keep_hand_changes()
        yield image, lock
    except BaseException:
        release_lock(lock, run_id)
        if image is not None:
            with contextlib.suppress(OSError):
                shutil.rmtree(image.run_folder(run_id))
            if not image.versions.versions and not image.runs:
                shutil.rmtree(image.folder, ignore_errors=True)
        raise


@contextlib.contextmanager
def drafted(root: Path, data: Path, name: str, run_id: str) -> Generator[tuple[StoredImage, None]]:
    """The image named `name`, for the draft `run_id` to try a change on, and no lock.

    A draft keeps its image apart and changes nothing kept for the image but its own run's record, so it claims
    nothing: drafts go on at the same time as each other and as a run that claims the image. When the block raises
    instead, the run's folder is removed.
    """
    image = find_image(root, data, name)
    if image is None or not image.versions.versions:
        raise invalid(
            f"A draft starts from a version of an image, and the tool keeps no version of {name}. Make the image with "
            "a call that is not a draft first.",
            name,
        )
    try:
        yield image, None
    except BaseException:
        with contextlib.suppress(OSError):
            shutil.rmtree(image.run_folder(run_id))
        raise


def draft_from(image: StoredImage, version: str | None) -> str:
    """The version a draft starts from: the one asked for, or the one in the image's file.

    A draft sends the version's own file, which never changes, rather than the image's file, which a run that claims
    the image can replace while the draft is going.
    """
    if version is not None:
        return image.version(version).id
    if image.versions.current is None or not image.current_file_matches():
        raise invalid(
            f"{image.name}'s file was changed outside the tool, so it is not a version a draft can start from. Pass "
            "the version to start from, or make a call that is not a draft, which keeps the file as a version first.",
            image.name,
        )
    return image.versions.current


def source(image: StoredImage, version: str | None) -> Path | None:
    """The file to edit: the version asked for, or the image's file; None when the image is created."""
    if version is not None:
        return image.folder / image.version(version).file
    return image.path if image.path.is_file() else None


def edited_version(image: StoredImage, version: str | None) -> str | None:
    """The version a request edits, by its id: the one asked for, or the one in the image's file, which the image has
    claimed so it is kept; None when the request creates the image."""
    if source(image, version) is None:
        return None
    return version or image.versions.current


def previewed_source(root: Path, data: Path, name: str, version: str | None) -> Path | None:
    """The file a request for the image named `name` would edit, found without claiming the image or keeping
    anything for it."""
    image = find_image(root, data, name)
    if image is not None:
        return source(image, version)
    if version is not None:
        raise ImageDesignError(f"Image {name} has no version {version!r}. Its versions: none.", "no-such-version", name)
    path = root / name
    return path if path.is_file() else None


def write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _end_crashed_runs(image: StoredImage) -> None:
    """Mark each run whose process ended without ending it, so the image's history says how it went.

    With the image claimed, no other run that makes versions is going, but a draft may be.
    """
    for run in list(image.runs):
        if run.status == "running" and (run.draft is None or not alive(run.pid)):
            run.status = "failed"
            run.error = CRASHED
            image.save_run(run)
