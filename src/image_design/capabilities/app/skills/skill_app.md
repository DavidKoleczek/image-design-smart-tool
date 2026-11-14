`app` serves the app, named Image Design Smart Tool, in a browser page on this machine, prints its URL, and keeps serving until interrupted. Only this machine can reach it.

The app's view is an MCP App. The page hosts it the way Claude or VS Code would inline, for agents that cannot. `mcp`'s `open_app` tool serves the same app from inside a session.

In the app the user browses the images of one directory, looks at the versions kept for an image and restores one, and renames, moves, or deletes images. An image made or changed outside the app shows in it within a second or so. `--name` opens the app on an image, and `mcp`'s `open_app` brings one up in an app already open.

The user also creates and edits images there with an OpenAI image model or with ChatGPT, and can stop a request. An edit can be guided by marks drawn on the image, by a mask painted on it, and by reference images that are dropped in, pasted, or picked from the directory, from pinned files and folders, and from what was used before. A request the app starts runs in a process of its own, so it finishes when the app is closed, and its events have `app` as their origin. With an OpenAI image model the user also makes animations, from a prompt or from a still image, and plays one or steps through its frames on a timeline. A request on an animation starts from the frame the user picked, marks drawn on an animation belong to that frame, and one frame can be made a still image of its own. The user also draws SVGs there with an agent, as a conversation that stays with the drawing: each message starts a run that continues the agent's last session, a message sent while the agent works steers it, and marks and references go with a message. The drawing's budgets are set there too, and a drawing exports to PNG, WebP, or JPEG where the user picks in the platform's save dialog. The OpenAI models need a key: `OPENAI_API_KEY` in the environment `app` is started in, or one the user saves from the app's settings. The user types it into a window on the machine, and it is kept in the platform's credential store, so it never passes through the app's view or an agent's session.

```bash
# on a free port; prints the URL, then blocks until Ctrl+C
image-design app

# on a fixed port, so a bookmark keeps working
image-design app --port 8789

# on the images of another directory, open on one of them
image-design app --directory art/concepts --name cactus.png
```

```python
from pathlib import Path

from image_design.lib import app_server, app_view

app = app_server(directory=Path("art/concepts"))
app.open().url  # the browser host page, which reaches app.server at its own /mcp
app.close()
app_view()  # the view's HTML, the MCP App resource
```

`open` returns once the page is listening, so the URL answers at once, and serves from daemon threads until `close` or the process exits.

The app keeps its theme and pane sizes in `image-design/app-settings.json` in the user's config folder, the same for every directory. What was last picked for a directory's images, such as the image shown, the image model and its output options, the agent that draws, and the references pinned there, is kept in `app/app.json` in its data directory.

## Arguments

- `--port N`: The port to bind on `127.0.0.1`. A free one is chosen when omitted.
- `--directory`: Where the images to show are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--name`: An image to open on, by its path in the directory. Defaults to the image the app showed last.

## Result

The URL on stdout, `http://127.0.0.1:<port>`, then nothing more while it serves. Uvicorn writes only warnings and errors to stderr.
