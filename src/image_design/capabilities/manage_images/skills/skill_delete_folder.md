`delete-folder` deletes every image in a folder as `delete-image` does, with everything kept for each, and then the
folder and the folders in it. Nothing of the images can be restored afterward. A file in the folder that is not an
image is never deleted, and the folder stays to hold it.

```bash
image-design delete-folder --name concepts/drafts
```

```python
from image_design.lib import delete_folder

left = delete_folder(name="concepts/drafts")
```

## Arguments

- `--name`: The folder's path in `.image-design`.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.

## Result

Prints nothing and exits 0 once the folder is gone. When files that are not images are left in it, it names them, and
the library returns their paths in `.image-design`:

```
Deleted the images in concepts/drafts. It still holds what the tool does not delete: concepts/drafts/notes.txt
```
