`copy-image` makes another image with a copy of an image's file and of everything kept for it: its versions, its
runs, and for a drawn SVG its script and sessions. The two are separate images from then on. The new name keeps the
extension, since copying an image does not convert it. An image a run is working on cannot be copied until the run
ends.

```bash
image-design copy-image --name cactus.png --new-name concepts/cactus.png
```

```python
from image_design.lib import copy_image

summary = copy_image(name="cactus.png", new_name="concepts/cactus.png")
```

## Arguments

- `--name`: The image's path in `.image-design`.
- `--new-name`: The copy's path, with the same extension.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--numbered`: When the new name is taken, take the next free name like it, such as `cactus (2).png`, instead of
  failing.
- `--json` (library: the `ImageSummary` returned): the copy as JSON instead of text.

## Result

The copy, then every version of it.

```
.image-design/concepts/cactus.png holds v2.

- v1: 1024x1024, openai
- v2 (in the file): 1024x1024, openai
```
