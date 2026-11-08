from typing import Literal, NamedTuple, get_args

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
    """Raised for any failure the library can name and explain how to fix."""


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
