`draw-svg-image` creates or edits an SVG image with an agent that draws it with code. The agent writes `image.py`, a
script with inline dependencies that writes the SVG, runs it with uv, renders the SVG with resvg, looks at the render,
and fixes what does not match the request. It needs uv on PATH and the `codex` or `claude` extra.

A new `--name` creates the image. The name of an image that exists edits it and overwrites its file. To redraw another
image, such as a PNG, as an SVG, pass it with `--reference` and name a new `.svg`.
Every drawing is kept as a version with the `image.py` that built it, so `restore-image-version` can put an earlier
one back. `image.py` is kept with the image's data and committed with the project, so the drawing can go on changing.
The agent puts each part in a named group, so a later request can change one part without redrawing the rest.

```bash
image-design draw-svg-image "A flat vector sailboat on calm water at sunset. No text." --name sailboat.svg
image-design draw-svg-image "Make the sail red." --name sailboat.svg --marks marks.json --resume-session true
```

```python
from image_design.lib import draw_svg_image

run = await draw_svg_image(prompt="A flat vector sailboat on calm water at sunset. No text.", name="sailboat.svg")
result = await run.result()
```

`marks.json` holds a list of marks, as for `generate-openai-image`. They are drawn on the render the agent is shown,
and the agent is told which named parts of the drawing are under each.

## Arguments

- `PROMPT`: What to draw, or what to change.
- `--name`: The image's path in the directory, ending in `.svg`.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory. Pass the same one
  every time.
- `--reference`: An image to show the agent with the prompt, such as a style or a subject. Repeatable. Any format.
- `--marks`: A JSON file of marks to draw on the render the agent is shown.
- `--canvas`: `WIDTHxHEIGHT`. Defaults to 512x512 for a new drawing, and to the image's own for an edit.
- `--max-shapes`, `--max-colors`, `--max-bytes`: The most elements that draw, distinct colors, and bytes of SVG, or
  `none` for no limit. None by default. The agent is told them, and `check-svg-image` measures them; an edit keeps
  each one left out.
- `--resume-session`: `true` to go on in the image's last agent session, so the agent remembers the earlier requests,
  or a session ID. `false` by default.
- `--agent-provider`: `codex` or `claude`. Defaults to the resumed session's, else the first installed.
- `--model`, `--reasoning-effort`: The agent's model and its effort. See `image-design list-intelligence-models`.
- `--timeout-seconds`: How long the agent may work. Defaults to 600.
- `--origin`: Who asked, such as `app`.
- `--detach`: Leave the agent going in a process of its own once it starts. Follow it with `read-image-activity`,
  message it with `steer-svg-image`, and stop it with `cancel-image`.
- `--json`: Print each event of the run as a line of JSON instead of text.

## Result

The path of the image's file. What the agent says and the tools it calls go to stderr. The command exits 0 when the
run is done and 1 when it failed, timed out, or was cancelled. Ctrl+C cancels it. An agent that stopped keeps its work,
so `--resume-session true` goes on from there.

```
.image-design/sailboat.svg
```

With `--json`, each event is a line of JSON: `started`, an `agent` event for each thing the agent does, a `preview`
with the path of each render it builds, a `steered` for each message sent to it, a `version` for the drawing kept, and
last `finished` or `failed`, whose `data` is the result. The result has the run's `status`, the `versions` it made,
and its `usage`: the agent's tokens, and their cost in US dollars when the agent provider reports it.
