"""Keep a file as a new version of an image, such as a crop or a merge a script made of it, or keep a draft's image."""

from pathlib import Path, PurePosixPath
import secrets

from image_design.schemas import IMAGE_FORMATS, SVG_SUFFIX, ImageDesignError, ImageRunRecord, ImageSummary
from image_design.shared.images import calls, pictures
from image_design.shared.images.store import (
    StoredImage,
    directories,
    find_image,
    image_name,
    new_image,
    release_lock,
    take_lock,
)

# The format, as Pillow names it, that each extension an image's name ends in holds.
FORMATS = {**{suffix: format.upper() for suffix, format in IMAGE_FORMATS.items()}, SVG_SUFFIX: "SVG"}


def add_image_version(
    name: str,
    path: Path | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
    parent: str | None = None,
    drafts: list[str] | None = None,
) -> ImageSummary:
    """Keep the file at `path` as the next version of the image named `name`, and put it in the image's file.

    The file is copied and left as it is. It has to be in the image's format, except that any still image becomes a PNG
    for a .png. `parent` is the agent's run that made it, which its version names; the one this process was started
    by when None. `drafts` are the drafts the file was made from, such as by merging them. With no `path`, the one
    draft in `drafts` is kept as it is, as a version its run made.
    """
    root, data = directories(directory, data_directory)
    named = image_name(name, root, data)
    suffix = PurePosixPath(named).suffix.lower()
    drafts = drafts or []
    if path is None and len(drafts) != 1:
        raise ImageDesignError(
            "Pass the file to keep as the next version, or one draft to keep as it is."
            + (
                " To keep several drafts as one version, merge them into a file first, then pass it with the drafts it "
                "was made from."
                if drafts
                else ""
            ),
            "invalid-request",
            named,
        )
    content = _content(path, named, suffix) if path is not None else None
    agent = calls.parent_of(root, data, parent, named)
    holder = f"version-{secrets.token_hex(3)}"
    # Claimed as a run claims it, so no run changes the image's versions at the same time.
    lock = take_lock(data, named, holder)
    try:
        image = find_image(root, data, named)
        if image is None:
            if drafts:
                raise _no_draft(named, drafts[0], [])
            if not (root / named).is_file():
                raise ImageDesignError(
                    f"There is no image named {named!r} in {root} to add a version to. Bring the file in as a new image "
                    "with import_image instead.",
                    "no-such-image",
                    named,
                )
            image = new_image(root, data, named)
        made_from = [_draft(image, run_id) for run_id in drafts]
        image.keep_hand_changes()
        if content is None:
            kept, drafted = made_from[0]
            version = image.add_version(drafted.read_bytes(), suffix, kept.method, kept.id)
            kept.versions.append(version.id)
            image.save_run(kept)
        else:
            run_id = agent.run.id if agent is not None else None
            version = image.add_version(content, suffix, "imported", run_id, drafts=drafts)
        image.publish(version)
    finally:
        release_lock(lock, holder)
    return image.summary()


def _draft(image: StoredImage, run_id: str) -> tuple[ImageRunRecord, Path]:
    """The draft `run_id` on the image, and the file it kept its image in, once it has made it."""
    for run in image.runs:
        if run.id == run_id and run.draft is not None:
            drafted = image.folder / run.draft
            if drafted.is_file():
                return run, drafted
            raise ImageDesignError(
                f"Draft {run_id} of {image.name} is still going. Wait for it to end, then keep it."
                if run.status == "running"
                else f"Draft {run_id} of {image.name} made no image, since it {run.status}. Keep one that is done.",
                "invalid-request",
                image.name,
            )
    raise _no_draft(image.name, run_id, [run.id for run in image.runs if run.draft is not None])


def _no_draft(name: str, run_id: str, known: list[str]) -> ImageDesignError:
    return ImageDesignError(
        f"Image {name} has no draft {run_id!r}. Its drafts: {', '.join(known) or 'none'}.", "no-such-draft", name
    )


def _content(path: Path, name: str, suffix: str) -> bytes:
    """What the version keeps of the file at `path`, once it is known to be in the image's format."""
    if not path.is_file():
        raise ImageDesignError(f"{path} is not a file. Pass the path of an image file.", "no-such-file", name)
    content = path.read_bytes()
    picture = pictures.describe(content)
    if picture is None:
        raise ImageDesignError(f"{path} is not an image the tool can read, so it was not kept.", "not-an-image", name)
    if picture.format == FORMATS[suffix] or (picture.format == "MPO" and suffix == ".jpg"):
        return content
    if suffix == ".png" and picture.frames == 1:
        return pictures.png(path)
    raise ImageDesignError(
        f"{path} is a {picture.format} image and {name} is a {suffix}, so it cannot be one of its versions. Save it "
        f"as a {suffix}, or bring it in as an image of its own with import_image.",
        "invalid-request",
        name,
    )
