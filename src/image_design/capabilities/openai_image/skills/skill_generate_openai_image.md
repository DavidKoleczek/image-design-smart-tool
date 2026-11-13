`generate-openai-image` creates or edits an image with an OpenAI image model through the Images API.
It needs the `openai` extra and an `OPENAI_API_KEY`. Each request is billed to that key, and it is never retried.

A new `--name` creates the image. The name of an image that exists edits it and overwrites its file.
Every image made is kept as a version in the data directory, so `restore-image-version` can put an earlier one back.

```bash
image-design generate-openai-image "A paper-cut cactus in a terracotta pot on a cream background." --name concepts/cactus.png
image-design generate-openai-image "Make the pot blue. Keep everything else unchanged." --name concepts/cactus.png --marks marks.json
```

```python
from image_design.lib import generate_openai_image

run = await generate_openai_image(prompt="A paper-cut cactus in a terracotta pot.", name="concepts/cactus.png")
result = await run.result()
```

`marks.json` holds a list of marks. Points are fractions of the image's width and height from its top left: two
opposite corners for a `circle` or `box`, the tail then the head for an `arrow`, and each point along a `sketch`.

```json
[{"shape": "circle", "points": [[0.4, 0.5], [0.6, 0.9]], "color": "red", "note": "this pot"}]
```

## Arguments

- `PROMPT`: What to make, or what to change.
- `--name`: The image's path in the directory. Its extension sets the format: `.png`, `.jpg`, `.webp`, or `.gif` for an
  animation.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory. Pass the same one
  every time.
- `--reference`: Another image to send with the prompt, such as for a style or a subject. Repeatable. Any image
  format, or an SVG; one other than PNG, JPEG, or WebP is sent as a PNG at its own size.
- `--marks`: A JSON file of marks drawn over the image being edited, sent as a separate layer.
- `--mask`: An image the image's size, transparent where the model may make changes, sent as a PNG. Only for edits of
  still images, and not with `--marks`. The model treats it as guidance.
- `--version`: The version to edit, such as `v2`. Defaults to the one in the image's file.
- `--frame`: When the image being edited is an animation, the frame to send, from 0.
- `--model`: `gpt-image-2.6-sunburst`, the default, or the faster `gpt-image-2.6-flare`.
- `--size`: `WIDTHxHEIGHT`, in multiples of 16. Defaults to the API's choice, and to the image's own size for an edit.
- `--quality`: `low`, `medium`, `high`, `xhigh`, `max`, or `auto`.
- `--complexity`: How much the model plans the image: `low`, `medium`, or `high`.
- `--background`: `transparent`, `opaque`, or `auto`. Transparent needs a `.png` or `.webp`.
- `--compression`: 0 to 100, for a `.jpg` or `.webp`.
- `--count`: How many images to make, 1 to 10. The first goes in the image's file, and each is kept as a version.
- `--frames`, `--frame-ms`: For a `.gif`, 2 to 16 frames, each shown for 20 to 2000 ms. An edit of a `.gif` keeps
  the image's own.
- `--previews`: In-progress images to receive before the final one, 0 to 3. Each adds 100 output tokens to the cost.
  Only with a `--count` of 1, and not for a `.gif`.
- `--timeout-seconds`: How long the request may take. Defaults to 600.
- `--origin`: Who asked, such as `app`.
- `--detach`: Leave the run going in a process of its own once it is sent. Stop it with `image-design cancel-image`.
- `--json`: Print each event of the run as a line of JSON instead of text.

## Result

The path of each image made, one per line: the image's file, then the version files of any more. Progress goes to
stderr. The command exits 0 when the run is done and 1 when it failed, timed out, or was cancelled. Ctrl+C cancels it.

```
.image-design/concepts/cactus.png
```

With `--json`, each event is a line of JSON: `started`, a `preview` for each in-progress image, a `version` for each
image kept, and last `finished` or `failed`, whose `data` is the result. The result has the run's `status`, the
`versions` it made, and its `usage`: tokens, and their cost in US dollars at the model's published prices.
