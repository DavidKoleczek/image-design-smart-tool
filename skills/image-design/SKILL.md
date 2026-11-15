---
name: image-design
description: >-
  Image creation and editing workspace. Drive it from the command line as `image-design`, or from Python through
  `image_design.lib`. Triggers on "image-design".
license: MIT
metadata:
  version: "0.2.0"
---

# Using image-design

Image creation and editing workspace.

## Install

The tool installs from its repository, https://github.com/DavidKoleczek/image-design-smart-tool.

```bash
# as a CLI, choosing the extras you want: [all], [codex], [claude], or [openai]
uv tool install "image-design[all] @ git+https://github.com/DavidKoleczek/image-design-smart-tool"

# as a library, from another project
uv add "image-design[all] @ git+https://github.com/DavidKoleczek/image-design-smart-tool"

# once, without installing
uvx --from "image-design[all] @ git+https://github.com/DavidKoleczek/image-design-smart-tool" image-design --help
```

## Use it

Run `image-design --help`. It prints the tool's skill: when to use it, every capability, sharp
edges, and which files to read. Follow it. Then read the capability's own skill with
`image-design <command> --help` before calling it: it carries the arguments, a worked
invocation, and the result. Never work from memory.

## Keep it current

Keep the tool up to date for the user by default if the permission mode allows it using `uv tool upgrade image-design`.
Keep the skill up to date for the user with `npx skills update`, adding `-g` for global installs. It was added with `npx skills add DavidKoleczek/image-design-smart-tool`.
Do not try to get around restrictions or operate against the user's preferences to update tools (or skills).
