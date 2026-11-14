"""Work on any image, whichever method made it: put an earlier version back, stop its run, and read its history."""

from pathlib import Path

from image_design.schemas import ImageActivity, ImageDesignError, ImageEvent, ImageSummary
from image_design.shared.images.runs import CANCEL
from image_design.shared.images.store import EVENTS, directories, read_events, release_lock, require_image, take_lock


def restore_image_version(
    name: str, version: str, directory: Path | None = None, data_directory: Path | None = None
) -> ImageSummary:
    """Put an earlier version of the image back in its file. Keeps the file first if it was changed by hand."""
    root, data = directories(directory, data_directory)
    image = require_image(root, data, name)
    holder = f"restore-{version}"
    lock = take_lock(data, image.name, holder)
    try:
        chosen = image.version(version)
        image.keep_hand_changes()
        image.publish(chosen)
    finally:
        release_lock(lock, holder)
    return image.summary()


def cancel_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None:
    """Ask the process running the image's run, which may be another one, to stop it."""
    root, data = directories(directory, data_directory)
    image = require_image(root, data, name)
    run = image.running()
    if run is None:
        raise ImageDesignError(f"Image {image.name} has no run going, so there is nothing to cancel.", "not-running")
    (image.run_folder(run.id) / CANCEL).touch()


def read_image_activity(
    name: str, directory: Path | None = None, data_directory: Path | None = None, after: str | None = None
) -> ImageActivity:
    """Every event of every run on the image, in order, or only those after `after`, a cursor an earlier call gave.

    A cursor is a run's id and how far into its events the reader got, so it stays good as more runs are added.
    """
    root, data = directories(directory, data_directory)
    image = require_image(root, data, name)
    ids = [run.id for run in image.runs]
    first, offset = 0, 0
    if after is not None:
        run_id, _, read_to = after.rpartition(":")
        if run_id not in ids or not read_to.isdigit():
            raise ImageDesignError(
                f"{after!r} is not a cursor read_image_activity gave for {image.name}. Pass the cursor of an earlier "
                "call, or leave out after to read from the start.",
                "invalid-request",
                image.name,
            )
        first, offset = ids.index(run_id), int(read_to)
    events: list[ImageEvent] = []
    cursor = after
    for index in range(first, len(ids)):
        read, end = read_events(image.run_folder(ids[index]) / EVENTS, offset if index == first else 0)
        events.extend(read)
        cursor = f"{ids[index]}:{end}"
    return ImageActivity(name=image.name, events=events, status=image.summary().status, cursor=cursor)
