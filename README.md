# Image Design Smart Tool

Image creation and editing workspace.

This is a [Smart Tool](https://github.com/microsoft/amplifier-smart-tools) which is a library with a thin CLI over it and agentic capabilities sit behind an interface so many providers can be used.
We support the [OpenAI Codex SDK](https://github.com/openai/codex/tree/main/sdk/python) and the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python).

## Installation

Prerequisites:
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- For the agentic capabilities, one of:
  - `codex` agent provider: the [Codex CLI](https://github.com/openai/codex) signed in with ChatGPT. See [authentication](https://developers.openai.com/codex/auth).
  - `claude` agent provider: `ANTHROPIC_API_KEY`, or any of its other supported modes of [authentication](https://code.claude.com/docs/en/agent-sdk/quickstart).
- An `OPENAI_API_KEY` from the [OpenAI API](https://platform.openai.com/api-keys)
- (Optional) Install the Smart Tools skill so your agent knows about Smart Tools: `npx skills add microsoft/amplifier-smart-tools`

To get started:

```bash
# Install the Agent Skill so your agent knows about it.
npx skills add DavidKoleczek/image-design-smart-tool
# Install the tool, choosing the extras you want
uv tool install "image-design[all | codex | claude | openai] @ git+https://github.com/DavidKoleczek/image-design-smart-tool"
# Check the install
image-design manifest
```

To use it as a library:

```bash
uv add "image-design[all] @ git+https://github.com/DavidKoleczek/image-design-smart-tool"
```

To update:

```bash
npx skills update image-design   # add -g for global installs
uv tool upgrade image-design
```

To uninstall:

```bash
npx skills remove image-design   # add -g for global installs
uv tool uninstall image-design
```

## Interface

Each command works in a workspace, the top-level directory of your project: the working directory, or the one `--workspace` names. The images are kept in its `.image-design`.
The app starts from anywhere. It opens on the workspace you opened last, or asks you to pick one first, and you can switch workspaces in it.

```bash
# Run the app in background on your system at http://127.0.0.1:8789
# PowerShell (Windows)
Start-Process image-design -ArgumentList "app", "--port", "8789" -WindowStyle Hidden
# Stop it on PowerShell
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8789 -State Listen).OwningProcess

# bash (macOS, Linux)
nohup image-design app --port 8789 > /dev/null 2>&1 &
# Stop it on bash
pkill -f "image-design app --port 8789"

# Serve the app as an MCP App
image-design mcp
# Serve the app in the browser
image-design app

# Bring existing images, or whole folders of them, into the workspace
image-design import-images ~/Pictures/references logo.png --folder references

image-design design-image "A paper-cut cactus in a terracotta pot, in the style of the reference." --name concepts/cactus.png --reference style.png
image-design design-image "Less detail, and keep the shading." --name concepts/cactus.png --resume-session true --image-model chatgpt
image-design steer-image --name concepts/cactus.png --message "Keep the pot."
image-design generate-openai-image "A paper-cut cactus in a terracotta pot." --name concepts/cactus.png
image-design generate-chatgpt-image "Make the pot blue." --name concepts/cactus.png
image-design draw-svg-image "A flat vector sailboat on calm water at sunset. No text." --name sailboat.svg
image-design check-svg-image --name sailboat.svg
image-design export-svg-image --name sailboat.svg --output sailboat.png --scale 2
image-design restore-image-version --name concepts/cactus.png --version v1
image-design read-image-activity --name sailboat.svg
image-design cancel-image --name concepts/cactus.png
image-design list-intelligence-models
```

See the [CLI reference](docs/02-cli.md) for every flag and the [library reference](docs/01-library.md) for the Python surface.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to set up your development environment.
