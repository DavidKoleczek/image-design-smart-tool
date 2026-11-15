`add-image-version` keeps a file as the next version of an image that exists, and puts it in the image's file, as a
run's first image is. It is for what a script makes of an image, such as an exact crop, a composite of an approved
edit into the original, or a background made transparent, which no image call should redo. The file is copied and
left as it is, and `restore-image-version` can put the version before back.

The file has to be in the image's format: a PNG for a `.png`, and so on, except that any still image becomes a PNG for a
`.png`. A file in another format is refused; bring it in as an image of its own with `import-image`. A version kept
from the processes of the agent `design-image` started names that agent's run.

```bash
image-design add-image-version --name concepts/cactus.png --path cropped.png
```

```python
from pathlib import Path

from image_design.lib import add_image_version

summary = add_image_version(name="concepts/cactus.png", path=Path("cropped.png"))
```

## Arguments

- `--name`: The image's path in the directory.
- `--path`: The file to keep as its next version.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--json` (library: the `ImageSummary` returned): the image as JSON instead of text.

## Result

The version now in the file, then every version of the image. A kept file's method is `imported`.

```
.image-design/concepts/cactus.png holds v3.

- v1: 1024x1024, openai
- v2: 1024x1024, openai
- v3 (in the file): 812x904, imported
```
