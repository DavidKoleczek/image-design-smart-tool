`restore-image-version` puts an earlier version of an image back in its file. If the file was changed by hand since
the tool last wrote it, the file is kept as a version of its own first, so nothing is lost.

```bash
image-design restore-image-version --name concepts/cactus.png --version v1
```

```python
from image_design.lib import restore_image_version

summary = restore_image_version(name="concepts/cactus.png", version="v1")
```

## Arguments

- `--name`: The image's path in `.image-design`.
- `--version`: The version to put back, such as `v1`.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--json` (library: the `ImageSummary` returned): the image as JSON instead of text.

## Result

The version now in the file, then every version of the image.

```
.image-design/concepts/cactus.png holds v1.

- v1 (in the file): 1024x1024, openai
- v2: 1024x1024, openai
```
