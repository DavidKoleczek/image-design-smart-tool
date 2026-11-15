`cancel-image` stops the run working on an image, whichever process runs it, such as one started with `--detach`.

```bash
image-design cancel-image --name concepts/cactus.png
```

```python
from image_design.lib import cancel_image

cancel_image(name="concepts/cactus.png")
```

## Arguments

- `--name`: The image's path in the directory.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.

## Result

Prints nothing and exits 0 once the run is asked to stop. The run ends `cancelled` within a second or two.
