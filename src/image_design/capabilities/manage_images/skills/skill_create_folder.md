`create-folder` makes a folder in the directory, and any folder above it. A folder stays until `delete-folder` removes
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

- `--name`: The folder's path in the directory.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--numbered`: When the name is taken, take the next free name like it, such as `drafts (2)`, instead of failing.

## Result

The folder's path in the directory.

```
concepts/drafts
```
