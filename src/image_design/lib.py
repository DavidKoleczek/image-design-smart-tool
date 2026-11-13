from contextlib import AbstractContextManager
from pathlib import Path
from typing import Literal, overload

from image_design.capabilities.intelligence_models import intelligence_models
from image_design.capabilities.manage_images import manage_images
from image_design.capabilities.openai_image import generate
from image_design.core import manifest
from image_design.core import skill as skill_module
from image_design.schemas import (
    ImageSummary,
    IntelligenceModels,
    Manifest,
    Mark,
    OpenAIImageBackground,
    OpenAIImageComplexity,
    OpenAIImageQuality,
)
from image_design.shared.images import runs
from image_design.shared.images.runs import ImageRun


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
    """Create or edit an image with an OpenAI image model through the Images API. Model-backed.

    A `name` new to `directory` creates the image, and the name of one that exists edits it, overwriting its file. Every
    image made is kept as a version in `data_directory`, which `restore_image_version` puts back. Needs the openai
    extra and an `OPENAI_API_KEY`; each request is billed to that key, and is never retried.

    Args:
        prompt: What to make, or what to change.
        name: The image's path in `directory`. Its extension sets the format: .png, .jpg, .webp, or .gif.
        directory: Where images are kept; `.image-design` in the working directory when None.
        data_directory: Where the tool keeps versions and runs; `.agents` in `directory` when None.
        references: Other images to send with the prompt, such as for a style or a subject.
        marks: Shapes drawn over the image being edited, sent as a separate layer, to show what the prompt refers to.
        mask: A PNG the image's size, transparent where the model may make changes; for edits of still images.
        version: The version to edit; the one in the image's file when None.
        frame: When the image being edited is an animation, the frame to send; the first when None.
        model: `gpt-image-2.6-sunburst` when None, or `gpt-image-2.6-flare`.
        size: Width and height; the API's default when None, and the edited image's size for an edit.
        quality: The API's default when None.
        complexity: How much the model plans the image; the API's default when None.
        background: `transparent` needs a .png or .webp; the API's default when None.
        compression: 0 to 100, for a .jpg or .webp.
        count: How many images to make, 1 to 10; each is kept as a version, and the first goes in the file.
        frames: For a .gif, 2 to 16 frames.
        frame_ms: For a .gif, how long each frame shows, 20 to 2000.
        previews: In-progress images the API sends before the final one, 0 to 3; only with a count of 1.
        timeout_seconds: How long the request may take before it is stopped.
        origin: Who asked, such as `app`.
        detach: Run the request in a process of its own, which goes on when the caller exits.

    Returns:
        The run, once the request is sent. Its `events()` yields each step, including `preview` events with the path of
        an in-progress image, and `result()` waits for the `ImageResult`.
    """
    return await generate.generate_openai_image(
        prompt=prompt,
        name=name,
        directory=directory,
        data_directory=data_directory,
        references=references,
        marks=marks,
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
        detach=detach,
    )


def restore_image_version(
    name: str, version: str, directory: Path | None = None, data_directory: Path | None = None
) -> ImageSummary:
    """Put an earlier version of an image back in its file, keeping the file first if it was changed by hand."""
    return manage_images.restore_image_version(name, version, directory, data_directory)


def cancel_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None:
    """Stop the run working on an image, from any process. A request already sent may still be billed."""
    manage_images.cancel_image(name, directory, data_directory)


def stopped_by_signals(run: ImageRun) -> AbstractContextManager[None]:
    """While in the block, stop the run on every signal that ends this process, such as Ctrl+C or its console closing.

    For a process that waits on a run it started, so nothing the run started outlives it. Each signal's handler is put
    back after.
    """
    return runs.stopped_by_signals(run)


def load_manifest() -> Manifest:
    """The tool's manifest as structured data, read from the SMART_TOOL.md shipped inside the package."""
    return manifest.load_manifest()


def skill(capability: str | None = None) -> str:
    """The tool's skill, or the named capability's own skill, wrapped so a reader knows where the tool's files are."""
    return skill_module.skill(capability)


def version() -> str:
    """The installed package's version, from its metadata."""
    return skill_module.version()


@overload
def list_intelligence_models(structured: Literal[False] = False) -> str: ...


@overload
def list_intelligence_models(structured: Literal[True]) -> IntelligenceModels: ...


def list_intelligence_models(structured: bool = False) -> str | IntelligenceModels:
    """The AI models to pick from for an agentic capability.

    The models are those of the installed agent providers; a capability also takes any other model its agent provider
    knows by name.

    Args:
        structured: Return `IntelligenceModels` instead of the text, for code that reads the fields.

    Returns:
        By default, text for an agent to read: the default as the flags to pass, then one model per line.
    """
    listing = intelligence_models.list_intelligence_models()
    return listing if structured else intelligence_models.describe(listing)
