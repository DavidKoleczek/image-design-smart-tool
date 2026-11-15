from contextlib import AbstractContextManager
from pathlib import Path
from typing import Literal, overload

from image_design.capabilities.app import folders as app_folders
from image_design.capabilities.app import mcp_server as app_server_module
from image_design.capabilities.app import server as app_module
from image_design.capabilities.app import settings as app_settings
from image_design.capabilities.app.mcp_server import AppServer
from image_design.capabilities.chatgpt_image import generate as chatgpt_image
from image_design.capabilities.chatgpt_image import method as chatgpt_method
from image_design.capabilities.design_image import design
from image_design.capabilities.design_image import method as design_method
from image_design.capabilities.design_image import steering as design_steering
from image_design.capabilities.design_image.runs import DesignRun
from image_design.capabilities.intelligence_models import intelligence_models
from image_design.capabilities.manage_images import folders as image_folders
from image_design.capabilities.manage_images import imports as image_imports
from image_design.capabilities.manage_images import manage_images
from image_design.capabilities.manage_images import relink as image_relink
from image_design.capabilities.manage_images import versions as image_versions
from image_design.capabilities.openai_image import generate
from image_design.capabilities.openai_image import key as openai_key
from image_design.capabilities.openai_image import method as openai_method
from image_design.capabilities.svg_image import check as svg_check
from image_design.capabilities.svg_image import draw as svg_draw
from image_design.capabilities.svg_image import method as svg_method
from image_design.capabilities.svg_image import steering as svg_steering
from image_design.capabilities.svg_image.runs import SvgRun
from image_design.core import manifest
from image_design.core import skill as skill_module
from image_design.intelligence.interface import Intelligence
from image_design.schemas import (
    DEFAULT_CHATGPT_REASONING_EFFORT,
    DEFAULT_REASONING_EFFORT,
    NOT_GIVEN,
    AgentProvider,
    ImageActivity,
    ImageListing,
    ImageMethods,
    ImageRelinking,
    ImageRequestPreview,
    ImageSummary,
    ImageView,
    IntelligenceModels,
    Manifest,
    Mark,
    NotGiven,
    OpenAIImageBackground,
    OpenAIImageComplexity,
    OpenAIImageQuality,
    OpenAIKeyStatus,
    ReasoningEffort,
    SvgCheck,
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
    frames: int | None = None,
    frame_ms: int | None = None,
    previews: int = 0,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
    parent: str | None = None,
) -> ImageRun:
    """Create or edit an image with an OpenAI image model through the Images API. Model-backed.

    A `name` new to `directory` creates the image, and the name of one that exists edits it, overwriting its file. Every
    image made is kept as a version in `data_directory`, which `restore_image_version` puts back. Needs the openai
    extra and an `OPENAI_API_KEY`. A request is never retried.

    Args:
        prompt: What to make, or what to change.
        name: The image's path in `directory`. Its extension sets the format: .png, .jpg, .webp, or .gif.
        directory: Where images are kept; `.image-design` in the working directory when None.
        data_directory: Where the tool keeps versions and runs; `.agents` in `directory` when None.
        references: Other images to send with the prompt, such as for a style or a subject. A PNG, JPEG, or WebP is
            sent as it is, and any other image, such as an SVG, as a PNG at its own size.
        marks: Shapes drawn over the image being edited, sent as a separate layer, to show what the prompt refers to.
        mask: An image the image's size, transparent where the model may make changes; for edits of still images.
        version: The version to edit; the one in the image's file when None.
        frame: When the image being edited is an animation, the frame to send; the first when None.
        model: `gpt-image-2.6-sunburst` when None, or `gpt-image-2.6-flare`.
        size: Width and height; the API's default when None, and the edited image's size for an edit.
        quality: The API's default when None.
        complexity: How much the model plans the image; the API's default when None.
        background: `transparent` needs a .png or .webp; the API's default when None.
        compression: 0 to 100, for a .jpg or .webp.
        frames: For a .gif, 2 to 16 frames.
        frame_ms: For a .gif, how long each frame shows, 20 to 2000.
        previews: In-progress images the API sends before the final one, 0 to 3.
        timeout_seconds: How long the request may take before it is stopped.
        origin: Who asked, such as `app`.
        detach: Run the request in a process of its own, which goes on when the caller exits.
        parent: The run of the image's agent that makes the call, from `design_image`; the one the
            IMAGE_DESIGN_PARENT environment variable names when None, which that agent's processes have.

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
        frames=frames,
        frame_ms=frame_ms,
        previews=previews,
        timeout_seconds=timeout_seconds,
        origin=origin,
        detach=detach,
        parent=parent,
    )


async def generate_chatgpt_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    version: str | None = None,
    transparent: bool = False,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_CHATGPT_REASONING_EFFORT,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
    parent: str | None = None,
) -> ImageRun:
    """Create or edit an image with the image generation built into Codex. Agentic.

    A Codex agent passes the request to its image tool. It uses the ChatGPT account Codex is signed in with, so it
    counts against that plan and needs no API key; with any other sign-in it raises before anything is sent. ChatGPT
    chooses the image model, the size, and the quality, and the image is always a PNG. Needs the codex extra.

    Args:
        prompt: What to make, or what to change. It is passed to the image tool as written.
        name: The image's path in `directory`, ending in .png. A new name creates the image, and one that exists edits
            it, overwriting its file.
        directory: Where images are kept; `.image-design` in the working directory when None.
        data_directory: Where the tool keeps versions and runs; `.agents` in `directory` when None.
        references: Other images to send with the prompt. A request sends at most five images, counting the image
            being edited and its marked copy.
        marks: Shapes drawn on a copy of the image being edited, to show what the prompt refers to. The copy is sent
            second, so with marks the references start at image 3.
        version: The version to edit; the one in the image's file when None.
        transparent: Ask for a transparent background.
        model: The Codex model that passes the request on, not the image model; Codex's default when None.
        reasoning_effort: That model's reasoning effort.
        timeout_seconds: How long the request may take before it is stopped.
        origin: Who asked, such as `app`.
        detach: Run the request in a process of its own, which goes on when the caller exits.
        intelligence: An agent to use in place of Codex, such as a fake in tests. Not with `detach`.
        parent: The run of the image's agent that makes the call, as for `generate_openai_image`.

    Returns:
        The run, once the agent has started. Its `result()` waits for the `ImageResult`, whose `usage` is None since
        the plan, not the tokens, pays for it.
    """
    return await chatgpt_image.generate_chatgpt_image(
        prompt=prompt,
        name=name,
        directory=directory,
        data_directory=data_directory,
        references=references,
        marks=marks,
        version=version,
        transparent=transparent,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        origin=origin,
        detach=detach,
        intelligence=intelligence,
        parent=parent,
    )


async def design_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    mask: Path | None = None,
    version: str | None = None,
    frame: int | None = None,
    resume_session: bool | str = False,
    image_model: str | None = None,
    size: tuple[int, int] | None = None,
    quality: OpenAIImageQuality | None = None,
    agent_provider: AgentProvider | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int | None = None,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
) -> DesignRun:
    """Create or edit an image with an agent that writes the image calls and makes them. Agentic.

    The agent has a shell in the working directory and drives this tool's own commands, with skills for the craft: it
    looks at the image and its history, and writes each call to the image model it is given and makes it, with
    `generate_openai_image` or `generate_chatgpt_image`, choosing every other argument of the call itself. It may make
    several images, write scripts for exact work, and read the project. Needs the codex or claude extra, and the method
    of the image model set up.

    Args:
        prompt: What the person wants, for the agent; not what an image model receives.
        name: The image's path in `directory`, not an SVG. A new name creates the image.
        directory: Where images are kept; `.image-design` in the working directory when None.
        data_directory: Where the tool keeps versions and runs; `.agents` in `directory` when None.
        references: Images that go with the request, which the agent decides how to use.
        marks: Shapes the person drew on the image, which the agent is shown and may pass on.
        mask: An image the image's size, transparent where changes may go, which the agent may pass on.
        version: The version the request is about; the image's file when None.
        frame: For an animation, the frame the request is about.
        resume_session: True to go on in the image's agent's last session, or the ID of an earlier one. A new session
            is told the image's history; one that goes on is told what happened since its last turn.
        image_model: What the agent makes its images with: an OpenAI image model, through `generate_openai_image`,
            or `chatgpt`, through `generate_chatgpt_image`; its calls to any other are refused. The default OpenAI image
            model when that method is set up, else `chatgpt`, when None. See `list_image_methods`.
        size, quality: What the person wants the image's calls to pass, which the agent is told; its own choice when
            None. Only with an OpenAI image model, since ChatGPT chooses its own.
        agent_provider: `codex` or `claude`; the resumed session's, else the first installed, when None.
        model: The agent provider's model; its default when None. See `list_intelligence_models`.
        reasoning_effort: The model's reasoning effort.
        timeout_seconds: How long the agent may work before it is stopped; None for no limit.
        origin: Who asked, such as `app`.
        detach: Run the agent in a process of its own, which goes on when the caller exits.
        intelligence: An agent to use in place of the agent provider's, such as a fake in tests. Not with `detach`.

    Returns:
        The run, once the agent's run is kept. Its `events()` yields what the agent says and the tools it calls,
        `steer()` sends it a message, and `result()` waits for the `ImageResult`. The calls it makes are runs of their
        own, which name it as their `parent`, and `read_image_activity` has them with it.
    """
    image_model = design_method.image_model(image_model, name, openai_method.describe(), chatgpt_method.describe())
    return await design.design_image(
        prompt=prompt,
        name=name,
        image_model=image_model,
        size=size,
        quality=quality,
        directory=directory,
        data_directory=data_directory,
        references=references,
        marks=marks,
        mask=mask,
        version=version,
        frame=frame,
        resume_session=resume_session,
        agent_provider=agent_provider,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        origin=origin,
        detach=detach,
        intelligence=intelligence,
    )


def steer_image(
    name: str,
    message: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    origin: str | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
) -> None:
    """Send a message to the agent working on an image while it works, from any process.

    The process running the agent delivers it within a second or so. `references` are shown to the agent with it, and
    `marks` are drawn on the image's file.
    """
    design_steering.steer_image(name, message, directory, data_directory, origin, references, marks)


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
    """What `generate_openai_image` would send for the same arguments, without sending it or keeping anything.

    The arguments are checked as a request's are, so what a request would raise for, this raises for. It needs
    neither the openai extra nor a key.

    Returns:
        The prompt as the model receives it, the images in the order they are sent, and each parameter the request
        sets by the name the Images API gives it. On an edit that includes the size worked out from the image.
    """
    return generate.preview_openai_image_request(
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
        frames=frames,
        frame_ms=frame_ms,
        previews=previews,
    )


def preview_chatgpt_image_request(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    version: str | None = None,
    transparent: bool = False,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_CHATGPT_REASONING_EFFORT,
) -> ImageRequestPreview:
    """What `generate_chatgpt_image` would send for the same arguments, without sending it or keeping anything.

    The arguments are checked as a request's are. Whether Codex is installed and signed in with ChatGPT is not, since
    no agent is started.

    Returns:
        The prompt as the image tool receives it, the images in the order they are sent, whether a transparent
        background is asked for, and the Codex model and reasoning effort that would carry the request.
    """
    return chatgpt_image.preview_chatgpt_image_request(
        prompt=prompt,
        name=name,
        directory=directory,
        data_directory=data_directory,
        references=references,
        marks=marks,
        version=version,
        transparent=transparent,
        model=model,
        reasoning_effort=reasoning_effort,
    )


async def draw_svg_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    canvas: tuple[int, int] | NotGiven = NOT_GIVEN,
    max_bytes: int | NotGiven | None = NOT_GIVEN,
    resume_session: bool | str = False,
    agent_provider: AgentProvider | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int | None = 600,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
) -> SvgRun:
    """Create or edit an SVG image with an agent that draws it with code. Agentic.

    The agent writes image.py, a script with inline dependencies that writes the SVG, runs it with uv, renders the SVG
    with resvg, looks at the render, and fixes what does not match the request. image.py is kept with the image's data
    and committed with the project, so the drawing can go on changing. Needs uv, and the codex or claude extra.

    Args:
        prompt: What to draw, or what to change.
        name: The image's path in `directory`, ending in .svg. A new name creates the image, and one that exists edits
            it, overwriting its file. To redraw another image as an SVG, pass it in `references` under a new name.
        directory: Where images are kept; `.image-design` in the working directory when None.
        data_directory: Where the tool keeps versions and runs; `.agents` in `directory` when None.
        references: Images shown to the agent with the prompt, in any format.
        marks: Shapes drawn on the render the agent is shown, to show what the prompt refers to. The agent is also
            told which named parts of the drawing are under each.
        canvas: The drawing's width and height. The agent is told the budgets, and `check_svg_image` measures them.
            A new drawing defaults to 512 by 512, and an edit keeps the earlier value of each budget left out.
        max_bytes: The largest the SVG file may be; None for no limit.
        resume_session: True to go on in the image's last agent session, so the agent remembers earlier requests, or
            the ID of an earlier session to go on in.
        agent_provider: `codex` or `claude`; the resumed session's, else the first installed, when None.
        model: The agent provider's model; its default when None. See `list_intelligence_models`.
        reasoning_effort: The model's reasoning effort.
        timeout_seconds: How long the agent may work before it is stopped; None for no limit.
        origin: Who asked, such as `app`.
        detach: Run the agent in a process of its own, which goes on when the caller exits.
        intelligence: An agent to use in place of the agent provider's, such as a fake in tests. Not with `detach`.

    Returns:
        The run, once the agent has started. Its `events()` yields each step, including what the agent says and the
        tools it calls, and a `preview` for each render it builds; `steer()` sends the agent a message; `result()`
        waits for the `ImageResult`.
    """
    return await svg_draw.draw_svg_image(
        prompt=prompt,
        name=name,
        directory=directory,
        data_directory=data_directory,
        references=references,
        marks=marks,
        canvas=canvas,
        max_bytes=max_bytes,
        resume_session=resume_session,
        agent_provider=agent_provider,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        origin=origin,
        detach=detach,
        intelligence=intelligence,
    )


def steer_svg_image(
    name: str,
    message: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    origin: str | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
) -> None:
    """Send a message to the agent drawing an SVG image while it works, from any process.

    The process running the drawing delivers it within a second or so. `references` are shown to the agent with it,
    and `marks` are drawn on the agent's latest render.
    """
    svg_steering.steer_svg_image(name, message, directory, data_directory, origin, references, marks)


def check_svg_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> SvgCheck:
    """Measure an SVG image against its budgets: its shapes, colors, bytes, named parts, and what resvg skips.

    It only reports; nothing passes or fails. An SVG the tool did not draw is measured against its own size.
    """
    return svg_check.check_svg_image(name, directory, data_directory)


def export_svg_image(
    name: str,
    output: Path,
    scale: float = 1,
    version: str | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
) -> Path:
    """Render an SVG image, or one of its versions, to a .png, .jpg, or .webp at `scale` times its size.

    A .jpg has no transparency, so what is see-through shows white. Returns the file written.
    """
    return svg_check.export_svg_image(name, output, scale, version, directory, data_directory)


def list_images(directory: Path | None = None, data_directory: Path | None = None) -> ImageListing:
    """Every image in the directory, in name order, with its versions and how its last run went, and every folder.

    An image file put in the directory by hand is listed too, with no versions until the tool changes it.
    """
    return manage_images.list_images(directory, data_directory)


def view_image(
    name: str,
    version: str | None = None,
    frames_output: Path | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
) -> ImageView:
    """One image and its versions, with its file or one of its versions frame by frame. A still image has one frame.

    Args:
        name: The image's path in `directory`.
        version: The version to view frame by frame, such as v2; the image's file when None.
        frames_output: A folder to write each frame of what is viewed to as a PNG, named `frame-<index>.png`. It is
            made if need be.
        directory: Where images are kept; `.image-design` in the working directory when None.
        data_directory: Where the tool keeps versions and runs; `.agents` in `directory` when None.

    Returns:
        The image's summary, and in `viewed` the size of what is viewed and its frames in order, each with how long it
        shows. A frame's `index` is what `frame` names in `generate_openai_image`.
    """
    return manage_images.view_image(name, version, frames_output, directory, data_directory)


def move_image(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary:
    """Rename an image, or move it to another folder of the directory. It keeps its versions and its history.

    The new name keeps the extension, since moving an image does not convert it. A name that is taken is refused, or
    with `numbered` becomes the first free one of `name (2)`, `name (3)`, and so on, which the summary returned has.
    """
    return manage_images.move_image(name, new_name, directory, data_directory, numbered)


def copy_image(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary:
    """Make another image under `new_name`, with a copy of the image's file and of everything kept for it: its
    versions, its runs, and for a drawn SVG its script and sessions. The two are separate images from then on.

    The new name keeps the extension. A name that is taken is refused, or with `numbered` becomes the first free one
    of `name (2)`, `name (3)`, and so on. An image a run is working on is refused until the run ends.
    """
    return manage_images.copy_image(name, new_name, directory, data_directory, numbered)


def import_image(
    path: Path,
    name: str | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary:
    """Bring an image file from anywhere on this machine into the directory as a new image.

    The file is copied and left as it is, and the copy is the image's first version, so a later edit can go back to
    it. A PNG, JPEG, WebP, GIF, or SVG is kept as it is, and any other still image, such as a BMP or TIFF, as a PNG.

    Args:
        path: The image file to bring in.
        name: The image's path in `directory`. It takes the file's own name at the top of the directory when None,
            and the file's name in a folder when it ends in a slash, such as `photos/`. A file already in the
            directory under that name stays where it is and is kept from then on.
        directory: Where images are kept; `.image-design` in the working directory when None.
        data_directory: Where the tool keeps versions and runs; `.agents` in `directory` when None.
        numbered: Take the first free one of `name (2)`, `name (3)`, and so on when the name is taken, rather than
            refuse.
    """
    return image_imports.import_image(path, name, directory, data_directory, numbered)


def add_image_version(
    name: str, path: Path, directory: Path | None = None, data_directory: Path | None = None, parent: str | None = None
) -> ImageSummary:
    """Keep a file as the next version of an image, such as a crop or a composite a script made, and put it in the
    image's file. The file is copied and left as it is.

    It has to be in the image's format, except that any still image becomes a PNG for a .png. `parent` is the run of
    the image's agent that made it, which the version names; the one the IMAGE_DESIGN_PARENT environment variable names
    when None.
    """
    return image_versions.add_image_version(name, path, directory, data_directory, parent)


def delete_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None:
    """Delete an image's file and everything kept for it. A run working on it is stopped first."""
    manage_images.delete_image(name, directory, data_directory)


def create_folder(
    name: str, directory: Path | None = None, data_directory: Path | None = None, numbered: bool = False
) -> str:
    """Make a folder in the directory, and any above it, and return its name. A folder stays until it is deleted.

    A name that is taken is refused, or with `numbered` becomes the first free one of `name (2)`, `name (3)`, and so
    on.
    """
    return image_folders.create_folder(name, directory, data_directory, numbered)


def move_folder(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> str:
    """Rename a folder, or move it into another, with everything in it, and return its name.
    Its images keep their versions and their history.

    It is refused while a run works on an image in it. A name that is taken is refused, or with `numbered` becomes
    the first free one of `name (2)`, `name (3)`, and so on.
    """
    return image_folders.move_folder(name, new_name, directory, data_directory, numbered)


def delete_folder(name: str, directory: Path | None = None, data_directory: Path | None = None) -> list[str]:
    """Delete every image in a folder as `delete_image` does, then the folder and the folders in it.

    Returns what is left, by paths in the directory: the files in it that are not images, which the tool never
    deletes, so the folder stays to hold them. Empty when the folder is gone.
    """
    return image_folders.delete_folder(name, directory, data_directory)


def relink_images(
    likely: list[str] | None = None, directory: Path | None = None, data_directory: Path | None = None
) -> ImageRelinking:
    """Find the images whose files were moved or renamed outside the tool, and keep each under the name its file has.

    An image is relinked when a file the tool keeps nothing for holds exactly what the image's current version does.
    A file that only has the image's file name, as after it was changed and then moved, is reported as likely and
    left alone.

    Args:
        likely: The images to relink to their likely file as well, by the names they are kept under.
        directory: Where images are kept; `.image-design` in the working directory when None.
        data_directory: Where the tool keeps versions and runs; `.agents` in `directory` when None.

    Returns:
        What was relinked, what is likely, and the images that still have no file.
    """
    return image_relink.relink_images(likely, directory, data_directory)


def list_image_methods() -> ImageMethods:
    """The three ways of making an image and the agent that directs the first two, whether each is set up on this
    machine, and what each takes.

    Set up means what a method needs is installed and, for the OpenAI API, that its key is set. Whether Codex or
    Claude is signed in is checked when a request is sent.
    """
    openai, chatgpt = openai_method.describe(), chatgpt_method.describe()
    return ImageMethods(
        openai=openai, chatgpt=chatgpt, svg=svg_method.describe(), design=design_method.describe(openai, chatgpt)
    )


def openai_api_key_status() -> OpenAIKeyStatus:
    """Where the OpenAI API key that `generate_openai_image` is billed to comes from, without the key itself.

    The `OPENAI_API_KEY` environment variable wins. Without it, the key saved with `save_openai_api_key` is used.
    """
    return openai_key.status()


def save_openai_api_key(key: str) -> None:
    """Keep an OpenAI API key in the platform's credential store, for when the environment has none.

    That is Windows Credential Manager, the macOS Keychain, or the Secret Service on Linux. The key is written to no
    file of the tool. Raises `ImageDesignError` when the machine has no such store.
    """
    openai_key.save(key)


def clear_openai_api_key() -> None:
    """Forget the OpenAI API key saved with `save_openai_api_key`, if there is one."""
    openai_key.clear()


def restore_image_version(
    name: str, version: str, directory: Path | None = None, data_directory: Path | None = None
) -> ImageSummary:
    """Put an earlier version of an image back in its file, keeping the file first if it was changed by hand.

    For an SVG the tool drew, the version's image.py goes back in place too.
    """
    return manage_images.restore_image_version(name, version, directory, data_directory)


def read_image_activity(
    name: str, directory: Path | None = None, data_directory: Path | None = None, after: str | None = None
) -> ImageActivity:
    """The history of an image: each run's request, what its agent did, and how it ended, as the run's events.

    Pass the `cursor` of an earlier call as `after` to get only what happened since.
    """
    return manage_images.read_image_activity(name, directory, data_directory, after)


def cancel_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None:
    """Stop the run working on an image, from any process."""
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


def app_server(directory: Path | None = None, data_directory: Path | None = None) -> AppServer:
    """The app's MCP server: the tool that opens the app, the tools its view calls, and the view as an MCP App.

    Serve `AppServer.server` over any MCP transport. `AppServer.open` serves the browser host page, which renders the
    view for agents that cannot embed it and reaches the same server at its own `/mcp`. `AppServer.close` stops it.

    The app shows the images in `AppServer.directory`, which `open_app` can switch, and `AppServer.show` or
    `open_app` brings an image up in it. How the person set up the app, such as its theme and pane sizes, is theirs
    in every directory, kept in `app-settings.json` in their config directory. What they last picked for a
    directory's images is kept in `app/app.json` in its data directory.

    Args:
        directory: Where the images the app shows are kept; `.image-design` in the working directory when omitted.
        data_directory: Where the tool keeps their versions and runs; `.agents` in the directory when omitted.
    """
    return app_server_module.AppServer(
        skill_module.DISTRIBUTION,
        version(),
        directory,
        data_directory,
        list_images,
        view_image,
        move_image,
        copy_image,
        import_image,
        delete_image,
        create_folder,
        move_folder,
        delete_folder,
        relink_images,
        restore_image_version,
        read_image_activity,
        list_image_methods,
        generate_openai_image,
        generate_chatgpt_image,
        preview_openai_image_request,
        preview_chatgpt_image_request,
        draw_svg_image,
        steer_svg_image,
        design_image,
        steer_image,
        export_svg_image,
        cancel_image,
        app_folders.choose_files,
        app_folders.choose_folder,
        app_folders.choose_save_path,
        openai_api_key_status,
        save_openai_api_key,
        clear_openai_api_key,
        app_folders.ask_secret,
        app_settings.settings_path(),
    )


def app_view() -> str:
    """The app's view, an MCP App: the HTML a host renders inline, and the one the browser host page renders."""
    return app_module.view()


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
