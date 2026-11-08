---
smart_tool_format: 1
name: image-design
version: 0.1.0
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
  - name: codex-sign-in
    purpose: >-
      The Codex CLI signed in with ChatGPT or an API key, for the codex agent provider.
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
