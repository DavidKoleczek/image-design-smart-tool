"""Work on any image, whichever method made it: list, view, move, and delete images, put an earlier version back, stop
a run, and read an image's history."""

import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import time

from image_design.schemas import ImageActivity, ImageDesignError, ImageEvent, ImageListing, ImageRunRecord, ImageSummary
from image_design.shared.images.runs import CANCEL
from image_design.shared.images.store import (
    EVENTS,
    StoredImage,
    directories,
    find_image,
    found_names,
    found_summary,
    image_name,
    kept_images,
    load_runs,
    read_events,
    read_state,
    release_lock,
    remove_empty_folders,
    require_image,
    take_lock,
    write_state,
)
from image_design.shared.images.store import alive as process_alive

# How long delete_image waits for the run it stopped to end.
STOP_WAIT_SECONDS = 15
STOP_POLL_SECONDS = 0.1
# How long it then gives the process that ran it to exit, which a process started only for the run does at once.
EXIT_WAIT_SECONDS = 1


def list_images(directory: Path | None = None, data_directory: Path | None = None) -> ImageListing:
    """Every image in the directory, in name order, and the one viewed last. Reads only.

    An image file the tool keeps no data for, such as one put there by hand, is listed with no versions.
    """
    root, data = directories(directory, data_directory)
    if root.exists() and not root.is_dir():
        raise ImageDesignError(f"{root} is a file, not a directory of images. Pass the --directory images are kept in.")
    kept, unreadable = kept_images(root, data)
    images = [image.summary() for image in kept]
    names = {image.name.casefold() for image in kept}
    images.extend(found_summary(root, name) for name in found_names(root, data) if name.casefold() not in names)
    images.sort(key=lambda summary: summary.name.casefold())
    last_viewed = read_state(data).last_viewed
    return ImageListing(
        directory=root,
        data_directory=data,
        images=images,
        last_viewed=last_viewed if any(summary.name == last_viewed for summary in images) else None,
        unreadable=unreadable,
    )


def view_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> ImageSummary:
    """Record the image as the one viewed last in its directory, and return its summary."""
    root, data = directories(directory, data_directory)
    summary = _summary(_find(root, data, name), root)
    write_state(data, read_state(data).model_copy(update={"last_viewed": summary.name}))
    return summary


def move_image(
    name: str, new_name: str, directory: Path | None = None, data_directory: Path | None = None
) -> ImageSummary:
    """Give the image another name, which moves its file, and return its summary there. Its versions stay with it."""
    root, data = directories(directory, data_directory)
    found = _find(root, data, name)
    old = _name(found)
    new = image_name(new_name, root, data)
    kept, wanted = PurePosixPath(old).suffix.lower(), PurePosixPath(new).suffix.lower()
    if kept != wanted:
        raise ImageDesignError(
            f"{new_name!r} ends in {wanted} and {old} is a {kept}. Moving an image does not convert it, so end the "
            f"new name in {kept}.",
            "invalid-name",
            old,
        )
    if new == old:
        return _summary(found, root)
    source, target = root / old, root / new
    taken = find_image(root, data, new)
    if isinstance(found, StoredImage) and taken is not None and taken.record.id == found.record.id:
        taken = None
    # The same file under another case is the image itself, on a file system that ignores case.
    if taken is not None or (target.exists() and not (source.exists() and target.samefile(source))):
        raise ImageDesignError(
            f"{target} already exists, so {old} cannot take its name. Choose another name, or delete that image first "
            f"with `image-design delete-image --name {new}`.",
            "name-in-use",
            new,
        )
    holder = f"move-{secrets.token_hex(3)}"
    locks = [take_lock(data, old, holder)]
    try:
        if new.casefold() != old.casefold():
            locks.append(take_lock(data, new, holder))
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                source.rename(target)
            except OSError as error:
                raise ImageDesignError(
                    f"{source} could not be moved to {target}: {error}. Close whatever has the file open, then move it "
                    "again.",
                    None,
                    old,
                ) from None
            remove_empty_folders(source.parent, root)
        if isinstance(found, StoredImage):
            found.record.name = new
            found.save_record()
        _follow(data, old, new)
    finally:
        for lock in locks:
            release_lock(lock, holder)
    return _summary(_find(root, data, new), root)


def delete_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None:
    """Delete the image's file and everything kept for it, stopping a run working on it first."""
    root, data = directories(directory, data_directory)
    found = _find(root, data, name)
    if isinstance(found, str):
        _remove_file(root / found, found)
        remove_empty_folders((root / found).parent, root)
        _follow(data, found, None)
        return
    run = found.running()
    if run is not None and run.pid == os.getpid():
        # Its handle is here, and waiting for it to end could hold up the very loop that ends it.
        raise ImageDesignError(
            f"Image {found.name} is being worked on by a run in this process. Stop it with `await run.cancel()` on its "
            "handle, then delete the image.",
            "already-running",
            found.name,
        )
    if run is not None:
        _stop(found, run)
    holder = f"delete-{secrets.token_hex(3)}"
    lock = take_lock(data, found.name, holder)
    try:
        # Moved aside in one step first, so what is kept for the image is either all there or all gone.
        aside = data / f".deleting-{found.record.id}"
        try:
            found.folder.rename(aside)
        except OSError as error:
            raise ImageDesignError(
                f"What is kept for {found.name} in {found.folder} could not be removed: {error}. Close whatever has a "
                "file in it open, then delete the image again.",
                None,
                found.name,
            ) from None
        try:
            _remove_file(found.path, found.name)
        except ImageDesignError:
            aside.rename(found.folder)
            raise
        shutil.rmtree(aside, ignore_errors=True)
        remove_empty_folders(found.path.parent, root)
        _follow(data, found.name, None)
    finally:
        release_lock(lock, holder)


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


def _find(root: Path, data: Path, name: str) -> StoredImage | str:
    """The image named `name`: what the tool keeps for it, or only its name when it is a file the tool has not kept.

    Case is ignored, as Windows and macOS do, and the name returned is the one the file has.
    """
    wanted = image_name(name, root, data)
    image = find_image(root, data, wanted)
    if image is not None:
        return image
    found = found_names(root, data)
    for each in found:
        if each.casefold() == wanted.casefold():
            return each
    known = ", ".join(found) or "none"
    raise ImageDesignError(
        f"There is no image named {name!r} in {root}. The images there: {known}. Name one of them, or pass the "
        "--directory and --data-directory it was made with.",
        "no-such-image",
        name,
    )


def _name(found: StoredImage | str) -> str:
    return found.name if isinstance(found, StoredImage) else found


def _summary(found: StoredImage | str, root: Path) -> ImageSummary:
    return found.summary() if isinstance(found, StoredImage) else found_summary(root, found)


def _follow(data: Path, name: str, new_name: str | None) -> None:
    """Keep the record of the image viewed last pointing at it when it moves, and empty it when the image is gone."""
    state = read_state(data)
    if state.last_viewed is not None and state.last_viewed.casefold() == name.casefold():
        write_state(data, state.model_copy(update={"last_viewed": new_name}))


def _remove_file(path: Path, name: str) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise ImageDesignError(
            f"{path} could not be deleted: {error}. Close whatever has the file open, then delete the image again.",
            None,
            name,
        ) from None


def _stop(image: StoredImage, run: ImageRunRecord) -> None:
    """Stop the run as `cancel_image` does, and wait for it to end and for its process to exit."""
    cancel = image.run_folder(run.id) / CANCEL
    cancel.parent.mkdir(parents=True, exist_ok=True)
    cancel.touch()
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    ended: float | None = None
    # Its process may keep a file of the run open until it exits, and Windows refuses to move a folder until then.
    while process_alive(run.pid):
        now = time.monotonic()
        current = next((each for each in load_runs(image.folder) if each.id == run.id), run)
        if current.status != "running":
            ended = ended or now
            # A process that goes on past the run it ran, as a caller of the library may, is not waited on further.
            if now - ended >= EXIT_WAIT_SECONDS:
                return
        elif now >= deadline:
            raise ImageDesignError(
                f"The run on {image.name} was asked to stop, but process {run.pid} had not ended it after "
                f"{STOP_WAIT_SECONDS} seconds, so the image was left as it is. Delete it again once the run has ended.",
                "already-running",
                image.name,
            )
        time.sleep(STOP_POLL_SECONDS)
