"""What every method does with a request before it sends it: check what it was given, and claim the image."""

from collections.abc import Generator
import contextlib
from pathlib import Path
import shutil
from typing import Any, NamedTuple

from pydantic import BaseModel, ValidationError

from image_design.schemas import ImageDesignError
from image_design.shared.images import pictures
from image_design.shared.images.store import StoredImage, find_image, new_image, release_lock, take_lock


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
    return [write(inputs / f"reference-{number}{each.suffix}", each.content) for number, each in enumerate(sent, 1)]


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
        _end_crashed_run(image)
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


def source(image: StoredImage, version: str | None) -> Path | None:
    """The file to edit: the version asked for, or the image's file; None when the image is created."""
    if version is not None:
        return image.folder / image.version(version).file
    return image.path if image.path.is_file() else None


def write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _end_crashed_run(image: StoredImage) -> None:
    """Mark a run whose process ended without ending it, so the image's history says how it went."""
    last = image.runs[-1] if image.runs else None
    if last is not None and last.status == "running":
        last.status = "failed"
        last.error = "The process running the request ended before the request did."
        image.save_runs()
