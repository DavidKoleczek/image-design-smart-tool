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

- `--name`: The folder's path in the directory.
- `--new-name`: The path to give it.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--numbered`: When the new name is taken, take the next free name like it, such as `drafts (2)`, instead of failing.
  Two folders are never merged.

## Result

The folder's new path in the directory.

```
concepts/drafts
```
