"""Create or edit an image with an OpenAI image model through the Images API."""

from datetime import UTC, datetime
from functools import partial
import os
from pathlib import Path, PurePosixPath
import sys
from typing import NamedTuple

from pydantic import BaseModel

from image_design.capabilities.openai_image import images_api
from image_design.schemas import (
    CHATGPT_IMAGE_MODEL,
    DEFAULT_OPENAI_IMAGE_MODEL,
    IMAGE_FORMATS,
    OPENAI_IMAGE_MODELS,
    SVG_SUFFIX,
    ImageRequestImage,
    ImageRequestPreview,
    ImageRunRecord,
    Mark,
    OpenAIImageBackground,
    OpenAIImageComplexity,
    OpenAIImageModel,
    OpenAIImageQuality,
)
from image_design.shared.images import calls, pictures
from image_design.shared.images import detach as detaching
from image_design.shared.images import marks as marking
from image_design.shared.images.requests import (
    Reference,
    claimed,
    edited_version,
    invalid,
    previewed_source,
    source,
    validated,
    write,
    write_references,
)
from image_design.shared.images.requests import references as sent_references
from image_design.shared.images.runs import DetachedRun, ImageRun, InProcessRun
from image_design.shared.images.store import StoredImage, directories, image_name, new_run_id

# What starts a detached run, given its request on stdin. Tests swap it for a command that fakes the API.
BACKGROUND_COMMAND = [sys.executable, "-m", "image_design.capabilities.openai_image.background"]
# The Images API's limits, from https://developers.openai.com/api/reference/resources/images/methods/edit and
# https://developers.openai.com/api/docs/guides/image-generation.
MAX_INPUT_IMAGES = 16
MAX_PREVIEWS = 3
FRAMES = (2, 16)
FRAME_MS = (20, 2000)
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
    frames: int | None = None
    frame_ms: int | None = None
    previews: int = 0
    timeout_seconds: int = 600
    origin: str | None = None
    parent: str | None = None


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
    frames: int | None = None,
    frame_ms: int | None = None,
    previews: int = 0,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
    parent: str | None = None,
) -> ImageRun:
    """Start creating the image named `name`, or editing it when it exists, and return its run once it is sent."""
    request = validated(
        OpenAIImageRequest,
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
        frames=frames,
        frame_ms=frame_ms,
        previews=previews,
        timeout_seconds=timeout_seconds,
        origin=origin,
        parent=parent,
    )
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
    return await detaching.detach(BACKGROUND_COMMAND, absolute, root, data, DetachedRun)


def preview_openai_image_request(
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
    frames: int | None = None,
    frame_ms: int | None = None,
    previews: int = 0,
) -> ImageRequestPreview:
    """What `generate_openai_image` would send for these arguments, checked the same way, with nothing sent or kept."""
    request = validated(
        OpenAIImageRequest,
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
        frames=frames,
        frame_ms=frame_ms,
        previews=previews,
    )
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    image = image_name(request.name, root, data)
    suffix = PurePosixPath(image).suffix.lower()
    chosen = _model(request.model)
    sent_references(request.references)
    edited = previewed_source(root, data, image, request.version)
    plan = _plan(request, image, edited, suffix)
    if request.mask is not None and plan.picture is not None:
        _mask(request.mask, plan.picture)
    images = [ImageRequestImage(role="source", path=edited)] if edited is not None else []
    images.extend(ImageRequestImage(role="reference", path=path) for path in request.references)
    if request.marks:
        images.append(ImageRequestImage(role="marks", path=None))
    if request.mask is not None:
        images.append(ImageRequestImage(role="mask", path=request.mask))
    return ImageRequestPreview(
        method="openai",
        name=image,
        edits=edited is not None,
        prompt=plan.prompt,
        added=plan.prompt[len(request.prompt) :].strip() or None,
        images=images,
        parameters=images_api.parameters(_api_request(request, plan, chosen, suffix, [], None, None)),
    )


async def start(request: OpenAIImageRequest) -> InProcessRun:
    """Check the request, keep what it sends, and start sending it."""
    _require_arguments(request)
    root, data = directories(request.directory, request.data_directory)
    name = image_name(request.name, root, data)
    suffix = PurePosixPath(name).suffix.lower()
    parent = calls.parent_of(root, data, request.parent, name)
    given = calls.given(parent)
    # An agent's call that names no model goes to the one the agent was given.
    model = _model(request.model or (None if given == CHATGPT_IMAGE_MODEL else given))
    calls.require_given(parent, model.id, name)
    images_api.preflight()
    sent = sent_references(request.references)
    run_id = new_run_id()
    with claimed(root, data, name, run_id) as (image, lock):
        folder = image.run_folder(run_id)
        api_request = _prepare(request, sent, image, suffix, model, folder / "inputs")
        version = edited_version(image, request.version)
        run = ImageRunRecord(
            id=run_id,
            method="openai",
            prompt=request.prompt,
            request={**_recorded(api_request, folder), **({"version": version} if version else {})},
            origin=request.origin,
            pid=os.getpid(),
            started=datetime.now(UTC),
        )
        calls.record(run, parent, image)
        image.runs.append(run)
        image.save_runs()
        work = partial(images_api.send, api_request, model, request.timeout_seconds)
        return InProcessRun(image, run, work, request.timeout_seconds, lock, suffix)


class _Plan(NamedTuple):
    """What a request sends, worked out from what was asked and the image being edited, before anything is written."""

    edited: Path | None
    picture: pictures.Picture | None
    frame: int
    size: tuple[int, int] | None
    frames: int | None
    frame_ms: int | None
    prompt: str


def _plan(request: OpenAIImageRequest, name: str, edited: Path | None, suffix: str) -> _Plan:
    """Work out what the request sends to edit the file `edited`, or to create the image when there is none, once it
    is known the API can take it."""
    animated = suffix == ".gif"
    if edited is None:
        given = {"marks": bool(request.marks), "a mask": request.mask is not None, "frame": request.frame is not None}
        what = next((what for what, used in given.items() if used), None)
        if what is not None:
            raise invalid(
                f"There is no image named {name} to edit, so {what} cannot be used. Leave it out to create the "
                "image, or name an image that exists.",
                name,
            )
    picture = pictures.read(edited) if edited is not None else None
    if picture is not None:
        if request.frame is not None and not 0 <= request.frame < picture.frames:
            raise invalid(
                f"{name} has {picture.frames} frame(s), so frame {request.frame} does not exist. Pass a frame "
                f"from 0 to {picture.frames - 1}.",
                name,
            )
        if request.mask is not None and (picture.frames > 1 or animated):
            raise invalid("A mask works only for edits of still images. Leave out the mask.", name)
    if len(request.references) + (edited is not None) > MAX_INPUT_IMAGES:
        raise invalid(
            f"A request can send at most {MAX_INPUT_IMAGES} images, counting the image being edited. Send fewer "
            "references.",
            name,
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
    prompt = request.prompt
    if request.marks:
        marking.require_marks(request.marks)
        prompt = f"{prompt}\n\n{MARKS_NOTE}\n{marking.describe(request.marks)}"
    return _Plan(edited, picture, request.frame or 0, size, frames, frame_ms, prompt)


def _prepare(
    request: OpenAIImageRequest,
    references: list[Reference],
    image: StoredImage,
    suffix: str,
    model: OpenAIImageModel,
    inputs: Path,
) -> images_api.ApiRequest:
    """The request to send, with the files it sends copied into `inputs`."""
    plan = _plan(request, image.name, source(image, request.version), suffix)
    inputs.mkdir(parents=True, exist_ok=True)
    sent: list[Path] = []
    if plan.edited is not None:
        sent.append(write(inputs / "image.png", pictures.frame_png(plan.edited, plan.frame)))
    sent.extend(write_references(references, inputs))
    markup = None
    if request.marks and plan.picture is not None:
        markup = write(inputs / "marks.png", marking.layer(request.marks, plan.picture.width, plan.picture.height))
    mask = None
    if request.mask is not None and plan.picture is not None:
        mask = write(inputs / "mask.png", _mask(request.mask, plan.picture))
    return _api_request(request, plan, model, suffix, sent, markup, mask)


def _api_request(
    request: OpenAIImageRequest,
    plan: _Plan,
    model: OpenAIImageModel,
    suffix: str,
    images: list[Path],
    markup: Path | None,
    mask: Path | None,
) -> images_api.ApiRequest:
    return images_api.ApiRequest(
        model=model.id,
        prompt=plan.prompt,
        images=images,
        markup=markup,
        mask=mask,
        size=plan.size,
        quality=request.quality,
        complexity=request.complexity,
        background=request.background,
        output_format=IMAGE_FORMATS[suffix],
        compression=request.compression,
        frames=plan.frames,
        frame_ms=plan.frame_ms,
        previews=request.previews,
    )


def _require_arguments(request: OpenAIImageRequest) -> None:
    """Raise for arguments the API would refuse, before anything is kept or sent."""
    suffix = PurePosixPath(request.name.replace("\\", "/")).suffix.lower()
    animated = suffix == ".gif"
    name = request.name
    if suffix == SVG_SUFFIX:
        raise invalid(
            f"{name!r} does not end in an image format OpenAI image models make. End it in one of: "
            f"{', '.join(IMAGE_FORMATS)}, or draw an SVG with draw_svg_image.",
            name,
        )
    if not request.prompt.strip():
        raise invalid("The prompt is empty. Say what to make, or what to change.", name)
    if not 0 <= request.previews <= MAX_PREVIEWS:
        raise invalid(f"previews is {request.previews}. Ask for 0 to {MAX_PREVIEWS} previews.", name)
    if request.previews and animated:
        raise invalid("A .gif has no previews. Leave out previews.", name)
    if request.timeout_seconds <= 0:
        raise invalid("timeout_seconds must be more than 0.", name)
    if not animated and (request.frames is not None or request.frame_ms is not None):
        raise invalid("frames and frame_ms are for a .gif. Leave them out, or name a .gif.", name)
    if request.frames is not None and not FRAMES[0] <= request.frames <= FRAMES[1]:
        raise invalid(f"frames is {request.frames}. A .gif can have {FRAMES[0]} to {FRAMES[1]} frames.", name)
    if request.frame_ms is not None and not FRAME_MS[0] <= request.frame_ms <= FRAME_MS[1]:
        raise invalid(f"frame_ms is {request.frame_ms}. A frame lasts {FRAME_MS[0]} to {FRAME_MS[1]} ms.", name)
    if request.compression is not None and suffix not in (".jpg", ".webp"):
        raise invalid("compression is for a .jpg or .webp. Leave it out, or name a .jpg or .webp.", name)
    if request.compression is not None and not 0 <= request.compression <= 100:
        raise invalid(f"compression is {request.compression}. Pass 0 to 100.", name)
    if request.background == "transparent" and suffix not in (".png", ".webp"):
        raise invalid("A transparent background needs a .png or .webp. Name one of those.", name)
    if request.marks and request.mask is not None:
        raise invalid("Marks and a mask cannot go together. Pass one of them.", name)
    if request.size is not None and (problem := pictures.size_problem(*request.size, animated=animated)) is not None:
        nearest = (
            "" if animated else " The nearest size that works is {}x{}.".format(*pictures.nearest_size(*request.size))
        )
        raise invalid(f"The size {request.size[0]}x{request.size[1]} does not work: {problem}.{nearest}", name)


def _model(model: str | None) -> OpenAIImageModel:
    wanted = model or DEFAULT_OPENAI_IMAGE_MODEL
    for known in OPENAI_IMAGE_MODELS:
        if known.id == wanted:
            return known
    names = ", ".join(known.id for known in OPENAI_IMAGE_MODELS)
    raise invalid(f"{wanted!r} is not an image model the tool supports. Pass one of: {names}.", None)


def _mask(mask: Path, picture: pictures.Picture) -> bytes:
    """The mask as the PNG the API takes, once it is known to fit the image."""
    content = pictures.png(mask)
    found = pictures.describe(content)
    if found is not None and (found.width, found.height) != (picture.width, picture.height):
        raise invalid(
            f"The mask {mask} is {found.width}x{found.height}, and the image is {picture.width}x{picture.height}. "
            "Make the mask the image's size.",
            None,
        )
    if not pictures.transparent(content):
        raise invalid(f"The mask {mask} has no transparent area. Make it transparent where changes may go.", None)
    return content


def _recorded(request: images_api.ApiRequest, folder: Path) -> dict[str, object]:
    """The request as the run's record keeps it: its settings, and the files it sent relative to the run's folder."""
    recorded = request.model_dump(mode="json", exclude_none=True, exclude={"prompt", "images", "markup", "mask"})
    recorded["images"] = [path.relative_to(folder).as_posix() for path in request.images]
    for field in ("markup", "mask"):
        path = getattr(request, field)
        if path is not None:
            recorded[field] = path.relative_to(folder).as_posix()
    return recorded
