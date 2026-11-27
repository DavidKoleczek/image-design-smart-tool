`view-image` prints one image and its versions. For an animation it also prints each frame and how long it shows,
and with `--frames-output` it writes each frame as a PNG, so an animation can be looked at one frame at a time.
`--version` views an earlier version instead of the image's file. A frame's index is what `--frame` names in
`generate-openai-image`.

```bash
image-design view-image --name concepts/cactus.png
image-design view-image --name loops/sway.gif --version v1 --frames-output frames/sway
```

```python
from pathlib import Path

from image_design.lib import view_image

view = view_image(name="loops/sway.gif", version="v1", frames_output=Path("frames/sway"))
```

## Arguments

- `--name`: The image's path in `.image-design`.
- `--version`: The version to view frame by frame, such as `v2`. Defaults to the one in the image's file.
- `--frames-output`: A folder to write each frame to, as `frame-<index>.png`. Its folders are made if need be. Without
  it, nothing is written.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--json` (library: the `ImageView` returned): the image as JSON instead of text, with its last run, the request that
  run was given, and in `viewed` each frame of what was viewed.

## Result

The version in the file, then every version of the image. For an animation, or with `--version` or `--frames-output`,
then what was viewed: its size, each frame's duration, and the file written for each.

```
.image-design/loops/sway.gif holds v2.

- v1: 512x512, 3 frames, openai
- v2 (in the file): 512x512, 4 frames, openai

loops/sway.gif v1: 3 frames of 512x512, 600 ms in all.

- 0: 200 ms, frames/sway/frame-0.png
- 1: 200 ms, frames/sway/frame-1.png
- 2: 200 ms, frames/sway/frame-2.png
```
