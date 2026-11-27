`move-image` renames an image, or moves it to another folder of `.image-design`. The image keeps its versions and its
history. The new name keeps the extension, since moving an image does not convert it. Move images with this rather
than a file manager, which leaves the tool without the image's new name; `relink-images` repairs that. A folder the
image leaves stays, even when it is left empty.

```bash
image-design move-image --name cactus.png --new-name concepts/cactus.png
```

```python
from image_design.lib import move_image

summary = move_image(name="cactus.png", new_name="concepts/cactus.png")
```

## Arguments

- `--name`: The image's path in `.image-design`.
- `--new-name`: The path to give it, with the same extension.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--numbered`: When the new name is taken, take the next free name like it, such as `cactus (2).png`, instead of
  failing.
- `--json` (library: the `ImageSummary` returned): the image as JSON instead of text.

## Result

The image under its new name, then every version of it.

```
.image-design/concepts/cactus.png holds v2.

- v1: 1024x1024, openai
- v2 (in the file): 1024x1024, openai
```
