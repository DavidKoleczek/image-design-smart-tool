"""The contract every agentic capability runs through, so the implementation is swappable."""

from collections.abc import AsyncIterator
from importlib.util import find_spec
import os
from pathlib import Path
from typing import Protocol

from image_design.core.skill import DISTRIBUTION, repository_url
from image_design.intelligence.schemas import IMAGE_MEDIA_TYPES, AgentEvent, AgentRequest, AgentResult, Steering
from image_design.schemas import AGENT_PROVIDERS, AgentProvider, ImageDesignError
from image_design.shared import state

# The import each agent provider's SDK answers to; its extra is named after the agent provider.
SDK_MODULES: dict[AgentProvider, str] = {
    "codex": "openai_codex",
    "claude": "claude_agent_sdk",
}


class AgentRun(Protocol):
    """One running agent: what it does as it happens, a way to talk to it, and how it ended."""

    @property
    def session_id(self) -> str | None:
        """The session a later run resumes, once the agent provider has made it; None before."""
        ...

    def events(self) -> AsyncIterator[AgentEvent]:
        """Every event from the start, then live ones until the run ends with `terminal`."""
        ...

    async def steer(self, message: str, images: list[Path] | None = None) -> None:
        """Send a message, and any images with it, to the agent while it works.

        The implementation's `steering` says how it lands.
        """
        ...

    async def cancel(self) -> None:
        """Stop the run at once, and everything it started; its session can still be resumed."""
        ...

    async def result(self) -> AgentResult:
        """Wait for the run to end.

        When the request carries an output schema, the result either holds a conforming
        `output` or an `error`; retry mechanics are the implementation's own business.
        """
        ...


class Intelligence(Protocol):
    """Runs agents against models; the library depends on this contract, never on an SDK."""

    implementation: str
    steering: Steering

    def preflight(self) -> None:
        """Raise ImageDesignError naming exactly what to configure when the implementation cannot run."""
        ...

    async def start(self, request: AgentRequest) -> AgentRun:
        """Start one agent and return once it runs; failures after that end the run with `AgentResult.error`."""
        ...


def installed(agent_provider: AgentProvider) -> bool:
    """Whether the agent provider's SDK is importable, without importing it."""
    return find_spec(SDK_MODULES[agent_provider]) is not None


def resolve_agent_provider(agent_provider: AgentProvider | None = None) -> AgentProvider:
    """The named agent provider when it is installed, else the first installed one in `AGENT_PROVIDERS` order."""
    if agent_provider is not None:
        if not installed(agent_provider):
            raise ImageDesignError(
                f"The {agent_provider} agent provider is not installed. Install image-design with it: "
                f"`uv tool install {_install_source(agent_provider)}`, or `uv add {_install_source(agent_provider)}` "
                "in a project that uses the library."
            )
        return agent_provider
    for candidate in AGENT_PROVIDERS:
        if installed(candidate):
            return candidate
    raise ImageDesignError(
        "Agentic capabilities need an agent provider and none is installed. Install image-design with every "
        f"one: `uv tool install {_install_source('all')}`, or put "
        + " or ".join(f"[{candidate}]" for candidate in AGENT_PROVIDERS)
        + " in place of [all] for just one. Use `uv add` instead of `uv tool install` in a project that uses the "
        "library."
    )


def resolve_intelligence(agent_provider: AgentProvider | None = None, model: str | None = None) -> Intelligence:
    """The shipped implementation for the agent provider `resolve_agent_provider` picks.

    `model` is what its preflight checks, when the implementation can check one before a run.
    """
    match resolve_agent_provider(agent_provider):
        case "codex":
            from image_design.intelligence.codex import CodexIntelligence

            return CodexIntelligence()
        case "claude":
            from image_design.intelligence.claude import ClaudeIntelligence

            return ClaudeIntelligence()


def select_intelligence(
    intelligence: Intelligence | None,
    agent_provider: AgentProvider | None,
    model: str | None,
    default_models: dict[AgentProvider, str],
) -> tuple[Intelligence, str]:
    """The intelligence a capability runs through and the model it asks for.

    An injected intelligence wins over `agent_provider`, which then only picks the default model; with neither
    named, that default is the first agent provider's, since nothing about an injected implementation says which
    agent provider it speaks for.
    """
    if intelligence is None:
        agent_provider = resolve_agent_provider(agent_provider)
        model = default_models[agent_provider] if model is None else model
        return resolve_intelligence(agent_provider, model), model
    return intelligence, default_models[agent_provider or AGENT_PROVIDERS[0]] if model is None else model


def require_showable(images: list[Path]) -> None:
    """Raise unless every image is a file of a type an agent can be shown, before a run starts with it."""
    for image in images:
        if image.suffix.lower() not in IMAGE_MEDIA_TYPES:
            raise ImageDesignError(
                f"{image} cannot be shown to the agent. Pass an image ending in one of: {', '.join(IMAGE_MEDIA_TYPES)}."
            )
        if not image.is_file():
            raise ImageDesignError(f"{image} is not a file. Pass the path of an image that exists.")


def agent_environment(request: AgentRequest) -> dict[str, str]:
    """The variables the agent's processes get over this process's: the request's, and PATH with its directories
    first."""
    environment = dict(request.environment)
    if request.path_directories:
        directories = [str(directory) for directory in request.path_directories]
        inherited = os.environ.get("PATH")
        environment["PATH"] = os.pathsep.join([*directories, inherited] if inherited else directories)
    return environment


def state_directory(agent_provider: AgentProvider) -> Path:
    """The platform's per-user state location for the agent provider, where what a later run resumes lives."""
    return state.state_directory() / agent_provider


def _install_source(extra: str) -> str:
    url = repository_url()
    return f'"{DISTRIBUTION}[{extra}] @ git+{url}"' if url else f'"{DISTRIBUTION}[{extra}]"'
