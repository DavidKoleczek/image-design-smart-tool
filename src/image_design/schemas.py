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
    _model("codex", "gpt-6-luna", "GPT-6 Luna"),
    _model("claude", "claude-opus-5-5", "Claude Opus 5.5"),
    _model("claude", "claude-sonnet-5-5", "Claude Sonnet 5.5"),
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
    method: ImageMethod = Field(description="What made it; `imported` for a file the tool found in place")
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
    max_shapes: int | None = Field(default=None, description="Elements that draw, such as path and rect; None for any")
    max_colors: int | None = Field(default=None, description="Distinct fill, stroke, and stop colors; None for any")
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
    path: Path
    current: str | None = Field(
        description="The version in the image's file; None when the file has been changed by hand since"
    )
    versions: list[ImageVersion]
    status: ImageRunStatus | None = Field(description="Its last run's status; None when it has had no run")


class ImageActivity(BaseModel):
    """What happened to an image, run by run: each request, what its agent did, and how it ended."""

    name: str
    events: list[ImageEvent] = Field(description="In order; each run's begin with `started`, which has its request")
    status: ImageRunStatus | None = Field(description="The last run's status; None when it has had no run")
    cursor: str | None = Field(
        description="Pass as `after` to get only what happens from here on; None when the image has had no run"
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
            f"Shapes: {self.shapes}{_at_most(self.budgets.max_shapes)}.",
            f"Colors: {len(self.colors)}{_at_most(self.budgets.max_colors)}{colors}",
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
