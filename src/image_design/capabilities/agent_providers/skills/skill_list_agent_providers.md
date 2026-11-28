`list-agent-providers` says which agent providers the agentic capabilities can run through on this
machine: whether each is installed, whether it is signed in, and how. It starts each installed one's
runtime and asks it, as a run does before its agent starts, so it takes a second or two.

```bash
image-design list-agent-providers
image-design list-agent-providers --json
```

```python
from image_design.lib import list_agent_providers

[(status.agent_provider, status.signed_in) for status in list_agent_providers().agent_providers]
```

Reach for it when a run fails because its agent provider has no credentials, or before the first
run on a machine. Each one that cannot run says why and what fixes it.

## Arguments

- `--json` (library: the `AgentProviders` returned): the agent providers as JSON instead of text.

## Result

One line per agent provider, in the order a run picks them: how it is signed in, or what keeps it
from running and how to fix that.

```
- codex: signed in with ChatGPT
- claude: installed, not signed in. The Claude Agent SDK has no credentials. Set ANTHROPIC_API_KEY ...
```

How it is signed in is in the runtime's own words, such as ChatGPT, an API key, a Claude
subscription, or a cloud provider, and never the account's email.
