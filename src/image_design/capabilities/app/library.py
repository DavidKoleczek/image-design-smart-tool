"""The references the app offers: what the person pinned, what requests sent from the app were given, and the images
in the folders they pinned."""

from collections.abc import Iterator
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

from PIL import Image, UnidentifiedImageError

from image_design.capabilities.app.settings import STATE_FOLDER, moved_path
from image_design.schemas import (
    AppState,
    FolderReference,
    ImageDesignError,
    ReferenceEntry,
    ReferenceFolderPage,
    ReferenceLibrary,
    UsedReference,
    UsedReferences,
)
from image_design.shared.images.store import make_data_directory, write_atomically

# What requests sent from the app were given, in the app's folder of a data directory.
USED = "used.json"
# Where, in that folder, an image dropped or pasted into the app is kept once it is pinned, since it has no path of
# its own.
KEPT = "pins"
# What the app offers as used before, at most.
USED_ENTRIES = 50
# The images a pinned folder lists at a time, so a folder of thousands still shows at once and the rest on asking.
FOLDER_ENTRIES = 500
# The folders a pinned folder's listing goes into at a time, so one as large as a whole drive still answers soon.
FOLDER_VISITS = 1000
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".tif", ".tiff")
DRAWING_SUFFIXES = (".svg",)


def entry(path: Path, name: str | None = None) -> ReferenceEntry | None:
    """The image file at `path` as the app offers it; None when it is not a file any more."""
    if not path.is_file():
        return None
    width, height = _size(path)
    return ReferenceEntry(name=name or path.name, path=path, width=width, height=height)


def read_library(data: Path, state: AppState) -> ReferenceLibrary:
    """What is pinned in `state` and what was used before in `data`, of what is still there."""
    pinned = [found for path in state.pins if (found := entry(path)) is not None]
    used: list[ReferenceEntry] = []
    copies: set[tuple[str, int]] = set()
    for each in _read_used(data).used:
        found = entry(each.path, each.name)
        if found is None:
            continue
        # An image dropped onto several requests is kept by each, so it is offered once, by its name and size.
        copy = (each.name.lower(), each.path.stat().st_size)
        if copy not in copies:
            copies.add(copy)
            used.append(found)
    return ReferenceLibrary(pinned=pinned, used=used)


def remember_used(data: Path, given: list[UsedReference]) -> None:
    """Keep `given` as what was used last in `data`, ahead of what was used before, each path once."""
    if not given:
        return
    by_path = {each.path: each for each in [*given, *_read_used(data).used]}
    kept = UsedReferences(used=list(by_path.values())[:USED_ENTRIES])
    make_data_directory(data)
    (data / STATE_FOLDER).mkdir(exist_ok=True)
    write_atomically(data / STATE_FOLDER / USED, kept.model_dump_json(indent=2))


def follow_move(data: Path, old: Path, new: Path) -> None:
    """Point what was used before in `data` at a file, or at everything in a folder, that went from `old` to `new`."""
    used = _read_used(data).used
    moved = [
        each.model_copy(
            update={
                "path": moved_path(each.path, old, new),
                # A reference named after its file takes the file's new name.
                "name": moved_path(each.path, old, new).name if each.name == each.path.name else each.name,
            }
        )
        for each in used
    ]
    if moved != used:
        write_atomically(data / STATE_FOLDER / USED, UsedReferences(used=moved).model_dump_json(indent=2))


def is_used(data: Path, path: Path) -> bool:
    return any(each.path == path for each in _read_used(data).used)


def list_folder(folder: Path, after: str | None = None) -> ReferenceFolderPage:
    """A page of the images in a pinned folder and in the folders in it: those in a folder by name, then each folder
    in it the same way. What is hidden is left out, and so are links to folders, which could lead back up.

    A page ends at `FOLDER_ENTRIES` images or once it has gone into `FOLDER_VISITS` folders. Pass the `after` it
    returns for the next.
    """
    entries: list[FolderReference] = []
    visits = 0
    reached = after
    try:
        for at, path in _walk(folder, (), _place(after)):
            if len(entries) >= FOLDER_ENTRIES or visits >= FOLDER_VISITS:
                return ReferenceFolderPage(entries=entries, after=reached)
            reached = at
            if path is None:
                visits += 1
                continue
            width, height = _size(path)
            entries.append(
                FolderReference(name=path.name, path=path, width=width, height=height, folder=at.rpartition("/")[0])
            )
    except OSError as error:
        raise ImageDesignError(
            f"Could not read the pinned folder {folder}: {error}. If it moved, unpin it and pin it from where it is "
            "now.",
            "missing-folder",
        ) from None
    return ReferenceFolderPage(entries=entries, after=None)


def keep(source: Path, data: Path) -> Path:
    """Copy an image the person sent into a folder of its own in `data`, to pin; return where."""
    target = data / STATE_FOLDER / KEPT / uuid.uuid4().hex / source.name
    try:
        make_data_directory(data)
        target.parent.mkdir(parents=True)
        shutil.copy2(source, target)
    except OSError as error:
        raise ImageDesignError(
            f"Could not keep {source.name} to pin it: {error}. Check that {data} can be written."
        ) from None
    return target


def is_kept(data: Path, path: Path) -> bool:
    return path.is_relative_to(data / STATE_FOLDER / KEPT)


def clear_unpinned(data: Path, pins: list[Path]) -> None:
    """Clear what was kept in `data` for pins no longer among `pins`."""
    kept = data / STATE_FOLDER / KEPT
    if not kept.is_dir():
        return
    for folder in kept.iterdir():
        if not any(path.is_relative_to(folder) for path in pins):
            shutil.rmtree(folder, ignore_errors=True)


def _read_used(data: Path) -> UsedReferences:
    try:
        return UsedReferences.model_validate_json((data / STATE_FOLDER / USED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UsedReferences()


def _size(path: Path) -> tuple[int | None, int | None]:
    if path.suffix.lower() in DRAWING_SUFFIXES:
        return None, None
    try:
        # Opening reads only the file's header, so a folder of large images still lists quickly.
        with Image.open(path) as image:
            return image.size
    except (UnidentifiedImageError, OSError):
        return None, None


# A name in the order a file manager lists it, whatever its case and with `2` before `10`: its runs of digits as
# numbers between the text around them, so the same place in two names holds the same kind of piece.
type _Order = tuple[tuple[int, str], ...]
# Where an entry is in a pinned folder's listing: for each folder down to it and then the entry itself, whether it is
# a folder, which comes after the images beside it, its name's order, and its name, to tell apart names that order
# the same.
type _Place = tuple[tuple[bool, _Order, str], ...]


def _order(name: str) -> _Order:
    pieces = re.split(r"(\d+)", name.casefold())
    return tuple((int(piece), "") if index % 2 else (0, piece) for index, piece in enumerate(pieces))


def _place(at: str | None) -> _Place:
    """Where `at`, as `_walk` gives it, is in the listing; before everything for None."""
    if not at:
        return ()
    names = at.removesuffix("/").split("/")
    return tuple((index < len(names) - 1 or at.endswith("/"), _order(name), name) for index, name in enumerate(names))


def _walk(directory: Path, place: _Place, start: _Place) -> Iterator[tuple[str, Path | None]]:
    """What is in `directory` past `start`, in listing order: each image with its path, and each folder, with none,
    before what is in it. Each comes with where the listing is once it is listed: its path from the pinned folder
    with forward slashes, which ends in one for a folder."""
    try:
        images, folders = _scan(directory)
    except OSError:
        # A folder inside the pinned one that cannot be read is left out, as a file manager does.
        if not place:
            raise
        return
    inside = [name for _, _, name in place]
    for name in images:
        if (*place, (False, _order(name), name)) > start:
            yield "/".join([*inside, name]), directory / name
    for name in folders:
        here = (*place, (True, _order(name), name))
        if here > start:
            yield "/".join([*inside, name, ""]), None
        # A page that ended inside this folder goes on from there.
        if here > start or start[: len(here)] == here:
            yield from _walk(directory / name, here, start)


def _scan(directory: Path) -> tuple[list[str], list[str]]:
    """The names of the images and of the folders in `directory`, each in order, leaving out what is hidden and links
    to folders."""
    images: list[str] = []
    folders: list[str] = []
    # scandir rather than iterdir, since on Windows what it finds comes with the attribute that hides it.
    with os.scandir(directory) as found:
        for each in found:
            try:
                if each.is_dir(follow_symlinks=False):
                    if not each.is_junction() and not _hidden(each):
                        folders.append(each.name)
                elif each.name.lower().endswith(IMAGE_SUFFIXES) and each.is_file() and not _hidden(each):
                    images.append(each.name)
            except OSError:
                continue
    return sorted(images, key=_ordered), sorted(folders, key=_ordered)


def _ordered(name: str) -> tuple[_Order, str]:
    return _order(name), name


def _hidden(found: os.DirEntry[str]) -> bool:
    """Whether the platform's file manager hides `found`: by the dot its name starts with, or by the attribute Windows
    or the flag macOS marks it with."""
    if found.name.startswith("."):
        return True
    status = found.stat(follow_symlinks=False)
    return bool(
        getattr(status, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_HIDDEN
        or getattr(status, "st_flags", 0) & stat.UF_HIDDEN
    )
