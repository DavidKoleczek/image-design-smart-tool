"""The folders of an image directory: make one, move one with everything in it, and delete one with its images."""

from collections.abc import Callable
import contextlib
from pathlib import Path
import secrets

from image_design.capabilities.manage_images.manage_images import delete_image, refuse_run_here
from image_design.schemas import ImageDesignError
from image_design.shared.images.store import (
    directories,
    find_image,
    folder_name,
    found,
    free_name,
    records,
    release_lock,
    save_record,
    take_lock,
    within,
)

# What file managers leave in a folder they showed, which does not keep an emptied folder from being removed.
LEFT_BY_FILE_MANAGERS = (".ds_store", "thumbs.db", "desktop.ini")


def create_folder(
    name: str, directory: Path | None = None, data_directory: Path | None = None, numbered: bool = False
) -> str:
    """Make a folder in the directory, and any above it, and return its name.

    A name that is taken is refused, or with `numbered` becomes the first free one of `name (2)`, `name (3)`, and on.
    """
    root, data = directories(directory, data_directory)
    new = folder_name(name, root, data)
    if (root / new).exists():
        new = _numbered(root, new, numbered, lambda each: (root / each).exists())
    try:
        (root / new).mkdir(parents=True)
    except OSError as error:
        raise ImageDesignError(
            f"{root / new} could not be made: {error}. Choose a name the file system takes.", "invalid-name"
        ) from None
    return new


def move_folder(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> str:
    """Give the folder another name, which moves everything in it, and return that name. Its images keep their
    versions.

    A name that is taken is refused, or with `numbered` becomes the first free one of `name (2)`, `name (3)`, and on.
    """
    root, data = directories(directory, data_directory)
    old = _existing(root, data, name)
    new = folder_name(new_name, root, data)
    if new == old:
        return old
    if within(new, old):
        raise ImageDesignError(
            f"{new!r} is inside {old}, and a folder cannot be moved into itself. Choose a name outside it.",
            "invalid-name",
        )
    source = root / old

    def taken(each: str) -> bool:
        # The same folder under another case is the folder itself, on a file system that ignores case.
        return (root / each).exists() and not (root / each).samefile(source)

    if taken(new):
        new = _numbered(root, new, numbered, taken)
    target = root / new
    inside = [(folder, record) for folder, record in records(data) if within(record.name, old)]
    holder = f"move-{secrets.token_hex(3)}"
    locks: list[Path] = []
    try:
        # Claimed as a run claims it, so the move is refused while a run works on an image in the folder.
        for _, record in inside:
            locks.append(take_lock(data, record.name, holder))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
        except OSError as error:
            raise ImageDesignError(
                f"{source} could not be moved to {target}: {error}. Close whatever has a file in it open, then move "
                "it again."
            ) from None
        for folder, record in inside:
            record.name = f"{new}{record.name[len(old) :]}"
            save_record(folder, record)
    finally:
        for lock in locks:
            release_lock(lock, holder)
    return new


def delete_folder(name: str, directory: Path | None = None, data_directory: Path | None = None) -> list[str]:
    """Delete every image in the folder as `delete_image` does, then the folder and the folders in it.

    Returns what is left, by paths in the directory: the files in it that no listing shows as images, which the tool
    never deletes, and the folders that hold them. Empty when the folder is gone.
    """
    root, data = directories(directory, data_directory)
    old = _existing(root, data, name)
    kept = {record.name.casefold(): record.name for _, record in records(data) if within(record.name, old)}
    files = {each.casefold(): each for each in found(root, data).names if within(each, old)}
    names = sorted({**files, **kept}.values(), key=str.casefold)
    # Before any image is deleted, so the folder is not left half deleted by a run that cannot be stopped from here.
    for each in kept.values():
        image = find_image(root, data, each)
        if image is not None:
            refuse_run_here(image)
    for each in names:
        delete_image(each, root, data)
    left: list[str] = []
    for folder, _, files_there in (root / old).walk(top_down=False):
        for file in files_there:
            if file.lower() in LEFT_BY_FILE_MANAGERS:
                with contextlib.suppress(OSError):
                    (folder / file).unlink()
            else:
                left.append((folder / file).relative_to(root).as_posix())
        with contextlib.suppress(OSError):
            folder.rmdir()
    return sorted(left, key=str.casefold)


def _existing(root: Path, data: Path, name: str) -> str:
    """The folder named `name` as the directory has it, ignoring case as Windows and macOS do."""
    wanted = folder_name(name, root, data)
    folders = found(root, data).folders
    for each in folders:
        if each.casefold() == wanted.casefold():
            return each
    raise ImageDesignError(
        f"There is no folder named {name!r} in {root}. The folders there: {', '.join(folders) or 'none'}. Name one "
        "of them, or pass the --directory it is in.",
        "no-such-folder",
    )


def _numbered(root: Path, name: str, numbered: bool, taken: Callable[[str], bool]) -> str:
    if numbered:
        return free_name(name, taken)
    raise ImageDesignError(
        f"{root / name} already exists. Choose another name, or pass --numbered to take the next free name like it.",
        "name-in-use",
    )
