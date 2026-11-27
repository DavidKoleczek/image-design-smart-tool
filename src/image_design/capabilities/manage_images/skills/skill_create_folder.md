`create-folder` makes a folder in the workspace's `.image-design`, and any folder above it. A folder stays until `delete-folder` removes
it, whether or not it holds an image. An image's name can also name a folder that does not exist yet, which is then
made with the image.

```bash
image-design create-folder --name concepts/drafts
```

```python
from image_design.lib import create_folder

name = create_folder(name="concepts/drafts")
```

## Arguments

- `--name`: The folder's path in `.image-design`.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--numbered`: When the name is taken, take the next free name like it, such as `drafts (2)`, instead of failing.

## Result

The folder's path in `.image-design`.

```
concepts/drafts
```
