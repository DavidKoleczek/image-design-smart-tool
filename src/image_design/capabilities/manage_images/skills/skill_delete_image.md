`delete-image` deletes an image's file and everything kept for it: its versions, its runs, and for a drawn SVG its
script and sessions. A run working on the image is stopped first. Nothing of the image can be restored afterward.
The folder it was in stays, even when it is left empty; `delete-folder` removes a folder.

```bash
image-design delete-image --name concepts/cactus.png
```

```python
from image_design.lib import delete_image

delete_image(name="concepts/cactus.png")
```

## Arguments

- `--name`: The image's path in `.image-design`.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.

## Result

Prints nothing and exits 0 once the image is gone.
