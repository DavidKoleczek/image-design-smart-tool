`generate-chatgpt-image` creates or edits an image with the image generation built into Codex. A Codex agent passes
the request to its image tool and the image comes back as a PNG.
It needs the `codex` extra and Codex signed in with ChatGPT, and it counts against that ChatGPT plan. With any other
sign-in it stops before anything is sent, so nothing is billed to an API key.

A new `--name` creates the image. The name of an image that exists edits it and overwrites its file.
Every image made is kept as a version in the data directory, so `restore-image-version` can put an earlier one back.
ChatGPT chooses the size and quality, so an edit can come back at a different size than the image it changes.

```bash
image-design generate-chatgpt-image "A paper-cut cactus in a terracotta pot on a cream background." --name concepts/cactus.png
image-design generate-chatgpt-image "Make the pot blue. Keep everything else unchanged." --name concepts/cactus.png --marks marks.json
```

```python
from image_design.lib import generate_chatgpt_image

run = await generate_chatgpt_image(prompt="A paper-cut cactus in a terracotta pot.", name="concepts/cactus.png")
result = await run.result()
```

`marks.json` holds a list of marks, as for `generate-openai-image`. They are drawn on a copy of the image, which is
sent second, so with marks the references start at image 3.

`--draft` tries an edit without changing the image, as for `generate-openai-image`.

## Arguments

- `PROMPT`: What to make, or what to change. It is passed to the image tool as written.
- `--name`: The image's path in `.image-design`, ending in `.png`.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--reference`: Another image to send with the prompt, such as for a style or a subject. Repeatable. Any image
  format, or an SVG; one other than PNG, JPEG, or WebP is sent as a PNG at its own size. A request sends at most 5
  images, counting the image being edited and its marked copy.
- `--marks`: A JSON file of marks to draw on a copy of the image being edited.
- `--version`: The version to edit, such as `v2`. Defaults to the one in the image's file.
- `--transparent`: Ask for a transparent background.
- `--model`, `--reasoning-effort`: The Codex model that passes the request on, not the image model. The effort defaults
  to `low`. See `image-design list-intelligence-models`.
- `--timeout-seconds`: How long the request may take. Defaults to 600.
- `--origin`: Who asked, such as `app`.
- `--detach`: Leave the run going in a process of its own once it is sent. Stop it with `image-design cancel-image`.
- `--draft`: Edit `--version`, or the version in the image's file, and save the result as a draft instead of a version.
- `--json`: Print each event of the run as a line of JSON instead of text.

## Result

The path of the image's file, or with `--draft` the path of the draft. Progress goes to stderr. The command exits 0
when the run is done and 1 when it failed, timed out, or was cancelled. Ctrl+C cancels it.

```
.image-design/concepts/cactus.png
```

With `--json`, each event is a line of JSON: `started`, a `version` for the image kept, and last `finished` or `failed`,
whose `data` is the result. The run's record in the data directory keeps the prompt the image tool received.
