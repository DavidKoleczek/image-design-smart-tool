"""The AI models to pick from, with the installed SDKs faked, so it runs on a bare install."""

from importlib.machinery import ModuleSpec
import json

import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.intelligence_models.intelligence_models import (
    describe,
    reasoning_efforts,
    require_reasoning_effort,
)
from image_design.cli import app
from image_design.intelligence import interface
from image_design.schemas import (
    AGENT_PROVIDERS,
    DEFAULT_INTELLIGENCE_MODELS,
    DEFAULT_REASONING_EFFORT,
    INTELLIGENCE_MODELS,
    PROVIDER_REASONING_EFFORTS,
    AgentProvider,
    ImageDesignError,
)

runner = CliRunner()


def only_installed(monkeypatch: pytest.MonkeyPatch, *agent_providers: AgentProvider) -> None:
    modules = {interface.SDK_MODULES[agent_provider] for agent_provider in agent_providers}

    def find_spec(name: str) -> ModuleSpec | None:
        return ModuleSpec(name, None) if name in modules else None

    monkeypatch.setattr(interface, "find_spec", find_spec)


def test_every_agent_provider_s_default_model_is_listed() -> None:
    listed = {(model.agent_provider, model.id) for model in INTELLIGENCE_MODELS}

    for agent_provider, model in DEFAULT_INTELLIGENCE_MODELS.items():
        assert (agent_provider, model) in listed


@pytest.mark.parametrize("agent_provider", AGENT_PROVIDERS)
def test_only_the_installed_agent_providers_models_are_listed_and_their_first_is_the_default(
    monkeypatch: pytest.MonkeyPatch, agent_provider: AgentProvider
) -> None:
    only_installed(monkeypatch, agent_provider)

    models = lib.list_intelligence_models(structured=True)

    assert models.models
    assert {model.agent_provider for model in models.models} == {agent_provider}
    assert models.default.agent_provider == agent_provider
    assert models.default.model == DEFAULT_INTELLIGENCE_MODELS[agent_provider]
    assert models.default.reasoning_effort == DEFAULT_REASONING_EFFORT


def test_with_none_installed_nothing_is_listed_and_the_default_is_the_first_agent_provider_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    only_installed(monkeypatch)

    models = lib.list_intelligence_models(structured=True)

    assert models.models == []
    assert models.default.agent_provider == AGENT_PROVIDERS[0]


def test_the_library_returns_text_by_default_and_the_listing_when_structured() -> None:
    assert lib.list_intelligence_models() == describe(lib.list_intelligence_models(structured=True))


def test_the_command_prints_the_listing_as_json_when_asked() -> None:
    result = runner.invoke(app, ["list-intelligence-models", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == lib.list_intelligence_models(structured=True).model_dump(mode="json")


def test_the_command_prints_the_default_then_one_model_per_line() -> None:
    result = runner.invoke(app, ["list-intelligence-models"])

    listing = lib.list_intelligence_models(structured=True)
    default = listing.default
    lines = result.output.splitlines()
    assert result.exit_code == 0
    assert lines[0] == (
        f"Default: --agent-provider {default.agent_provider} --model {default.model} "
        f"--reasoning-effort {default.reasoning_effort}"
    )
    assert lines[1] == ""
    assert lines[2:] == [
        f"- {model.agent_provider} {model.id} ({model.label}): {', '.join(model.reasoning_efforts)}; vision"
        for model in listing.models
    ]


def test_the_command_says_so_when_no_agent_provider_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    only_installed(monkeypatch)

    result = runner.invoke(app, ["list-intelligence-models"])

    assert result.exit_code == 0
    assert result.output.splitlines()[-1] == "No agent provider is installed, so no models are listed."


def test_a_model_the_tool_does_not_list_takes_every_effort_its_agent_provider_has() -> None:
    assert reasoning_efforts("claude", "claude-some-future-model") == PROVIDER_REASONING_EFFORTS["claude"]
    assert "ultra" not in reasoning_efforts("claude", DEFAULT_INTELLIGENCE_MODELS["claude"])
    assert "ultra" in reasoning_efforts("codex", DEFAULT_INTELLIGENCE_MODELS["codex"])


def test_a_reasoning_effort_the_model_does_not_take_names_the_ones_it_does() -> None:
    assert require_reasoning_effort("max", "claude", "claude-opus-5-5") == "max"
    assert require_reasoning_effort("ultra") == "ultra"

    with pytest.raises(ImageDesignError, match="'ultra' is not a reasoning effort claude-opus-5-5 takes"):
        require_reasoning_effort("ultra", "claude", "claude-opus-5-5")
    with pytest.raises(ImageDesignError, match=r"'extreme' is not a reasoning effort. Pass one of: low"):
        require_reasoning_effort("extreme")
