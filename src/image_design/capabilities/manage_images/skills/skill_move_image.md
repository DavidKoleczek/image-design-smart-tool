`move-image` renames an image, or moves it to another folder of the directory. The image keeps its versions and its
history. The new name keeps the extension, since moving an image does not convert it.

```bash
image-design move-image --name cactus.png --new-name concepts/cactus.png
```

```python
from image_design.lib import move_image

summary = move_image(name="cactus.png", new_name="concepts/cactus.png")
```

## Arguments

- `--name`: The image's path in the directory.
- `--new-name`: The path to give it, with the same extension.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--json` (library: the `ImageSummary` returned): the image as JSON instead of text.

## Result

The image under its new name, then every version of it.

```
.image-design/concepts/cactus.png holds v2.

- v1: 1024x1024, openai
- v2 (in the file): 1024x1024, openai
```
