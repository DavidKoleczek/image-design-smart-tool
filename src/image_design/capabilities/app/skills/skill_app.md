`app` serves the app, named Image Design Smart Tool, in a browser page on this machine, prints its URL, and keeps serving until interrupted. Only this machine can reach it.

The app's view is an MCP App. The page hosts it the way Claude or VS Code would inline, for agents that cannot. `mcp`'s `open_app` tool serves the same app from inside a session.

```bash
# on a free port; prints the URL, then blocks until Ctrl+C
image-design app

# on a fixed port, so a bookmark keeps working
image-design app --port 8789
```

```python
from image_design.lib import app_server, app_view

app = app_server()
app.open().url  # the browser host page, which reaches app.server at its own /mcp
app.close()
app_view()  # the view's HTML, the MCP App resource
```

`open` returns once the page is listening, so the URL answers at once, and serves from daemon threads until `close` or the process exits.

## Arguments

- `--port N`: The port to bind on `127.0.0.1`. A free one is chosen when omitted.

## Result

The URL on stdout, `http://127.0.0.1:<port>`, then nothing more while it serves. Uvicorn writes only warnings and errors to stderr.
