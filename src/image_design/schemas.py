from datetime import UTC, datetime
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
# The extensions an image's name can end in, and the format each is saved in.
IMAGE_FORMATS: dict[str, ImageFormat] = {".png": "png", ".jpg": "jpeg", ".webp": "webp", ".gif": "gif"}
ImageMethod = Literal["openai", "chatgpt", "imported"]
ImageRunStatus = Literal["running", "done", "failed", "cancelled", "timed-out"]
ImageEventKind = Literal["started", "preview", "version", "finished", "failed"]
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


class ImageVersions(BaseModel):
    """versions.json: every version of an image, and which one its file holds."""

    current: str | None = Field(default=None, description="The version in the image's file")
    versions: list[ImageVersion] = Field(default_factory=list)


class ImageRecord(BaseModel):
    """image.json: what marks an image as one the tool keeps data for. It is committed with the project."""

    tool: Literal["image-design"] = "image-design"
    id: str = Field(description="Names the image's folder in the data directory, and stays the same when it moves")
    name: str = Field(description="The image's path in its directory, with forward slashes")
    created: datetime


class ImageRunRecord(BaseModel):
    """One request on an image, as runs.json keeps it while it runs and after."""

    id: str
    method: ImageMethod
    prompt: str
    request: dict[str, Any] = Field(
        description="The settings it was sent with, and the files it sent, as copied into the run's folder"
    )
    origin: str | None = Field(default=None, description="Who asked, such as `app`")
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
