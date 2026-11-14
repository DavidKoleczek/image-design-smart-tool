`export-svg-image` renders an SVG image, or one of its versions, to a `.png`, `.jpg`, or `.webp` file at a scale of
its canvas size, with resvg. A `.jpg` has no transparency, so what is see-through shows white.

```bash
image-design export-svg-image --name sailboat.svg --output exports/sailboat@2x.png --scale 2
```

```python
from pathlib import Path

from image_design.lib import export_svg_image

written = export_svg_image(name="sailboat.svg", output=Path("exports/sailboat@2x.png"), scale=2)
```

## Arguments

- `--name`: The image's path in the directory, ending in `.svg`.
- `--output`: The file to write, ending in `.png`, `.jpg`, or `.webp`. Its folder is made if need be.
- `--scale`: Times the canvas size. Defaults to 1.
- `--version`: The version to render, such as `v2`. Defaults to the one in the image's file.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.

## Result

The path of the file written.

```
exports/sailboat@2x.png
```
