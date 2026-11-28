"""Lists the agent providers with their runtimes faked, so it needs no sign-in and starts no runtime."""

from importlib.machinery import ModuleSpec
from pathlib import Path

from mcp import Client
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.agent_providers import agent_providers
from image_design.cli import app
from image_design.intelligence import interface
from image_design.schemas import AGENT_PROVIDERS, AgentProvider, AgentProviders, AgentProviderStatus, ImageDesignError

runner = CliRunner()


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch) -> dict[AgentProvider, str | None]:
    """How each agent provider's runtime is signed in, None for not, which a test sets."""
    how: dict[AgentProvider, str | None] = dict.fromkeys(AGENT_PROVIDERS)

    def signed_in_with(agent_provider: AgentProvider) -> str:
        if how[agent_provider] is None:
            raise ImageDesignError(f"{agent_provider} has no credentials. Set them up.")
        return str(how[agent_provider])

    monkeypatch.setattr(agent_providers, "agent_signed_in_with", signed_in_with)
    installed(monkeypatch, *AGENT_PROVIDERS)
    return how


def installed(monkeypatch: pytest.MonkeyPatch, *names: AgentProvider) -> None:
    modules = {interface.SDK_MODULES[name] for name in names}

    def find_spec(name: str) -> ModuleSpec | None:
        return ModuleSpec(name, None) if name in modules else None

    monkeypatch.setattr(interface, "find_spec", find_spec)


def test_each_agent_provider_says_whether_it_is_installed_and_how_it_is_signed_in(
    signed_in: dict[AgentProvider, str | None], monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(monkeypatch, "codex")
    signed_in["codex"] = "ChatGPT"

    codex, claude = lib.list_agent_providers().agent_providers

    assert codex == AgentProviderStatus(
        agent_provider="codex", installed=True, signed_in=True, signed_in_with="ChatGPT", problem=None
    )
    assert (claude.agent_provider, claude.installed, claude.signed_in, claude.signed_in_with) == (
        "claude",
        False,
        False,
        None,
    )
    assert claude.problem is not None
    assert "uv tool install" in claude.problem
    assert "[claude]" in claude.problem


def test_one_not_signed_in_says_what_to_configure(signed_in: dict[AgentProvider, str | None]) -> None:
    codex, _ = lib.list_agent_providers().agent_providers

    assert (codex.installed, codex.signed_in, codex.signed_in_with) == (True, False, None)
    assert codex.problem == "codex has no credentials. Set them up."


def test_the_cli_prints_one_line_each_or_the_list_as_json(signed_in: dict[AgentProvider, str | None]) -> None:
    signed_in["claude"] = "Claude Max"

    listed = runner.invoke(app, ["list-agent-providers"])
    as_json = runner.invoke(app, ["list-agent-providers", "--json"])

    assert (listed.exit_code, as_json.exit_code) == (0, 0)
    assert listed.stdout.splitlines() == [
        "- codex: installed, not signed in. codex has no credentials. Set them up.",
        "- claude: signed in with Claude Max",
    ]
    providers = AgentProviders.model_validate_json(as_json.stdout).agent_providers
    assert [(status.agent_provider, status.signed_in) for status in providers] == [("codex", False), ("claude", True)]


async def test_the_app_lists_them_for_its_settings(signed_in: dict[AgentProvider, str | None], tmp_path: Path) -> None:
    app_server = lib.app_server(tmp_path)
    try:
        async with Client(f"{app_server.open().url}/mcp") as client:
            before = await client.call_tool("list_agent_providers", {})
            signed_in["claude"] = "Anthropic Console account"
            after = await client.call_tool("list_agent_providers", {})
    finally:
        app_server.close()

    listed = [AgentProviders.model_validate(result.structured_content).agent_providers for result in (before, after)]
    assert [[(status.agent_provider, status.signed_in_with) for status in each] for each in listed] == [
        [("codex", None), ("claude", None)],
        [("codex", None), ("claude", "Anthropic Console account")],
    ]
