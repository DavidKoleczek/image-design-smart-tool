# Vision

A one stop shop for anything image creation and editing with AI. It could be used for concept art, infographics, pixel art and so on.

There are sub-capabilities, that directly interact with image generation models. There are capabilities creating, creating (re-generating) from references, and editing.

Directory layout:
- A "workspace" is the top-level directory of the user's project. 
- `.image-design/` in it is the directory for everything related to what you do within this tool and app
  - Rest of the files and directories underneath are the final generated images
  - Except `.agents/` is special in that it holds the data associated with the generated images. Chat logs, history, metadata, etc. Everything except what's needed to reproduce images is gitignored by default.

It has an app that makes it easy to create new images from references and follow a particular style. 
It also has an easy way to mark up images to send feedback for them to be edited. 
It also might have some common, modular image editor capabilities like color grading. 
Eventually those modular capabilities might be ones that each user could customize/develop for themselves based on their own need.
The app can be opened by an agent or embeds its work through an MCP app.

## Non-Goals

- Not meant for videos, or 3D models.

## Principles

- The library is the tool. The CLI and any other surface are thin wrappers over it.
- The intelligence is behind an interface, so another implementation is a new module rather than a rewrite.
- The tool works on Windows, macOS, and Linux seamlessly.
