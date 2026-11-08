# Library Reference

Every capability of Image Design is reachable from `image_design.lib`.
All other surfaces, including the CLI, are thin wrappers over the library.

## Agent Intelligence

Capabilities which require an agent use the `Intelligence` protocol in `image_design.intelligence.interface`:

```python
class Intelligence(Protocol):
    implementation: str
    steering: Steering

    def preflight(self) -> None: ...
    async def start(self, request: AgentRequest) -> AgentRun: ...


class AgentRun(Protocol):
    session_id: str | None

    def events(self) -> AsyncIterator[AgentEvent]: ...
    async def steer(self, message: str) -> None: ...
    async def cancel(self) -> None: ...
    async def result(self) -> AgentResult: ...
```

`preflight` raises `ImageDesignError` naming what to configure when the implementation cannot run.
`start` starts one agent and returns once it runs.
`AgentRun.events` replays every `AgentEvent` from the start, then live ones, ending with one `terminal`: the agent's messages, reasoning, tool calls and results, and usage, in the same shape for every agent provider.
`steer` sends a message while the agent works; `steering` says whether it lands mid-turn or queued for the next turn.
`cancel` stops the run, and `result` waits for its `AgentResult`: the text, structured output, or error, whether it was cancelled, and the session.
Setting `AgentRequest.resume` to an earlier `AgentResult.session_id` continues that session instead of starting a fresh one - which is useful when the new request would benefit from the context in that existing session.
Images must be PNG, JPEG, GIF, or WebP files; any other raises `ImageDesignError` before the run starts.

`resolve_intelligence(agent_provider)` returns a shipped implementation, one per agent provider, each installed through the extra of the same name:

- `codex`: `CodexIntelligence`
  - Built on the [OpenAI Codex SDK](https://github.com/openai/codex/tree/main/sdk/python)
  - Run with the user's Codex sign-in and `~/.codex/config.toml` and a session is a Codex thread.
- `claude`: `ClaudeIntelligence`, 
  - Built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) 
  - Run with the user's Claude Code settings and the credentials Claude Code resolves: `ANTHROPIC_API_KEY`, or a cloud provider's. See [its docs](https://code.claude.com/docs/en/agent-sdk/quickstart). 
  - Sessions are kept where Claude Code keeps them; a plain completion runs in the platform's per-user state directory, in `image-design/claude`.

### List intelligence models

The AI models to pick from, each with the reasoning efforts it takes, whether it can be shown images, etc.

```python
def list_intelligence_models(structured: bool = False) -> str | IntelligenceModels
```

## Manifest

The tool's `SMART_TOOL.md` as structured data: the frontmatter as fields, the Markdown below it as `Manifest.body`.

```python
def load_manifest() -> Manifest
```

## Skill

What an agent reads once it has decided to drive the tool: the manifest body, its `requires` as prerequisites, and the capability list, wrapped so the reader knows where the tool's files are.
Naming a capability returns that capability's own skill instead: the same wrapper, a heading carrying the capability's name, whether it is deterministic or model-backed, and the Markdown in its folder's `skills/`, which covers its arguments, a worked invocation, and its result.
The CLI's `--help` prints exactly this, the tool's at the root and the capability's on a command.

```python
def skill(capability: str | None = None) -> str
```

The capabilities the skill lists, one entry each, driven by the same table the CLI is built from:

```python
class Capability(NamedTuple):
    name: str
    summary: str
    model_backed: bool
    skill: str
    resources: tuple[str, ...] = ()
```

- `name` and `summary`: the command's name and its line in the tool's capability list.
- `model_backed`: whether it calls an AI model, agentic or not, which decides the kind shown in both skills.
- `skill`: the capability's skill body, a Markdown file relative to the installed package root, written without frontmatter, title, or kind line because the renderer supplies them.
- `resources`: the files that body refers to, relative to the installed package root, listed under `<skill_resources>` in the capability's skill. The block is omitted when there are none.

## Version

The installed package's version, from its metadata. The CLI's `--version` prints it.

```python
def version() -> str
```
