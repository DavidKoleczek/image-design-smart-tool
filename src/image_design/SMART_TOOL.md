---
smart_tool_format: 1
name: image-design
version: 0.2.0
description: >-
  Image creation and editing workspace
use_cases:
  - >-
    Generate a new image, such as concept art or an infographic
  - >-
    Edit an existing image
platforms:
  - linux
  - macos
  - windows
requires:
  - name: uv
    purpose: >-
      uv on PATH for using the tool and agents to run generated scripts.
    optional: false
    install: https://docs.astral.sh/uv/getting-started/installation/
  - name: openai-api-key
    purpose: >-
      OPENAI_API_KEY, and image-design installed with the openai extra, for generate-openai-image.
      Without them, images cannot be made through the OpenAI Images API. Each request is billed to the key.
    optional: true
    install: https://platform.openai.com/api-keys
  - name: codex-sign-in
    purpose: >-
      The Codex CLI signed in with ChatGPT or an API key, for the codex agent provider.
      generate-chatgpt-image needs the ChatGPT sign-in.
      Without it, the agentic capabilities cannot run through codex.
    optional: true
    install: https://developers.openai.com/codex/auth
  - name: claude-credentials
    purpose: >-
      ANTHROPIC_API_KEY, or a cloud provider's credentials, for the claude agent provider.
      Without them, the agentic capabilities cannot run through claude.
    optional: true
    install: https://code.claude.com/docs/en/agent-sdk/quickstart
---

Image creation and editing tool.
