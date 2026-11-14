`check-svg-image` measures an SVG image: its canvas and bytes against its budgets, its shapes and colors, its named
parts, and what resvg does not render, such as scripts and animation. It only reports; nothing passes or fails. The budgets are
those of the image's last drawing, and an SVG the tool did not draw is measured against its own size.

```bash
image-design check-svg-image --name sailboat.svg
```

```python
from image_design.lib import check_svg_image

check = check_svg_image(name="sailboat.svg")
```

## Arguments

- `--name`: The image's path in the directory, ending in `.svg`.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--json` (library: the `SvgCheck` returned): the check as JSON instead of text.

## Result

```
Canvas: 512x512. The SVG declares 512x512, with viewBox 0 0 512 512.
Shapes: 24.
Colors: 5: #1d3557, #457b9d, #a8dadc, #e63946, #f1faee.
Bytes: 3,912.
Named parts:
- sky (2 shapes)
- boat (6 shapes)
- boat/sail (2 shapes)
Not rendered by resvg: nothing.
```
