"""Find the images whose files were moved or renamed outside the tool, and keep each under the name its file has."""

from collections import defaultdict
from pathlib import Path, PurePosixPath
import secrets

from image_design.schemas import ImageDesignError, ImageMove, ImageRelinking
from image_design.shared.images.store import (
    StoredImage,
    directories,
    file_facts,
    found_names,
    kept_images,
    release_lock,
    save_record,
    take_lock,
)


def relink_images(likely: list[str] | None = None, workspace: Path | None = None) -> ImageRelinking:
    """Point each image whose file is gone at the file that is certainly it, and report the rest.

    A file is certainly an image's when the tool keeps nothing for it and it holds exactly what the image's current
    version does. When several images or files hold the same, those with the same file name pair up. A file is likely
    an image's when it only has the image's file name, as after it was changed and then moved: it is reported, and
    taken for the images named in `likely`.
    """
    root, data = directories(workspace)
    kept, _ = kept_images(root, data)
    known = {image.name.casefold() for image in kept}
    # An image a run is still making has no file yet, and one that never had a version never had a file.
    gone = sorted(
        (
            image
            for image in kept
            if image.versions.current is not None and not image.path.is_file() and image.running() is None
        ),
        key=lambda image: image.name.casefold(),
    )
    free = [name for name in found_names(root, data) if name.casefold() not in known] if gone else []
    certain = _certain(root, gone, free)
    paired = {image.record.id for image, _ in certain}
    taken = {name for _, name in certain}
    maybe = _by_file_name(
        [image for image in gone if image.record.id not in paired], [name for name in free if name not in taken]
    )
    wanted = {name.replace("\\", "/").casefold() for name in likely or []}
    unknown = wanted - {image.name.casefold() for image, _ in maybe}
    if unknown:
        having = ", ".join(image.name for image, _ in maybe) or "none"
        raise ImageDesignError(
            f"{', '.join(sorted(unknown))} has no likely file to take. The images that have one: {having}.",
            "no-such-image",
        )
    relinked: list[ImageMove] = []
    taking = [*certain, *((image, name) for image, name in maybe if image.name.casefold() in wanted)]
    for image, name in sorted(taking, key=lambda pair: pair[0].name.casefold()):
        if _relink(image, name):
            relinked.append(ImageMove(name=image.name, new_name=name))
    moved = {move.name for move in relinked}
    offered = [ImageMove(name=image.name, new_name=name) for image, name in maybe if image.name not in moved]
    settled = moved | {move.name for move in offered}
    return ImageRelinking(
        relinked=relinked, likely=offered, gone=[image.name for image in gone if image.name not in settled]
    )


def _certain(root: Path, gone: list[StoredImage], free: list[str]) -> list[tuple[StoredImage, str]]:
    """Each image with the one file that holds what its current version does."""
    images: dict[str, list[StoredImage]] = defaultdict(list)
    for image in gone:
        images[image.version(str(image.versions.current)).sha256].append(image)
    files: dict[str, list[str]] = defaultdict(list)
    for name in free:
        facts = file_facts(root / name)
        if facts is not None and facts.sha256 in images:
            files[facts.sha256].append(name)
    pairs: list[tuple[StoredImage, str]] = []
    for sha256, names in files.items():
        same = _by_file_name(images[sha256], names)
        pairs.extend(same)
        left = [image for image in images[sha256] if all(image is not paired for paired, _ in same)]
        names_left = [name for name in names if all(name != paired for _, paired in same)]
        if len(left) == 1 and len(names_left) == 1:
            pairs.append((left[0], names_left[0]))
    return pairs


def _by_file_name(images: list[StoredImage], names: list[str]) -> list[tuple[StoredImage, str]]:
    """Each image with the file that has its file name, when one image and one file have that name."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for name in names:
        by_name[PurePosixPath(name).name.casefold()].append(name)
    wanting: dict[str, list[StoredImage]] = defaultdict(list)
    for image in images:
        wanting[PurePosixPath(image.name).name.casefold()].append(image)
    return [
        (waiting[0], by_name[file_name][0])
        for file_name, waiting in wanting.items()
        if len(waiting) == 1 and len(by_name[file_name]) == 1
    ]


def _relink(image: StoredImage, name: str) -> bool:
    """Keep the image under `name`; False when a run claimed it meanwhile, which leaves it for the next time."""
    holder = f"relink-{secrets.token_hex(3)}"
    try:
        lock = take_lock(image.data, image.name, holder)
    except ImageDesignError:
        return False
    try:
        save_record(image.folder, image.record.model_copy(update={"name": name}))
    finally:
        release_lock(lock, holder)
    return True
