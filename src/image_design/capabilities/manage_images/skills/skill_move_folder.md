`move-folder` renames a folder, or moves it into another, with everything in it. Its images keep their versions and
their history under their new names. Move folders with this rather than a file manager, which leaves the tool without
the images' new names. The move is refused while a run works on an image in the folder.

```bash
image-design move-folder --name drafts --new-name concepts/drafts
```

```python
from image_design.lib import move_folder

name = move_folder(name="drafts", new_name="concepts/drafts")
```

## Arguments

- `--name`: The folder's path in `.image-design`.
- `--new-name`: The path to give it.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--numbered`: When the new name is taken, take the next free name like it, such as `drafts (2)`, instead of failing.
  Two folders are never merged.

## Result

The folder's new path in `.image-design`.

```
concepts/drafts
```
