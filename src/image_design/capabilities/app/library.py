"""The references the app offers: what the person pinned, what requests sent from the app were given, and the images
in the folders they pinned."""

from pathlib import Path
import shutil
import uuid

from PIL import Image, UnidentifiedImageError

from image_design.capabilities.app.settings import STATE_FOLDER, moved_path
from image_design.schemas import (
    AppState,
    ImageDesignError,
    ReferenceEntry,
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
# What a pinned folder lists, at most, so a folder of thousands still shows at once.
FOLDER_ENTRIES = 500
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".tif", ".tiff")
DRAWING_SUFFIXES = (".svg",)


def entry(path: Path, name: str | None = None) -> ReferenceEntry | None:
    """The image file at `path` as the app offers it; None when it is not a file any more."""
    if not path.is_file():
        return None
    width = height = None
    if path.suffix.lower() not in DRAWING_SUFFIXES:
        try:
            # Opening reads only the file's header, so a folder of large images still lists quickly.
            with Image.open(path) as image:
                width, height = image.size
        except (UnidentifiedImageError, OSError):
            pass
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


def list_folder(folder: Path) -> list[ReferenceEntry]:
    """The images in a pinned folder, by name, leaving out hidden files and what is in its folders."""
    try:
        files = [
            child
            for child in folder.iterdir()
            if not child.name.startswith(".") and child.suffix.lower() in IMAGE_SUFFIXES
        ]
    except OSError as error:
        raise ImageDesignError(
            f"Could not read the pinned folder {folder}: {error}. If it moved, unpin it and pin it from where it is "
            "now.",
            "missing-folder",
        ) from None
    files.sort(key=lambda child: child.name.lower())
    entries = (entry(child) for child in files[:FOLDER_ENTRIES])
    return [found for found in entries if found is not None]


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
