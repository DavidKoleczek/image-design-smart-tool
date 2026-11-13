"""Work on any image, whichever method made it: put an earlier version back, and stop the run working on it."""

from pathlib import Path

from image_design.schemas import ImageDesignError, ImageSummary
from image_design.shared.images.runs import CANCEL
from image_design.shared.images.store import directories, release_lock, require_image, take_lock


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
