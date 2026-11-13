"""Create or edit an image with an OpenAI image model through the Images API."""

import contextlib
from datetime import UTC, datetime
from functools import partial
import os
from pathlib import Path, PurePosixPath
import shutil
import sys

from pydantic import BaseModel, ValidationError

from image_design.capabilities.openai_image import images_api
from image_design.schemas import (
    DEFAULT_OPENAI_IMAGE_MODEL,
    IMAGE_FORMATS,
    OPENAI_IMAGE_MODELS,
    ImageDesignError,
    ImageRunRecord,
    Mark,
    OpenAIImageBackground,
    OpenAIImageComplexity,
    OpenAIImageModel,
    OpenAIImageQuality,
)
from image_design.shared.images import detach as detaching
from image_design.shared.images import marks as marking
from image_design.shared.images import pictures
from image_design.shared.images.runs import ImageRun, InProcessRun
from image_design.shared.images.store import (
    StoredImage,
    directories,
    find_image,
    image_name,
    new_image,
    new_run_id,
    release_lock,
    take_lock,
)

# What starts a detached run, given its request on stdin. Tests swap it for a command that fakes the API.
BACKGROUND_COMMAND = [sys.executable, "-m", "image_design.capabilities.openai_image.background"]
# The Images API's limits, from https://developers.openai.com/api/reference/resources/images/methods/edit and
# https://developers.openai.com/api/docs/guides/image-generation.
MAX_INPUT_IMAGES = 16
MAX_COUNT = 10
MAX_PREVIEWS = 3
FRAMES = (2, 16)
FRAME_MS = (20, 2000)
REFERENCE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
# What the API is told about marks, which it receives as a separate layer over the image being edited.
MARKS_NOTE = (
    "The separate markup layer over the image has marks that show what this request refers to. Do not draw the marks "
    "in the image."
)


class OpenAIImageRequest(BaseModel):
    """Everything `generate_openai_image` was asked, which a detached run's process starts from."""

    prompt: str
    name: str
    directory: Path | None = None
    data_directory: Path | None = None
    references: list[Path] = []
    marks: list[Mark] = []
    mask: Path | None = None
    version: str | None = None
    frame: int | None = None
    model: str | None = None
    size: tuple[int, int] | None = None
    quality: OpenAIImageQuality | None = None
    complexity: OpenAIImageComplexity | None = None
    background: OpenAIImageBackground | None = None
    compression: int | None = None
    count: int = 1
    frames: int | None = None
    frame_ms: int | None = None
    previews: int = 0
    timeout_seconds: int = 600
    origin: str | None = None


async def generate_openai_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    mask: Path | None = None,
    version: str | None = None,
    frame: int | None = None,
    model: str | None = None,
    size: tuple[int, int] | None = None,
    quality: OpenAIImageQuality | None = None,
    complexity: OpenAIImageComplexity | None = None,
    background: OpenAIImageBackground | None = None,
    compression: int | None = None,
    count: int = 1,
    frames: int | None = None,
    frame_ms: int | None = None,
    previews: int = 0,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
) -> ImageRun:
    """Start creating the image named `name`, or editing it when it exists, and return its run once it is sent."""
    try:
        request = OpenAIImageRequest(
            prompt=prompt,
            name=name,
            directory=directory,
            data_directory=data_directory,
            references=references or [],
            marks=marks or [],
            mask=mask,
            version=version,
            frame=frame,
            model=model,
            size=size,
            quality=quality,
            complexity=complexity,
            background=background,
            compression=compression,
            count=count,
            frames=frames,
            frame_ms=frame_ms,
            previews=previews,
            timeout_seconds=timeout_seconds,
            origin=origin,
        )
    except ValidationError as error:
        problem = error.errors()[0]
        where = ".".join(str(part) for part in problem["loc"])
        raise ImageDesignError(f"{where}: {problem['msg']}.", "invalid-request", name) from None
    if not detach:
        return await start(request)
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    # Made absolute here, since the run's process need not resolve them from the same place.
    absolute = request.model_copy(
        update={
            "directory": root,
            "data_directory": data,
            "references": [path.resolve() for path in request.references],
            "mask": request.mask.resolve() if request.mask else None,
        }
    )
    return await detaching.detach(BACKGROUND_COMMAND, absolute, root, data)


async def start(request: OpenAIImageRequest) -> InProcessRun:
    """Check the request, keep what it sends, and start sending it."""
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    name = image_name(request.name, root, data)
    suffix = PurePosixPath(name).suffix.lower()
    model = _model(request.model)
    images_api.preflight()
    for path in request.references:
        _require_reference(path)
    run_id = new_run_id()
    lock = take_lock(data, name, run_id)
    image: StoredImage | None = None
    try:
        image = find_image(root, data, name) or new_image(root, data, name)
        _end_crashed_run(image)
        image.keep_hand_changes()
        folder = image.run_folder(run_id)
        api_request = _prepare(request, image, suffix, model, folder / "inputs")
        run = ImageRunRecord(
            id=run_id,
            method="openai",
            prompt=request.prompt,
            request=_recorded(api_request, folder),
            origin=request.origin,
            pid=os.getpid(),
            started=datetime.now(UTC),
        )
        image.runs.append(run)
        image.save_runs()
        work = partial(images_api.send, api_request, model, request.timeout_seconds)
        return InProcessRun(image, run, work, request.timeout_seconds, lock, suffix)
    except BaseException:
        release_lock(lock, run_id)
        if image is not None:
            with contextlib.suppress(OSError):
                shutil.rmtree(image.run_folder(run_id))
            if not image.versions.versions and not image.runs:
                # Nothing was ever kept for it, so it is forgotten.
                shutil.rmtree(image.folder, ignore_errors=True)
        raise


def _prepare(
    request: OpenAIImageRequest, image: StoredImage, suffix: str, model: OpenAIImageModel, inputs: Path
) -> images_api.ApiRequest:
    """The request to send, with the files it sends copied into `inputs`, once it is known the API can take it."""
    animated = suffix == ".gif"
    source = _source(request, image)
    if source is None:
        given = {"marks": bool(request.marks), "a mask": request.mask is not None, "frame": request.frame is not None}
        what = next((what for what, used in given.items() if used), None)
        if what is not None:
            raise _invalid(
                f"There is no image named {image.name} to edit, so {what} cannot be used. Leave it out to create the "
                "image, or name an image that exists.",
                image.name,
            )
    picture = pictures.read(source) if source is not None else None
    frame = request.frame or 0
    if picture is not None:
        if request.frame is not None and not 0 <= request.frame < picture.frames:
            raise _invalid(
                f"{image.name} has {picture.frames} frame(s), so frame {request.frame} does not exist. Pass a frame "
                f"from 0 to {picture.frames - 1}.",
                image.name,
            )
        if request.mask is not None and (picture.frames > 1 or animated):
            raise _invalid("A mask works only for edits of still images. Leave out the mask.", image.name)
    if len(request.references) + (source is not None) > MAX_INPUT_IMAGES:
        raise _invalid(
            f"A request can send at most {MAX_INPUT_IMAGES} images, counting the image being edited. Send fewer "
            "references.",
            image.name,
        )
    # An edit keeps what the image being edited has, unless the request says otherwise.
    size, frames, frame_ms = request.size, request.frames, request.frame_ms
    if size is None and picture is not None and not animated:
        size = pictures.nearest_size(picture.width, picture.height)
    if animated and picture is not None and picture.frames > 1:
        if size is None and pictures.size_problem(picture.width, picture.height, animated=True) is None:
            size = (picture.width, picture.height)
        frames = frames or min(max(picture.frames, FRAMES[0]), FRAMES[1])
        if frame_ms is None and picture.frame_ms:
            frame_ms = min(max(picture.frame_ms, FRAME_MS[0]), FRAME_MS[1])

    inputs.mkdir(parents=True, exist_ok=True)
    sent: list[Path] = []
    if source is not None:
        sent.append(_write(inputs / "image.png", pictures.frame_png(source, frame)))
    for number, reference in enumerate(request.references, 1):
        if reference.suffix.lower() in images_api.MEDIA_TYPES:
            sent.append(_copy(reference, inputs / f"reference-{number}{reference.suffix.lower()}"))
        else:
            sent.append(_write(inputs / f"reference-{number}.png", pictures.frame_png(reference)))
    markup = None
    if request.marks and picture is not None:
        marking.require_marks(request.marks)
        markup = _write(inputs / "marks.png", marking.layer(request.marks, picture.width, picture.height))
    mask = None
    if request.mask is not None and picture is not None:
        mask = _copy(_require_mask(request.mask, picture), inputs / "mask.png")
    prompt = request.prompt
    if request.marks:
        prompt = f"{prompt}\n\n{MARKS_NOTE}\n{marking.describe(request.marks)}"
    return images_api.ApiRequest(
        model=model.id,
        prompt=prompt,
        images=sent,
        markup=markup,
        mask=mask,
        size=size,
        quality=request.quality,
        complexity=request.complexity,
        background=request.background,
        output_format=IMAGE_FORMATS[suffix],
        compression=request.compression,
        count=request.count,
        frames=frames,
        frame_ms=frame_ms,
        previews=request.previews,
    )


def _require_arguments(request: OpenAIImageRequest) -> None:
    """Raise for arguments the API would refuse, before anything is kept or sent."""
    suffix = PurePosixPath(request.name.replace("\\", "/")).suffix.lower()
    animated = suffix == ".gif"
    name = request.name
    if not request.prompt.strip():
        raise _invalid("The prompt is empty. Say what to make, or what to change.", name)
    if not 1 <= request.count <= MAX_COUNT:
        raise _invalid(f"count is {request.count}. Make from 1 to {MAX_COUNT} images at a time.", name)
    if not 0 <= request.previews <= MAX_PREVIEWS:
        raise _invalid(f"previews is {request.previews}. Ask for 0 to {MAX_PREVIEWS} previews.", name)
    if request.previews and request.count > 1:
        raise _invalid("Previews work only with a count of 1. Leave out previews, or make one image.", name)
    if request.previews and animated:
        raise _invalid("A .gif has no previews. Leave out previews.", name)
    if request.timeout_seconds <= 0:
        raise _invalid("timeout_seconds must be more than 0.", name)
    if not animated and (request.frames is not None or request.frame_ms is not None):
        raise _invalid("frames and frame_ms are for a .gif. Leave them out, or name a .gif.", name)
    if request.frames is not None and not FRAMES[0] <= request.frames <= FRAMES[1]:
        raise _invalid(f"frames is {request.frames}. A .gif can have {FRAMES[0]} to {FRAMES[1]} frames.", name)
    if request.frame_ms is not None and not FRAME_MS[0] <= request.frame_ms <= FRAME_MS[1]:
        raise _invalid(f"frame_ms is {request.frame_ms}. A frame lasts {FRAME_MS[0]} to {FRAME_MS[1]} ms.", name)
    if request.compression is not None and suffix not in (".jpg", ".webp"):
        raise _invalid("compression is for a .jpg or .webp. Leave it out, or name a .jpg or .webp.", name)
    if request.compression is not None and not 0 <= request.compression <= 100:
        raise _invalid(f"compression is {request.compression}. Pass 0 to 100.", name)
    if request.background == "transparent" and suffix not in (".png", ".webp"):
        raise _invalid("A transparent background needs a .png or .webp. Name one of those.", name)
    if request.marks and request.mask is not None:
        raise _invalid("Marks and a mask cannot go together. Pass one of them.", name)
    if request.size is not None and (problem := pictures.size_problem(*request.size, animated=animated)) is not None:
        nearest = (
            "" if animated else " The nearest size that works is {}x{}.".format(*pictures.nearest_size(*request.size))
        )
        raise _invalid(f"The size {request.size[0]}x{request.size[1]} does not work: {problem}.{nearest}", name)


def _source(request: OpenAIImageRequest, image: StoredImage) -> Path | None:
    """The file to edit: the version asked for, or the image's file; None when the image is created."""
    if request.version is not None:
        return image.folder / image.version(request.version).file
    return image.path if image.path.is_file() else None


def _model(model: str | None) -> OpenAIImageModel:
    wanted = model or DEFAULT_OPENAI_IMAGE_MODEL
    for known in OPENAI_IMAGE_MODELS:
        if known.id == wanted:
            return known
    names = ", ".join(known.id for known in OPENAI_IMAGE_MODELS)
    raise _invalid(f"{wanted!r} is not an image model the tool supports. Pass one of: {names}.", None)


def _require_reference(path: Path) -> None:
    if path.suffix.lower() == ".svg":
        raise _invalid(
            f"{path} is an SVG, which cannot be sent to the Images API. Pass a PNG, JPEG, WebP, or GIF.", None
        )
    if path.suffix.lower() not in REFERENCE_SUFFIXES:
        raise _invalid(f"{path} is not an image to send. Pass a file ending in: {', '.join(REFERENCE_SUFFIXES)}.", None)
    pictures.read(path)


def _require_mask(mask: Path, picture: pictures.Picture) -> Path:
    found = pictures.read(mask)
    if found.format != "PNG" or not found.alpha:
        raise _invalid(f"The mask {mask} must be a PNG with transparency, transparent where changes may go.", None)
    if (found.width, found.height) != (picture.width, picture.height):
        raise _invalid(
            f"The mask {mask} is {found.width}x{found.height}, and the image is {picture.width}x{picture.height}. "
            "Make the mask the image's size.",
            None,
        )
    return mask


def _end_crashed_run(image: StoredImage) -> None:
    """Mark a run whose process ended without ending it, so the image's history says how it went."""
    last = image.runs[-1] if image.runs else None
    if last is not None and last.status == "running":
        last.status = "failed"
        last.error = "The process running the request ended before the request did."
        image.save_runs()


def _recorded(request: images_api.ApiRequest, folder: Path) -> dict[str, object]:
    """The request as the run's record keeps it: its settings, and the files it sent relative to the run's folder."""
    recorded = request.model_dump(mode="json", exclude_none=True, exclude={"prompt", "images", "markup", "mask"})
    recorded["images"] = [path.relative_to(folder).as_posix() for path in request.images]
    for field in ("markup", "mask"):
        path = getattr(request, field)
        if path is not None:
            recorded[field] = path.relative_to(folder).as_posix()
    return recorded


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _copy(source: Path, target: Path) -> Path:
    shutil.copyfile(source, target)
    return target


def _invalid(message: str, image: str | None) -> ImageDesignError:
    return ImageDesignError(message, "invalid-request", image)
