"""Work on any image, whichever method made it: list, view, move, copy, and delete images, put an earlier version
back, stop a run, and read an image's history."""

import os
from pathlib import Path
import secrets
import shutil
import time
import uuid

from image_design.capabilities.manage_images.names import find, name_of, settled, summary_of, with_same_extension
from image_design.schemas import (
    ImageActivity,
    ImageDesignError,
    ImageEvent,
    ImageFrame,
    ImageFrames,
    ImageListing,
    ImageRunRecord,
    ImageSummary,
    ImageView,
)
from image_design.shared.images import pictures
from image_design.shared.images.runs import CANCEL
from image_design.shared.images.store import (
    EVENTS,
    IMAGES,
    StoredImage,
    directories,
    found,
    found_summary,
    kept_images,
    load_runs,
    read_events,
    release_lock,
    require_image,
    save_record,
    take_lock,
)
from image_design.shared.images.store import alive as process_alive

# How long delete_image waits for the run it stopped to end.
STOP_WAIT_SECONDS = 15
STOP_POLL_SECONDS = 0.1
# How long it then gives the process that ran it to exit, which a process started only for the run does at once.
EXIT_WAIT_SECONDS = 1


def list_images(directory: Path | None = None, data_directory: Path | None = None) -> ImageListing:
    """Every image in the directory, in name order, and every folder. Reads only.

    An image file the tool keeps no data for, such as one put there by hand, is listed with no versions.
    """
    root, data = directories(directory, data_directory)
    if root.exists() and not root.is_dir():
        raise ImageDesignError(f"{root} is a file, not a directory of images. Pass the --directory images are kept in.")
    kept, unreadable = kept_images(root, data)
    images = [image.summary() for image in kept]
    names = {image.name.casefold() for image in kept}
    there = found(root, data)
    images.extend(found_summary(root, name) for name in there.names if name.casefold() not in names)
    images.sort(key=lambda summary: summary.name.casefold())
    return ImageListing(
        directory=root, data_directory=data, images=images, folders=there.folders, unreadable=unreadable
    )


def view_image(
    name: str,
    version: str | None = None,
    frames_output: Path | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
) -> ImageView:
    """The image's summary, with its file or one of its versions frame by frame. Writes only to `frames_output`, a
    folder each frame is written to as a PNG named after its index."""
    root, data = directories(directory, data_directory)
    viewing = find(root, data, name)
    summary = summary_of(viewing, root)
    if version is not None:
        image = viewing if isinstance(viewing, StoredImage) else require_image(root, data, name)
        viewed = _frames(image.folder / image.version(version).file, version)
    elif summary.width is not None:
        viewed = _frames(root / summary.name, None)
    elif frames_output is not None:
        raise ImageDesignError(
            f"{summary.name} has no file that can be read, so it has no frames to write out. Pass --version to write "
            "out a version's frames.",
            "no-such-file",
            summary.name,
        )
    else:
        viewed = None
    if viewed is not None and frames_output is not None:
        _write_frames(viewed, frames_output, summary.name)
    return ImageView(**dict(summary), viewed=viewed)


def move_image(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary:
    """Give the image another name, which moves its file, and return its summary there. Its versions stay with it.

    A name that is taken is refused, or with `numbered` becomes the first free one of `name (2)`, `name (3)`, and on.
    """
    root, data = directories(directory, data_directory)
    moving = find(root, data, name)
    old = name_of(moving)
    new = with_same_extension(old, new_name, root, data)
    if new == old:
        return summary_of(moving, root)
    new = settled(root, data, new, moving, numbered, old)
    source, target = root / old, root / new
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
        if isinstance(moving, StoredImage):
            moving.record.name = new
            moving.save_record()
    finally:
        for lock in locks:
            release_lock(lock, holder)
    return summary_of(find(root, data, new), root)


def copy_image(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary:
    """Make another image under `new_name` with a copy of the image's file and of everything kept for it, and return
    its summary.

    A name that is taken is refused, or with `numbered` becomes the first free one of `name (2)`, `name (3)`, and on.
    """
    root, data = directories(directory, data_directory)
    original = find(root, data, name)
    old = name_of(original)
    new = settled(root, data, with_same_extension(old, new_name, root, data), None, numbered, f"a copy of {old}")
    source, target = root / old, root / new
    holder = f"copy-{secrets.token_hex(3)}"
    # Claimed as a run claims it, so what is kept for the image does not change while it is copied.
    locks = [take_lock(data, old, holder)]
    try:
        locks.append(take_lock(data, new, holder))
        try:
            if isinstance(original, StoredImage):
                _copy_kept(original, new)
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        except OSError as error:
            raise ImageDesignError(
                f"{old} could not be copied to {target}: {error}. Check that {root} and {data} can be written and "
                "have room.",
                None,
                old,
            ) from None
    finally:
        for lock in locks:
            release_lock(lock, holder)
    return summary_of(find(root, data, new), root)


def delete_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None:
    """Delete the image's file and everything kept for it, stopping a run working on it first."""
    root, data = directories(directory, data_directory)
    deleting = find(root, data, name)
    if isinstance(deleting, str):
        _remove_file(root / deleting, deleting)
        return
    refuse_run_here(deleting)
    run = deleting.running()
    if run is not None:
        _stop(deleting, run)
    holder = f"delete-{secrets.token_hex(3)}"
    lock = take_lock(data, deleting.name, holder)
    try:
        # Moved aside in one step first, so what is kept for the image is either all there or all gone.
        aside = data / f".deleting-{deleting.record.id}"
        try:
            deleting.folder.rename(aside)
        except OSError as error:
            raise ImageDesignError(
                f"What is kept for {deleting.name} in {deleting.folder} could not be removed: {error}. Close whatever "
                "has a file in it open, then delete the image again.",
                None,
                deleting.name,
            ) from None
        try:
            _remove_file(deleting.path, deleting.name)
        except ImageDesignError:
            aside.rename(deleting.folder)
            raise
        shutil.rmtree(aside, ignore_errors=True)
    finally:
        release_lock(lock, holder)


def refuse_run_here(image: StoredImage) -> None:
    """Raise when a run in this process is working on the image, which deleting it cannot stop."""
    run = image.running()
    if run is not None and run.pid == os.getpid():
        # Its handle is here, and waiting for it to end could hold up the very loop that ends it.
        raise ImageDesignError(
            f"Image {image.name} is being worked on by a run in this process. Stop it with `await run.cancel()` on its "
            "handle, then delete the image.",
            "already-running",
            image.name,
        )


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
        for event in read:
            if event.kind == "started":
                # Where the run's folder is now, which is not where it started for a copy or a project that moved.
                event.data["run_folder"] = str(image.run_folder(ids[index]))
        events.extend(read)
        cursor = f"{ids[index]}:{end}"
    return ImageActivity(name=image.name, events=events, status=image.summary().status, cursor=cursor)


def _frames(path: Path, version: str | None) -> ImageFrames:
    """Each frame of the file and how long it shows: one frame for a still image."""
    picture = pictures.read(path)
    # An SVG has the one frame resvg renders, which Pillow cannot read.
    reel = pictures.reel(path) if picture.frames > 1 else None
    durations = [reel.duration_ms(index) for index in range(reel.count)] if reel is not None else [0]
    return ImageFrames(
        version=version,
        path=path,
        width=picture.width,
        height=picture.height,
        frames=[ImageFrame(index=index, duration_ms=duration) for index, duration in enumerate(durations)],
    )


def _write_frames(viewed: ImageFrames, output: Path, name: str) -> None:
    """Write each frame to `output` as a PNG, and set each frame's `path` to its file."""
    reel = pictures.reel(viewed.path) if len(viewed.frames) > 1 else None
    try:
        output.mkdir(parents=True, exist_ok=True)
        for frame in viewed.frames:
            written = output / f"frame-{frame.index}.png"
            written.write_bytes(reel.png(frame.index) if reel is not None else pictures.png(viewed.path))
            frame.path = written.resolve()
    except OSError as error:
        raise ImageDesignError(
            f"The frames of {name} could not be written to {output}: {error}. Pass a folder that can be written.",
            None,
            name,
        ) from None


def _copy_kept(original: StoredImage, new: str) -> None:
    """Keep for the image named `new` a copy of everything kept for `original`."""
    record = original.record.model_copy(update={"id": uuid.uuid4().hex, "name": new})
    # Copied aside and moved into place in one step, so a listing never reads a copy that is half there.
    aside = original.data / f".copying-{record.id}"
    try:
        shutil.copytree(original.folder, aside)
        save_record(aside, record)
        aside.rename(original.data / IMAGES / record.id)
    except OSError:
        shutil.rmtree(aside, ignore_errors=True)
        raise


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
