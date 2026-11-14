`view-image` prints one image and its versions, and records it as the image viewed last. The app opens on that image,
and shows it when this is called while the app is open.

```bash
image-design view-image --name concepts/cactus.png
```

```python
from image_design.lib import view_image

summary = view_image(name="concepts/cactus.png")
```

## Arguments

- `--name`: The image's path in the directory.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--json` (library: the `ImageSummary` returned): the image as JSON instead of text, with its last run and the request
  that run was given.

## Result

The version in the file, then every version of the image.

```
.image-design/concepts/cactus.png holds v2.

- v1: 1024x1024, openai
- v2 (in the file): 1024x1024, openai
```
