`mcp` runs the tool's MCP server over stdio, with the app as an [MCP App](https://github.com/modelcontextprotocol/ext-apps).

Configure the client to launch the command `image-design` with the single argument `mcp`.
The client owns the process. Do not run it yourself in a terminal: it waits for an MCP client on stdin.
Nothing is served until `open_app` is called, so each session gets its own app on its own free port, and a session that never opens it binds nothing.

```json
{ "mcpServers": { "image-design": { "command": "image-design", "args": ["mcp"] } } }
```

The library has no `mcp` function. The command calls `run_stdio()` in `image_design.adapters.mcp`, which serves `app_server().server` from the library over stdio.

## Arguments

- `--directory`: Where the images to show are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.

## Tools

- `open_app`: serves the app and returns its browser URL and the directory it shows. Its `_meta.ui.resourceUri` names the view, so a host that renders MCP Apps shows it inline. A client that takes URL elicitation, such as Claude Code, is asked to open the URL in the browser. Calling it again returns the same URL. Pass `directory`, and `data_directory` when it is not `.agents` in that directory, to switch the app to other images.

The view calls the server's other tools, such as `list_images`, `generate_openai_image`, `cancel_image`, and `save_app_settings`. They are listed only to hosts that render MCP Apps and are marked for the app alone, so an agent uses the CLI instead.

## Resources

Listed only to hosts that render MCP Apps.

- `ui://image-design/app`: the view.
- `image-design://images/{+name}`: an image's file, as base64, for the view.
- `image-design://versions/{version}/{+name}`: a version kept for an image, such as `v2`.
- `image-design://thumbnails/{version}/{+name}`: a small WebP of a version, or of the image's file when the version is `file`.
- `image-design://previews/{run}/{index}/{+name}`: an in-progress image of a run, by the run's ID and the index its `preview` event has.
- `image-design://references/{+path}`: a small WebP of an image the app offers as a reference, by its path on this machine.
