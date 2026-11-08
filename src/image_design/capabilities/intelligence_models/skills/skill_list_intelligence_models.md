`list-intelligence-models` lists the models that are available for agentic capabilities.
Pass your choice to an agentic capability as `--agent-provider`, `--model`, and `--reasoning-effort`.

```bash
image-design list-intelligence-models
image-design list-intelligence-models --json
```

```python
from image_design.lib import list_intelligence_models

print(list_intelligence_models(structured=True))
```

An agentic capability also takes any other model the agent provider knows by name, with any
reasoning effort that agent provider has.

## Arguments

- `--json` (library: `structured=True`): the listing as JSON (library: `IntelligenceModels`)
  instead of one model per line. Off by default.

## Result

The default a capability runs with, as the flags to pass, then one line per model: its agent
provider, its ID (pass it as `--model`), its label, the reasoning efforts it takes, and `vision`
when it can be shown images.

```
Default: --agent-provider codex --model gpt-6.1-sol --reasoning-effort medium

- codex gpt-6.1-sol (GPT-6.1 Sol): low, medium, high, xhigh, max, ultra; vision
- claude claude-opus-5-5 (Claude Opus 5.5): low, medium, high, xhigh, max; vision
```
