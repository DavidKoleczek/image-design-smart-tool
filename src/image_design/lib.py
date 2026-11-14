from contextlib import AbstractContextManager
from pathlib import Path
from typing import Literal, overload

from image_design.capabilities.app import mcp_server as app_server_module
from image_design.capabilities.app import server as app_module
from image_design.capabilities.app import settings as app_settings
from image_design.capabilities.app.mcp_server import AppServer
from image_design.capabilities.chatgpt_image import generate as chatgpt_image
from image_design.capabilities.chatgpt_image import method as chatgpt_method
from image_design.capabilities.intelligence_models import intelligence_models
from image_design.capabilities.manage_images import manage_images
from image_design.capabilities.openai_image import generate
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
    ImageSummary,
    IntelligenceModels,
    Manifest,
    Mark,
    NotGiven,
    OpenAIImageBackground,
    OpenAIImageComplexity,
    OpenAIImageQuality,
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
    )


async def draw_svg_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    canvas: tuple[int, int] | NotGiven = NOT_GIVEN,
    max_shapes: int | NotGiven | None = NOT_GIVEN,
    max_colors: int | NotGiven | None = NOT_GIVEN,
    max_bytes: int | NotGiven | None = NOT_GIVEN,
    resume_session: bool | str = False,
    agent_provider: AgentProvider | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int = 600,
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
        max_shapes: The most elements that draw; None for no limit.
        max_colors: The most distinct colors; None for no limit.
        max_bytes: The largest the SVG file may be; None for no limit.
        resume_session: True to go on in the image's last agent session, so the agent remembers earlier requests, or
            the ID of an earlier session to go on in.
        agent_provider: `codex` or `claude`; the resumed session's, else the first installed, when None.
        model: The agent provider's model; its default when None. See `list_intelligence_models`.
        reasoning_effort: The model's reasoning effort.
        timeout_seconds: How long the agent may work before it is stopped.
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
        max_shapes=max_shapes,
        max_colors=max_colors,
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
    """Every image in the directory, in name order, with its versions and how its last run went.

    An image file put in the directory by hand is listed too, with no versions until the tool changes it.
    """
    return manage_images.list_images(directory, data_directory)


def view_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> ImageSummary:
    """One image and its versions. Records it as the image viewed last, which the app opens on."""
    return manage_images.view_image(name, directory, data_directory)


def move_image(
    name: str, new_name: str, directory: Path | None = None, data_directory: Path | None = None
) -> ImageSummary:
    """Rename an image, or move it to another folder of the directory. It keeps its versions and its history.

    The new name keeps the extension, since moving an image does not convert it.
    """
    return manage_images.move_image(name, new_name, directory, data_directory)


def delete_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None:
    """Delete an image's file and everything kept for it. A run working on it is stopped first."""
    manage_images.delete_image(name, directory, data_directory)


def list_image_methods() -> ImageMethods:
    """The three ways of making an image, whether each is set up on this machine, and what each takes.

    Set up means what a method needs is installed and, for the OpenAI API, that its key is set. Whether Codex or
    Claude is signed in is checked when a request is sent.
    """
    return ImageMethods(openai=openai_method.describe(), chatgpt=chatgpt_method.describe(), svg=svg_method.describe())


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
    """Stop the run working on an image, from any process.

    A request already sent may still be billed, or counted against a plan.
    """
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

    The app shows the images in `AppServer.directory`, which `open_app` can switch. How the person set up the app,
    such as its theme and pane sizes, is theirs in every directory, kept in `app-settings.json` in their config
    directory. What they last picked for a directory's images is kept in `app/app.json` in its data directory.

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
        delete_image,
        restore_image_version,
        read_image_activity,
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
