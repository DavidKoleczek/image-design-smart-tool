`delete-image` deletes an image's file and everything kept for it: its versions, its runs, and for a drawn SVG its
script and sessions. A run working on the image is stopped first. Nothing of the image can be restored afterward.

```bash
image-design delete-image --name concepts/cactus.png
```

```python
from image_design.lib import delete_image

delete_image(name="concepts/cactus.png")
```

## Arguments

- `--name`: The image's path in the directory.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.

## Result

Prints nothing and exits 0 once the image is gone.
