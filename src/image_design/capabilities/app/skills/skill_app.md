`app` serves the app, named Image Design, in a browser page on this machine, prints its URL, and keeps serving until interrupted. Only this machine can reach it.

The app's view is an MCP App. The page hosts it the way Claude or VS Code would inline, for agents that cannot. `mcp`'s `open_app` tool serves the same app from inside a session.

`app` starts from any directory. It opens on the workspace opened last in an app, and when there is none the user picks one first: an existing project's top-level folder, or a new folder made for one. The top bar names the workspace, and the user switches to another there. A run started in one workspace goes on while the app shows another.

In the app the user browses the images of one workspace, brings in image files or whole folders of them, looks at the versions kept for an image and restores one, and renames, moves, or deletes images. Each image being worked on, and each new image, has a tab of its own, so switching between them keeps everything in progress, and closing one drops what was in progress there. An image opened with a click takes the preview tab until something is done in it. An image made or changed outside the app shows in it within a second or so. `--name` opens the app on an image, and `mcp`'s `open_app` brings one up in an app already open.

The user also creates and edits images there by talking to an agent, as a conversation that stays with the image: the agent writes each image call to the image model the user picked for it, one of OpenAI's or ChatGPT's, and makes it, choosing the call's other settings itself unless the user picked a size or quality for a new image, each call shows as a card that opens to exactly what was sent, a message sent while the agent works steers it, and Continue session keeps the agent's memory of the conversation. An image call can also be written by hand, or one the agent made opened in the editor, changed, and sent again, with no agent. The user can stop either. A new image goes in the folder picked for it, which starts as the folder the user is in. An edit can be guided by marks drawn on the image, by a mask painted on it, and by reference images that are dropped in, pasted, or picked from the workspace's images, from the earlier versions of its images, from pinned files and folders, and from what was used before. A request the app starts runs in a process of its own, so it finishes when the app is closed, and its events have `app` as their origin. With an OpenAI image model the user also makes animations, from a prompt or from a still image, and plays one or steps through its frames on a timeline. A request on an animation starts from the frame the user picked, marks drawn on an animation belong to that frame, and one frame can be made a still image of its own. The user also draws SVGs there with an agent, as a conversation that stays with the drawing: each message starts a run that continues the agent's last session, a message sent while the agent works steers it, and marks and references go with a message. The drawing's budgets are set there too, and a drawing exports to PNG, WebP, or JPEG where the user picks in the platform's save dialog. The OpenAI models need a key: `OPENAI_API_KEY` in the environment `app` is started in, or one the user saves from the app's settings. The user types it into a window on the machine, and it is kept in the platform's credential store, so it never passes through the app's view or an agent's session.

```bash
# on a free port, on the workspace opened last; prints the URL, then blocks until Ctrl+C
image-design app

# on a fixed port, so a bookmark keeps working
image-design app --port 8789

# on the images of a workspace, open on one of them
image-design app --workspace ~/projects/garden --name concepts/cactus.png
```

```python
from pathlib import Path

from image_design.lib import app_server, app_view

app = app_server(workspace=Path.home() / "projects" / "garden")
app.open().url  # the browser host page, which reaches app.server at its own /mcp
app.close()
app_view()  # the view's HTML, the MCP App resource
```

`open` returns once the page is listening, so the URL answers at once, and serves from daemon threads until `close` or the process exits.

The app keeps its theme and pane sizes in `image-design/app-settings.json` in the user's config folder, the same for every workspace, and the workspaces opened in it in `app-workspaces.json` beside that. What was last picked for a workspace's images, such as the image shown and the images open in tabs, the image model and its output options, the agent that draws, the image's agent with its image model and a new image's size and quality, and the references pinned there, is kept in `.image-design/.agents/app/app.json` in the workspace.

## Arguments

- `--port N`: The port to bind on `127.0.0.1`. A free one is chosen when omitted.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images to show. Defaults to the workspace opened last that is still a folder; with none, the user picks one in the app.
- `--name`: An image to open on, by its path in `.image-design`. Defaults to the image the app showed last. Needs a workspace to open it in.

## Result

The URL on stdout, `http://127.0.0.1:<port>`, then nothing more while it serves. Uvicorn writes only warnings and errors to stderr.
