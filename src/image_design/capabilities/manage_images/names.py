"""Finding an image by its name, and settling the name a moved, copied, or imported one takes."""

from pathlib import Path, PurePosixPath

from image_design.schemas import ImageDesignError, ImageSummary
from image_design.shared.images.store import StoredImage, find_image, found_names, found_summary, free_name, image_name


def find(root: Path, data: Path, name: str) -> StoredImage | str:
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
        "--workspace it is in.",
        "no-such-image",
        name,
    )


def name_of(found: StoredImage | str) -> str:
    return found.name if isinstance(found, StoredImage) else found


def summary_of(found: StoredImage | str, root: Path) -> ImageSummary:
    return found.summary() if isinstance(found, StoredImage) else found_summary(root, found)


def with_same_extension(old: str, new_name: str, root: Path, data: Path) -> str:
    """`new_name` as an image's name, once it is known to end as `old` does, since no capability here converts."""
    new = image_name(new_name, root, data)
    kept, wanted = PurePosixPath(old).suffix.lower(), PurePosixPath(new).suffix.lower()
    if kept != wanted:
        raise ImageDesignError(
            f"{new_name!r} ends in {wanted} and {old} is a {kept}. Moving or copying an image does not convert it, so "
            f"end the new name in {kept}.",
            "invalid-name",
            old,
        )
    return new


def taken(root: Path, data: Path, name: str, own: StoredImage | str | None) -> bool:
    """Whether an image or a file has the name, other than `own`, the image that is taking it."""
    kept = find_image(root, data, name)
    if kept is not None and not (isinstance(own, StoredImage) and kept.record.id == own.record.id):
        return True
    target = root / name
    if not target.exists():
        return False
    source = root / name_of(own) if own is not None else None
    # The same file under another case is the image itself, on a file system that ignores case.
    return not (source is not None and source.exists() and target.samefile(source))


def settled(root: Path, data: Path, name: str, own: StoredImage | str | None, numbered: bool, taker: str) -> str:
    """`name` when nothing else has it. When something does, the first numbered name that is free with `numbered`,
    and a failure without."""
    if not taken(root, data, name, own):
        return name
    if numbered:
        return free_name(name, lambda each: taken(root, data, each, own))
    raise ImageDesignError(
        f"{root / name} already exists, so {taker} cannot take its name. Choose another name, pass --numbered to take "
        f"the next free name like it, or delete that image first with `image-design delete-image --name {name}`.",
        "name-in-use",
        name,
    )
