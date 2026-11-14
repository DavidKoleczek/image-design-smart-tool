from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, NamedTuple, get_args

from pydantic import BaseModel, Field

ReasoningEffort = Literal["low", "medium", "high", "xhigh", "max", "ultra"]
AgentProvider = Literal["codex", "claude"]
# Also the order an agent provider is picked in when none is named.
AGENT_PROVIDERS: tuple[AgentProvider, ...] = ("codex", "claude")

DEFAULT_INTELLIGENCE_MODELS: dict[AgentProvider, str] = {
    "codex": "gpt-6.1-sol",
    "claude": "claude-opus-5-5",
}
DEFAULT_REASONING_EFFORT: ReasoningEffort = "medium"
REASONING_EFFORTS: tuple[ReasoningEffort, ...] = get_args(ReasoningEffort)
# The reasoning efforts each agent provider takes, for a model the tool does not list.
PROVIDER_REASONING_EFFORTS: dict[AgentProvider, tuple[ReasoningEffort, ...]] = {
    "codex": REASONING_EFFORTS,
    "claude": ("low", "medium", "high", "xhigh", "max"),
}

SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"
SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class ImageDesignError(Exception):
    """Raised for any failure the library can name and explain how to fix.

    `reason` is a stable name for the failure, for code that acts on it, and `image` the image it concerns.
    """

    def __init__(self, message: str, reason: str | None = None, image: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.image = image


# region: Manifest


class ManifestRequirement(BaseModel):
    """One environment prerequisite; `install` references documentation, never a command."""

    name: str
    purpose: str
    install: str
    optional: bool = False


class Manifest(BaseModel):
    """The structured form of SMART_TOOL.md."""

    smart_tool_format: int
    name: str = Field(pattern=SLUG_PATTERN)
    version: str = Field(pattern=SEMVER_PATTERN)
    description: str
    use_cases: list[str]
    platforms: list[str]
    requires: list[ManifestRequirement] = Field(default_factory=list)
    body: str = Field(description="The Markdown below the frontmatter: the skill `--help` renders")


# endregion

# region: Skill


class Capability(NamedTuple):
    """One capability of the tool: its line in the skill's capability list and its own skill."""

    name: str
    summary: str
    model_backed: bool
    skill: str  # the capability's skill body, a Markdown file relative to the skill directory
    resources: tuple[str, ...] = ()  # the files that skill refers to, relative to the skill directory


# endregion

# region: Intelligence models


class IntelligenceModel(BaseModel):
    """One AI model an agentic capability can run on, and the reasoning efforts it takes."""

    agent_provider: AgentProvider
    id: str = Field(description="The agent provider's own model ID")
    label: str
    reasoning_efforts: list[ReasoningEffort]
    vision: bool = Field(description="Whether the model can be shown images")


def _model(agent_provider: AgentProvider, id: str, label: str) -> IntelligenceModel:
    efforts = list(PROVIDER_REASONING_EFFORTS[agent_provider])
    return IntelligenceModel(agent_provider=agent_provider, id=id, label=label, reasoning_efforts=efforts, vision=True)


# The models agentic capabilities support, in the order they are listed.
INTELLIGENCE_MODELS: tuple[IntelligenceModel, ...] = (
    _model("codex", "gpt-6.1-sol", "GPT-6.1 Sol"),
    _model("codex", "gpt-6.1-terra", "GPT-6.1 Terra"),
    _model("codex", "gpt-6-astra", "GPT-6 Astra"),
    _model("claude", "claude-opus-5-5", "Claude Opus 5.5"),
    _model("claude", "claude-sonnet-5-5", "Claude Sonnet 5.5"),
    _model("claude", "claude-fable-5-2", "Claude Fable 5.2"),
)


class IntelligenceChoice(BaseModel):
    """What runs an agentic capability: the agent provider, the AI model, and the reasoning effort."""

    agent_provider: AgentProvider
    model: str
    reasoning_effort: ReasoningEffort


class IntelligenceModels(BaseModel):
    """The AI models to pick from for agentic capabilities."""

    models: list[IntelligenceModel] = Field(description="Those of the agent providers that are installed")
    default: IntelligenceChoice = Field(
        description="What an agentic capability runs with when given no agent provider, model, or reasoning effort"
    )


# endregion

# region: Images

ImageFormat = Literal["png", "jpeg", "webp", "gif"]
# The extensions a raster image's name can end in, and the format each is saved in.
IMAGE_FORMATS: dict[str, ImageFormat] = {".png": "png", ".jpg": "jpeg", ".webp": "webp", ".gif": "gif"}
# The extension of an SVG image's name, the other kind of image the tool keeps.
SVG_SUFFIX = ".svg"
ImageMethod = Literal["openai", "chatgpt", "svg", "imported"]
ImageRunStatus = Literal["running", "done", "failed", "cancelled", "timed-out"]
ImageEventKind = Literal["started", "preview", "agent", "steered", "version", "finished", "failed"]
MarkShape = Literal["circle", "box", "arrow", "sketch"]
Fraction = Annotated[float, Field(ge=0, le=1)]


class Mark(BaseModel):
    """A shape drawn over an image to show what a request refers to."""

    shape: MarkShape
    points: list[tuple[Fraction, Fraction]] = Field(
        min_length=2,
        description="Fractions of the image's width and height from its top left: two opposite corners for a circle "
        "or a box, the tail and then the head for an arrow, and each point along a sketch",
    )
    strokes: list[list[tuple[Fraction, Fraction]]] = Field(
        default_factory=list,
        description="For a sketch drawn in several strokes, each stroke after the first, which `points` is",
    )
    color: str = Field(default="red", description="A CSS color name or a hex code")
    note: str = ""


class ImageUsage(BaseModel):
    """What a run used: the tokens the service reported, and what they cost."""

    input_text_tokens: int = 0
    input_image_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = Field(default=None, description="US dollars at the model's published prices; None if unknown")


class ImageVersion(BaseModel):
    """One version of an image: a file kept with the image's data, and what made it."""

    id: str = Field(description="v1, v2, and so on, in the order they were made")
    file: Path = Field(description="Relative to the image's folder in the data directory as kept, absolute in results")
    width: int
    height: int
    frames: int = Field(default=1, description="More than 1 for an animation")
    sha256: str
    method: ImageMethod = Field(
        description="What made it; `imported` for a file the tool found in place or was given to bring in"
    )
    run_id: str | None = None
    created: datetime
    script: Path | None = Field(
        default=None,
        description="For an SVG the tool drew, the image.py that builds it, kept as `file` is, with its lock beside it "
        "under the same name and .lock added",
    )


class ImageVersions(BaseModel):
    """versions.json: every version of an image, and which one its file holds."""

    current: str | None = Field(default=None, description="The version in the image's file")
    versions: list[ImageVersion] = Field(default_factory=list)


class NotGiven(Enum):
    """A parameter left out, so it keeps the value it had; None, by contrast, sets no value."""

    NOT_GIVEN = "NOT_GIVEN"


NOT_GIVEN = NotGiven.NOT_GIVEN
DEFAULT_SVG_CANVAS = (512, 512)


class SvgBudgets(BaseModel):
    """What an SVG drawing should stay within. The agent is told them, and `check_svg_image` measures against them."""

    canvas: tuple[int, int] = Field(description="Width and height, the size of the SVG's view")
    max_bytes: int | None = Field(default=None, description="The size of the SVG file; None for any")


class ImageRecord(BaseModel):
    """image.json: what marks an image as one the tool keeps data for. It is committed with the project."""

    tool: Literal["image-design"] = "image-design"
    id: str = Field(description="Names the image's folder in the data directory, and stays the same when it moves")
    name: str = Field(description="The image's path in its directory, with forward slashes")
    created: datetime
    budgets: SvgBudgets | None = Field(
        default=None, description="For an SVG the tool drew, the budgets of its last drawing, which an edit keeps"
    )


class ImageRunRecord(BaseModel):
    """One request on an image, as runs.json keeps it while it runs and after."""

    id: str
    method: ImageMethod
    prompt: str
    request: dict[str, Any] = Field(
        description="The settings it was sent with, and the files it sent, as copied into the run's folder"
    )
    origin: str | None = Field(default=None, description="Who asked, such as `app`")
    agent_provider: AgentProvider | None = Field(default=None, description="For an agentic method, what ran the agent")
    session_id: str | None = Field(
        default=None, description="For an agentic method, the agent's session, which a later run can resume"
    )
    status: ImageRunStatus = "running"
    pid: int = Field(description="The process running it; a `running` run whose process is gone has crashed")
    started: datetime
    last_event: datetime | None = None
    finished: datetime | None = None
    versions: list[str] = Field(default_factory=list, description="The versions it made")
    image_prompt: str | None = Field(
        default=None, description="The prompt the image model received, when the method words it rather than the caller"
    )
    usage: ImageUsage | None = None
    error: str | None = None


class ImageRuns(BaseModel):
    """runs.json: every request on an image. Not committed, since it changes with every event and names processes."""

    runs: list[ImageRunRecord] = Field(default_factory=list)


class ImageEvent(BaseModel):
    """One line of a run's events.jsonl."""

    time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str
    kind: ImageEventKind
    text: str = Field(default="", description="What happened, for a person to read")
    data: dict[str, Any] = Field(default_factory=dict)


class ImageResult(BaseModel):
    """How a run ended, and what it made."""

    name: str
    path: Path = Field(description="The image's file")
    directory: Path
    data_directory: Path
    run_id: str
    status: ImageRunStatus
    versions: list[ImageVersion] = Field(
        default_factory=list, description="The versions it made; the first went into the image's file"
    )
    usage: ImageUsage | None = None
    error: str | None = None


class ImageSummary(BaseModel):
    """An image, its versions, and how its last run went."""

    name: str
    id: str | None = Field(
        description="Names what the tool keeps for the image, and stays the same when it moves; None for a file the "
        "tool keeps nothing for"
    )
    path: Path
    width: int | None = Field(description="Of the image's file; None when it has no file, or one that cannot be read")
    height: int | None
    frames: int | None = Field(description="More than 1 for an animation")
    modified: datetime | None = Field(description="When the image's file was last written; None when it has no file")
    sha256: str | None = Field(description="Of the image's file, which changes when its content does")
    current: str | None = Field(
        description="The version in the image's file; None when the file has been changed by hand since"
    )
    versions: list[ImageVersion] = Field(description="Empty for a file the tool has made no change to yet")
    status: ImageRunStatus | None = Field(description="Its last run's status; None when it has had no run")
    last_run: ImageRunRecord | None = Field(description="Its last run, with the request it was given")


class ImageListing(BaseModel):
    """Every image in a directory, in name order, and its folders."""

    directory: Path
    data_directory: Path
    images: list[ImageSummary]
    folders: list[str] = Field(
        description="Every folder in the directory, by its path with forward slashes, whether or not it holds an image"
    )
    unreadable: list[str] = Field(
        default_factory=list, description="Why each image whose data cannot be read was left out"
    )


class ImageMove(BaseModel):
    """An image whose file is under another name than the tool has for it."""

    name: str = Field(description="The name the tool had for the image")
    new_name: str = Field(description="Where its file is")


class ImageRelinking(BaseModel):
    """What `relink_images` found for the images whose files were moved outside the tool."""

    relinked: list[ImageMove] = Field(description="The images now kept under the name their file has")
    likely: list[ImageMove] = Field(
        description="Left as they are: the file has the image's file name but not what its current version holds"
    )
    gone: list[str] = Field(description="The images that still have no file, and no file that could be theirs")

    def describe(self) -> str:
        lines = [f"Relinked {move.name} to {move.new_name}." for move in self.relinked]
        lines += [
            f"{move.name} has no file, and {move.new_name} may be it, with other content than its current version. "
            f"To take it: image-design relink-images --likely {move.name}"
            for move in self.likely
        ]
        lines += [f"{name} has no file, and no file in the directory could be it." for name in self.gone]
        return "\n".join(lines) or "Every image has its file."


ImageRequestRole = Literal["source", "marked-copy", "reference", "marks", "mask"]


class ImageRequestImage(BaseModel):
    """One image a request sends."""

    role: ImageRequestRole = Field(
        description="`source` is the image being edited. Its marks go to the OpenAI API as `marks`, a layer beside "
        "it, and to ChatGPT as `marked-copy`, a copy of it with them drawn on"
    )
    path: Path | None = Field(description="The file it is read from; None for what the tool draws from the marks")


class ImageRequestPreview(BaseModel):
    """What a request to an image model would send, worked out without sending it or keeping anything."""

    method: ImageMethod
    name: str
    edits: bool = Field(description="Whether an image with that name exists, so the request edits it")
    prompt: str = Field(description="As the image model receives it")
    added: str | None = Field(
        description="What the tool adds after the prompt as written, such as what the marks are; None when it adds "
        "nothing"
    )
    images: list[ImageRequestImage] = Field(description="In the order they are sent")
    parameters: dict[str, str | int | bool] = Field(
        description="What the request sets, by the names the service gives them; what it leaves out is the service's "
        "choice. For ChatGPT, the image tool's `transparent_background`, and the `codex_model` and "
        "`reasoning_effort` that carry the request"
    )


class ImageActivity(BaseModel):
    """What happened to an image, run by run: each request, what its agent did, and how it ended."""

    name: str
    events: list[ImageEvent] = Field(
        description="In order; each run's begin with `started`, which has its request and its `run_folder`, the "
        "folder the files the request names are relative to"
    )
    status: ImageRunStatus | None = Field(description="The last run's status; None when it has had no run")
    cursor: str | None = Field(
        description="Pass as `after` to get only what happens from here on; None when the image has had no run"
    )


class ImageFrame(BaseModel):
    """One frame of an image, or of one of its versions."""

    index: int = Field(description="From 0, as `frame` names it in a request that edits the image")
    duration_ms: int = Field(description="How long it shows; 0 for a still image, and where the file gives none")
    path: Path | None = Field(default=None, description="The PNG written for it, when the frames were written out")


class ImageFrames(BaseModel):
    """The image's file, or one of its versions, frame by frame: one frame for a still image."""

    version: str | None = Field(description="The version; None for the image's file")
    path: Path = Field(description="Its file")
    width: int
    height: int
    frames: list[ImageFrame]

    def describe(self, name: str) -> str:
        """The frames as text, a line for each, for a person or an agent to read."""
        count = len(self.frames)
        what = f"{name} {self.version}" if self.version else name
        if count == 1:
            head = f"{what}: {self.width}x{self.height}."
            path = self.frames[0].path
            return head if path is None else f"{head} Its frame: {path}"
        total = sum(frame.duration_ms for frame in self.frames)
        lines = [f"{what}: {count} frames of {self.width}x{self.height}, {total} ms in all.", ""]
        for frame in self.frames:
            written = f", {frame.path}" if frame.path is not None else ""
            lines.append(f"- {frame.index}: {frame.duration_ms} ms{written}")
        return "\n".join(lines)


class ImageView(ImageSummary):
    """An image, its versions, and how its last run went, with its file or one of its versions frame by frame."""

    viewed: ImageFrames | None = Field(
        description="The version asked for, else the image's file; None when it has no file, or one that cannot be read"
    )


# endregion

# region: SVG images


class SvgPart(BaseModel):
    """A named group of a drawing."""

    id: str = Field(description="Its id, after the ids of the named groups it is in, joined by /")
    shapes: int = Field(description="The elements that draw in it")


class SvgCheck(BaseModel):
    """An SVG drawing measured against its budgets. It only reports: nothing passes or fails."""

    name: str
    path: Path
    budgets: SvgBudgets
    size: tuple[float, float] | None = Field(description="The width and height the SVG declares; None when it does not")
    view_box: tuple[float, float, float, float] | None = Field(description="Its viewBox; None when it has none")
    shapes: int = Field(description="The elements that draw, such as path, rect, circle, text, and use")
    colors: list[str] = Field(description="Each distinct color, as #rrggbb, or #rrggbbaa when it is see-through")
    bytes: int
    texts: int = Field(description="Text elements, which render with the fonts of the machine that renders them")
    parts: list[SvgPart]
    skipped: list[str] = Field(description="What resvg does not render, such as scripts and animation, with counts")

    def describe(self) -> str:
        """The check as text, a line for each measure, for a person or an agent to read."""
        width, height = self.budgets.canvas
        declared = "declares no size" if self.size is None else f"declares {self.size[0]:g}x{self.size[1]:g}"
        view_box = "no viewBox" if self.view_box is None else "viewBox " + " ".join(f"{n:g}" for n in self.view_box)
        colors = f": {', '.join(self.colors)}." if self.colors else "."
        lines = [
            f"Canvas: {width}x{height}. The SVG {declared}, with {view_box}.",
            f"Shapes: {self.shapes}.",
            f"Colors: {len(self.colors)}{colors}",
            f"Bytes: {self.bytes:,}{_at_most(self.budgets.max_bytes)}.",
        ]
        if self.texts:
            lines.append(
                f"Text elements: {self.texts}. They render with the fonts of the machine that renders them, so they "
                "can look different elsewhere."
            )
        if self.parts:
            lines.append("Named parts:")
            lines.extend(f"- {part.id} ({part.shapes} shape{'' if part.shapes == 1 else 's'})" for part in self.parts)
        else:
            lines.append("Named parts: none. Put each part in a <g> with an id.")
        lines.append("Not rendered by resvg: " + (", ".join(self.skipped) + "." if self.skipped else "nothing."))
        return "\n".join(lines)


def _at_most(budget: int | None) -> str:
    return f" (at most {budget:,})" if budget is not None else ""


# endregion

# region: OpenAI images

OpenAIImageQuality = Literal["low", "medium", "high", "xhigh", "max", "auto"]
OpenAIImageComplexity = Literal["low", "medium", "high"]
OpenAIImageBackground = Literal["transparent", "opaque", "auto"]


class OpenAIImageModel(BaseModel):
    """An OpenAI image model the tool supports, and its prices in US dollars per million tokens.

    The Images API reports no cached tokens, so the cached prices are left out.
    """

    id: str
    label: str
    pricing: str = Field(description="The page the prices are from")
    text_input: float
    image_input: float
    image_output: float


OPENAI_IMAGE_MODELS: tuple[OpenAIImageModel, ...] = (
    OpenAIImageModel(
        id="gpt-image-2.6-sunburst",
        label="GPT Image 2.6 Sunburst",
        pricing="https://developers.openai.com/api/docs/models/gpt-image-2.6-sunburst",
        text_input=5.0,
        image_input=8.0,
        image_output=30.0,
    ),
    OpenAIImageModel(
        id="gpt-image-2.6-flare",
        label="GPT Image 2.6 Flare",
        pricing="https://developers.openai.com/api/docs/models/gpt-image-2.6-flare",
        text_input=5.0,
        image_input=8.0,
        image_output=30.0,
    ),
)
DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-2.6-sunburst"

# endregion

# region: ChatGPT images

# The agent only hands the request to the image tool, which needs little reasoning.
DEFAULT_CHATGPT_REASONING_EFFORT: ReasoningEffort = "low"

# endregion

# region: Image methods


class OpenAIKeyStatus(BaseModel):
    """Where the OpenAI API key comes from. The key itself is never part of it."""

    source: Literal["environment", "saved"] | None = Field(
        description="What requests are sent with: the OPENAI_API_KEY environment variable, which wins, or the key "
        "saved in the platform's credential store; None when there is no key"
    )
    saved: bool = Field(description="Whether a key is saved, also when the environment's is the one used")


class ImageMethodSetup(BaseModel):
    """Whether a way of making images can run on this machine, and the names it makes."""

    ready: bool = Field(
        description="Whether what it needs is installed and configured; a sign-in is checked when a request is sent"
    )
    problem: str | None = Field(description="What to set up, when it is not ready")
    formats: list[str] = Field(description="The extensions the name of an image it makes can end in")


class OpenAIImageSizes(BaseModel):
    """The sizes a still image can have. An animation only needs each side to be a multiple of `step`."""

    step: int = Field(description="Each side is a multiple of this")
    max_edge: int
    max_ratio: float = Field(description="The most the long side can be of the short side")
    min_pixels: int
    max_pixels: int


class OpenAIImageMethod(ImageMethodSetup):
    """What `generate_openai_image` takes."""

    models: list[OpenAIImageModel]
    default_model: str
    sizes: OpenAIImageSizes
    qualities: list[OpenAIImageQuality]
    complexities: list[OpenAIImageComplexity]
    backgrounds: list[OpenAIImageBackground]
    max_images: int = Field(description="The images a request can send, counting the image being edited")
    max_count: int
    max_previews: int
    frames: tuple[int, int] = Field(description="The fewest and the most frames an animation can have")
    frame_ms: tuple[int, int] = Field(description="The shortest and the longest a frame can last")


class ChatGPTImageMethod(ImageMethodSetup):
    """What `generate_chatgpt_image` takes."""

    models: list[IntelligenceModel] = Field(description="The Codex models that can carry the request")
    default_model: str
    default_reasoning_effort: ReasoningEffort
    max_images: int = Field(description="The images a request can send, counting the image being edited")


class SvgImageMethod(ImageMethodSetup):
    """What `draw_svg_image` takes."""

    models: list[IntelligenceModel] = Field(description="Those of the agent providers that are installed")
    default: IntelligenceChoice
    default_canvas: tuple[int, int]
    export_formats: list[str] = Field(description="The extensions `export_svg_image` renders to")


class ImageMethods(BaseModel):
    """The three ways of making an image."""

    openai: OpenAIImageMethod
    chatgpt: ChatGPTImageMethod
    svg: SvgImageMethod

    def describe(self) -> str:
        """The methods as text, for a person or an agent to read."""
        openai, chatgpt, svg = self.openai, self.chatgpt, self.svg
        sizes = openai.sizes
        size_limits = (
            f"each side a multiple of {sizes.step}, at most {sizes.max_edge}; {sizes.min_pixels:,} to "
            f"{sizes.max_pixels:,} pixels; the long side at most {sizes.max_ratio:g} times the short side"
        )
        limits = f"{openai.max_images} images sent, {openai.max_count} made, and {openai.max_previews} previews"
        (fewest, most), (shortest, longest) = openai.frames, openai.frame_ms
        agent = (
            f"--agent-provider {svg.default.agent_provider} --model {svg.default.model} "
            f"--reasoning-effort {svg.default.reasoning_effort}"
        )
        width, height = svg.default_canvas
        blocks = [
            _method_lines(
                "generate-openai-image",
                openai,
                [
                    "Models: " + _with_default([model.id for model in openai.models], openai.default_model),
                    f"Sizes: {size_limits}",
                    "Qualities: " + ", ".join(openai.qualities),
                    "Complexities: " + ", ".join(openai.complexities),
                    "Backgrounds: " + ", ".join(openai.backgrounds),
                    f"At most {limits}",
                    f"A .gif: {fewest} to {most} frames of {shortest} to {longest} ms",
                ],
            ),
            _method_lines(
                "generate-chatgpt-image",
                chatgpt,
                [
                    "Codex models: " + _with_default([model.id for model in chatgpt.models], chatgpt.default_model),
                    f"Reasoning effort: {chatgpt.default_reasoning_effort} by default",
                    f"At most {chatgpt.max_images} images sent",
                ],
            ),
            _method_lines(
                "draw-svg-image",
                svg,
                [
                    f"Agent: {agent} by default; `image-design list-intelligence-models` lists the others",
                    f"Canvas: {width}x{height} by default",
                    "Exports to: " + ", ".join(svg.export_formats),
                ],
            ),
        ]
        return "\n\n".join(blocks)


def _method_lines(command: str, method: ImageMethodSetup, facts: list[str]) -> str:
    ready = "ready" if method.ready else f"not set up. {method.problem}"
    lines = [f"{command}: {ready}", f"- Names end in: {', '.join(method.formats)}"]
    lines.extend(f"- {fact}" for fact in facts)
    return "\n".join(lines)


def _with_default(values: list[str], default: str) -> str:
    return ", ".join(f"{value} (default)" if value == default else value for value in values) or "none installed"


# endregion


# region: App

ThemePreference = Literal["system", "light", "dark"]
AppMethod = Literal["model", "svg"]
ImagesView = Literal["details", "grid"]
AppImageKind = Literal["image", "animation"]


class PaneLayout(BaseModel):
    """One side pane of the app at one of its widths: how wide it is, and whether it shows."""

    size: int | None = Field(default=None, ge=0, description="Its width in pixels; None for the default")
    open: bool = True


class AppLayout(BaseModel):
    """The app's side panes at one of its widths."""

    images: PaneLayout = Field(default_factory=PaneLayout)
    request: PaneLayout = Field(default_factory=PaneLayout)


class AppSettings(BaseModel):
    """app-settings.json in the user's config directory: how the person set up the app, the same in every directory."""

    theme: ThemePreference = Field(default="system", description="`system` follows the host's theme")
    images_view: ImagesView = Field(
        default="details", description="How Your images lists them: a file tree with columns, or a grid of previews"
    )
    advanced: bool = Field(default=False, description="Whether a request's advanced options show")
    wide: AppLayout = Field(default_factory=AppLayout, description="The panes from 1100 pixels wide")
    medium: AppLayout = Field(default_factory=AppLayout, description="The panes from 640 to 1100 pixels wide")


class AppImageRequest(BaseModel):
    """What the person last picked in the app for a request to an image model."""

    model: str | None = Field(
        default=None,
        description="An OpenAI image model's ID, or `chatgpt`; None for the default of the first method set up",
    )
    size: tuple[int, int] | None = Field(
        default=None, description="None for the service's choice, and on an edit the size of the image being edited"
    )
    quality: OpenAIImageQuality = "auto"
    format: str = Field(default=".png", description="The extension a new still image's name ends in")
    background: OpenAIImageBackground = "auto"
    count: int = Field(default=1, ge=1)
    kind: AppImageKind = Field(default="image", description="What a new image is: a still image, or an animation")
    frame_size: tuple[int, int] | None = Field(
        default=None, description="A new animation's size; None for the service's choice"
    )
    frames: int = Field(default=8, ge=1, description="How many frames a new animation has")
    frame_ms: int = Field(default=200, ge=1, description="How long each frame of a new animation shows")
    complexity: OpenAIImageComplexity | None = Field(default=None, description="None for the service's choice")
    compression: int = Field(default=100, ge=0, le=100, description="For a .jpg or .webp")
    codex_model: str | None = Field(
        default=None, description="The Codex model that carries a request to ChatGPT; None for the default"
    )
    reasoning_effort: ReasoningEffort | None = Field(
        default=None, description="That model's reasoning effort; None for the default"
    )


class AppSvgRequest(BaseModel):
    """What the person last picked in the app for drawing an SVG: the agent, and a new drawing's budgets."""

    agent_provider: AgentProvider | None = Field(default=None, description="None for the default")
    model: str | None = Field(default=None, description="The agent's model; None for the agent provider's default")
    reasoning_effort: ReasoningEffort | None = Field(default=None, description="None for the default")
    canvas: tuple[int, int] | None = Field(default=None, description="A new drawing's; None for the default")
    max_bytes: int | None = Field(default=None, ge=1, description="None for any")
    timeout_seconds: int | None = Field(default=None, ge=1, description="How long a run may take; None for no limit")


AppFolderShows = Literal["files", "dialog"]


class AppFolder(BaseModel):
    """A folder the person pinned in the app to find references in."""

    path: Path
    shows: AppFolderShows = Field(
        default="files",
        description="`files` lists its images in the app, and `dialog` opens the platform's file dialog in it",
    )


class ReferenceEntry(BaseModel):
    """An image file the app offers as a reference."""

    name: str
    path: Path
    width: int | None = Field(description="None for a drawing, which has no size in pixels, or a file not read")
    height: int | None


class ReferenceLibrary(BaseModel):
    """The references the app offers besides the images in its directory, of what is still there."""

    pinned: list[ReferenceEntry]
    used: list[ReferenceEntry] = Field(description="What requests sent from the app were given, newest first")


class UsedReference(BaseModel):
    """A reference a request sent from the app was given: the name it had, and where the file is now."""

    name: str
    path: Path


class UsedReferences(BaseModel):
    """app/used.json in a data directory: what requests sent from the app were given as references."""

    used: list[UsedReference] = Field(default_factory=list, description="Newest first")


class AppState(BaseModel):
    """app/app.json in a data directory: what the person last picked in the app for the images there."""

    method: AppMethod = Field(
        default="model", description="The way of making an image picked last: an image model, or drawing an SVG"
    )
    request: AppImageRequest = Field(default_factory=AppImageRequest)
    svg: AppSvgRequest = Field(default_factory=AppSvgRequest)
    closed_folders: list[str] = Field(
        default_factory=list, description="The folders closed in Your images, by their paths with forward slashes"
    )
    pins: list[Path] = Field(default_factory=list, description="The image files pinned as references, newest first")
    folders: list[AppFolder] = Field(default_factory=list, description="The folders pinned to find references in")
    shown: str | None = Field(
        default=None,
        description="The image the app showed last, which it opens on. `show_image` and `open_app` set it, and a "
        "save keeps it as it is",
    )


class AppImages(ImageListing):
    """The images as the app lists them: every image in its directory, and the one it showed last."""

    shown: str | None = Field(description="None when the app has shown none, or that image is gone")
    likely: list[ImageMove] = Field(
        default_factory=list,
        description="The images with no file that `relink_image` can point at the file that may be theirs",
    )


# endregion
