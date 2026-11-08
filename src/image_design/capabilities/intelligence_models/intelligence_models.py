from image_design.intelligence.interface import installed
from image_design.schemas import (
    AGENT_PROVIDERS,
    DEFAULT_INTELLIGENCE_MODELS,
    DEFAULT_REASONING_EFFORT,
    INTELLIGENCE_MODELS,
    PROVIDER_REASONING_EFFORTS,
    REASONING_EFFORTS,
    AgentProvider,
    ImageDesignError,
    IntelligenceChoice,
    IntelligenceModels,
    ReasoningEffort,
)


def list_intelligence_models() -> IntelligenceModels:
    """The models of the installed agent providers, and the default."""
    # The one `resolve_agent_provider` picks when given none, or the first in order when none is installed.
    provider = next((candidate for candidate in AGENT_PROVIDERS if installed(candidate)), AGENT_PROVIDERS[0])
    return IntelligenceModels(
        models=[model for model in INTELLIGENCE_MODELS if installed(model.agent_provider)],
        default=IntelligenceChoice(
            agent_provider=provider,
            model=DEFAULT_INTELLIGENCE_MODELS[provider],
            reasoning_effort=DEFAULT_REASONING_EFFORT,
        ),
    )


def describe(listing: IntelligenceModels) -> str:
    """The listing as text: the default as flags, then one model per line, in far fewer tokens than JSON."""
    default = listing.default
    flags = f"--agent-provider {default.agent_provider} --model {default.model}"
    lines = [f"Default: {flags} --reasoning-effort {default.reasoning_effort}", ""]
    for model in listing.models:
        vision = "; vision" if model.vision else ""
        lines.append(
            f"- {model.agent_provider} {model.id} ({model.label}): {', '.join(model.reasoning_efforts)}{vision}"
        )
    if not listing.models:
        lines.append("No agent provider is installed, so no models are listed.")
    return "\n".join(lines)


def reasoning_efforts(agent_provider: AgentProvider, model: str) -> tuple[ReasoningEffort, ...]:
    """What `model` takes: its own efforts when the tool lists it, else every one its agent provider has."""
    listed = next(
        (
            candidate
            for candidate in INTELLIGENCE_MODELS
            if candidate.agent_provider == agent_provider and candidate.id == model
        ),
        None,
    )
    if listed is not None:
        return tuple(listed.reasoning_efforts)
    return PROVIDER_REASONING_EFFORTS[agent_provider]


def require_reasoning_effort(
    reasoning_effort: str, agent_provider: AgentProvider | None = None, model: str | None = None
) -> ReasoningEffort:
    """`reasoning_effort` as its literal type; raises unless `model` takes it, or any model does when none is named."""
    if agent_provider is None or model is None:
        efforts, what = REASONING_EFFORTS, "a reasoning effort"
    else:
        efforts, what = reasoning_efforts(agent_provider, model), f"a reasoning effort {model} takes"
    for effort in efforts:
        if effort == reasoning_effort:
            return effort
    raise ImageDesignError(
        f"{reasoning_effort!r} is not {what}. Pass one of: {', '.join(efforts)}. "
        "`image-design list-intelligence-models` lists each model's."
    )
