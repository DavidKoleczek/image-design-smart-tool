"""Bring image files, and folders of them, from anywhere on the machine into a workspace, kept from the start."""

from pathlib import Path, PurePosixPath
import secrets
import shutil

from image_design.capabilities.manage_images.folders import create_folder
from image_design.capabilities.manage_images.names import settled
from image_design.schemas import ImageDesignError, ImageImports, ImageRefusal, ImageSummary
from image_design.shared.images import pictures
from image_design.shared.images.store import (
    directories,
    find_image,
    folder_name,
    image_name,
    new_image,
    release_lock,
    take_lock,
)

# The formats, as Pillow names them, that an image keeps as the file has them, and the extension each is kept under.
# An MPO is the JPEG many cameras write. Any other image is kept as a PNG.
KEPT_AS_IS = {"PNG": ".png", "JPEG": ".jpg", "MPO": ".jpg", "WEBP": ".webp", "GIF": ".gif", "SVG": ".svg"}
CONVERTED_SUFFIX = ".png"
# The files of a folder brought in that come in as images. A project's folder holds more than images, and the rest of
# its files are left where they are rather than refused one by one.
FOLDER_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".tif", ".tiff")


def import_image(
    path: Path, name: str | None = None, workspace: Path | None = None, numbered: bool = False
) -> ImageSummary:
    """Bring the image file at `path` into the workspace as a new image, with the file as its first version.

    The image has the file's own name at the top of the image directory when `name` is None, the file's name in a
    folder when `name` ends in a slash, and `name` otherwise. A file already in the image directory under that name
    stays where it is and is kept from then on. A name that is taken is refused, or with `numbered` becomes the first
    free one of `name (2)`, `name (3)`, and on.
    """
    root, data = directories(workspace)
    content, suffix = _content(path)
    folder = name is None or name.replace("\\", "/").endswith("/")
    new = image_name(f"{name or ''}{path.stem}{suffix}" if folder else str(name), root, data)
    if PurePosixPath(new).suffix.lower() != suffix:
        raise ImageDesignError(
            f"{name!r} ends in {PurePosixPath(new).suffix} and {path.name} comes in as a {suffix}. End the name in "
            f"{suffix}, or end it in a slash to name only the folder.",
            "invalid-name",
            new,
        )
    target = root / new
    in_place = target.is_file() and target.samefile(path) and find_image(root, data, new) is None
    if not in_place:
        new = settled(root, data, new, None, numbered, path.name)
    holder = f"import-{secrets.token_hex(3)}"
    lock = take_lock(data, new, holder)
    try:
        image = new_image(root, data, new)
        try:
            if not in_place:
                image.path.parent.mkdir(parents=True, exist_ok=True)
                image.path.write_bytes(content)
            image.keep_hand_changes()
        except OSError as error:
            shutil.rmtree(image.folder, ignore_errors=True)
            raise ImageDesignError(
                f"{path} could not be brought in as {image.path}: {error}. Check that {root} and {data} can be "
                "written.",
                None,
                new,
            ) from None
    finally:
        release_lock(lock, holder)
    return image.summary()


def import_images(paths: list[Path], folder: str | None = None, workspace: Path | None = None) -> ImageImports:
    """Bring each file and folder at `paths` into the workspace, in `folder` of its images or at their top, as new
    images under numbered names where theirs are taken.

    A folder comes in under its own name with the folders in it. Of its files only images come in, and hidden files
    and folders are left out. What cannot come in is refused with why, and the rest still comes in.
    """
    root, data = directories(workspace)
    into = folder_name(folder, root, data) if folder else None
    imports = ImageImports(images=[], folders=[], refused=[])
    for path in paths:
        if path.is_dir():
            _import_folder(path.resolve(), into, root, imports)
            continue
        try:
            imports.images.append(import_image(path=path, name=_inside(into), workspace=root.parent, numbered=True))
        except ImageDesignError as error:
            imports.refused.append(ImageRefusal(name=path.name, reason=error.reason, message=str(error)))
    return imports


def _import_folder(source: Path, into: str | None, root: Path, imports: ImageImports) -> None:
    """Bring the folder `source` into `into` of the image directory `root`, under its own name, with what of it comes
    in."""
    # Read before anything is made, so a folder brought in from inside the image directory never takes in its copy.
    walked: list[tuple[Path, list[str], list[str]]] = []
    for folder, folders, files in source.walk():
        folders[:] = sorted(each for each in folders if not each.startswith("."))
        walked.append((folder, list(folders), sorted(files)))
    try:
        top = create_folder(name=f"{into}/{source.name}" if into else source.name, workspace=root.parent, numbered=True)
    except ImageDesignError as error:
        imports.refused.append(ImageRefusal(name=source.name, reason=error.reason, message=str(error)))
        return
    imports.folders.append(top)
    for folder, folders, files in walked:
        inside = folder.relative_to(source).as_posix()
        place = top if inside == "." else f"{top}/{inside}"
        for each in folders:
            try:
                (root / place / each).mkdir(parents=True, exist_ok=True)
            except OSError as error:
                imports.refused.append(
                    ImageRefusal(
                        name=f"{source.name}/{_from(inside, each)}",
                        reason="invalid-name",
                        message=f"{folder / each} could not be made in {root / place}: {error}.",
                    )
                )
                continue
            imports.folders.append(f"{place}/{each}")
        for file in files:
            if file.startswith(".") or Path(file).suffix.lower() not in FOLDER_IMAGE_SUFFIXES:
                continue
            try:
                imports.images.append(
                    import_image(path=folder / file, name=f"{place}/", workspace=root.parent, numbered=True)
                )
            except ImageDesignError as error:
                name = f"{source.name}/{_from(inside, file)}"
                imports.refused.append(ImageRefusal(name=name, reason=error.reason, message=str(error)))


def _inside(folder: str | None) -> str | None:
    """A folder as `import_image` takes it for a name: ending in a slash, so the image keeps its file's name."""
    return f"{folder}/" if folder else None


def _from(inside: str, name: str) -> str:
    """The path of `name`, in the folder at `inside` of a folder brought in, from that folder."""
    return name if inside == "." else f"{inside}/{name}"


def _content(path: Path) -> tuple[bytes, str]:
    """What the image keeps of the file at `path`, and the extension it is kept under."""
    if not path.is_file():
        raise ImageDesignError(f"{path} is not a file. Pass the path of an image file.", "no-such-file")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ImageDesignError(f"{path} could not be read: {error}. Check that it can be opened.") from None
    picture = pictures.describe(content)
    if picture is None:
        raise ImageDesignError(
            f"{path} is not an image the tool can read, so it was not brought in. Pass a PNG, JPEG, WebP, GIF, or SVG, "
            "or another still image such as a BMP or TIFF, which is kept as a PNG.",
            "not-an-image",
        )
    if picture.format in KEPT_AS_IS:
        return content, KEPT_AS_IS[picture.format]
    return pictures.frame_png(path), CONVERTED_SUFFIX
