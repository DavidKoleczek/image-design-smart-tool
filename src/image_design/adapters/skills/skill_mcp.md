`mcp` runs the tool's MCP server over stdio, with the app as an [MCP App](https://github.com/modelcontextprotocol/ext-apps).

Configure the client to launch the command `image-design` with the single argument `mcp`.
The client owns the process. Do not run it yourself in a terminal: it waits for an MCP client on stdin.
Nothing is served until `open_app` is called, so each session gets its own app on its own free port, and a session that never opens it binds nothing.

```json
{ "mcpServers": { "image-design": { "command": "image-design", "args": ["mcp"] } } }
```

The library has no `mcp` function. The command calls `run_stdio()` in `image_design.adapters.mcp`, which serves `app_server().server` from the library over stdio.

## Tools

- `open_app`: serves the app and returns its browser URL. Its `_meta.ui.resourceUri` names the view, so a host that renders MCP Apps shows it inline. A client that takes URL elicitation, such as Claude Code, is asked to open the URL in the browser. Calling it again returns the same URL.

## Resources

- `ui://image-design/app`: the view, listed only to hosts that render MCP Apps.
