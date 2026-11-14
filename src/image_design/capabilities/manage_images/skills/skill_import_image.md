`import-image` brings an image file from anywhere on this machine into the directory as a new image. The file is
copied and left as it is. The copy is the image's first version, so a later edit can go back to it. A PNG, JPEG, WebP,
GIF, or SVG is kept as it is, and any other still image, such as a BMP or TIFF, is kept as a PNG.

An image file already in the directory needs no import to be listed or edited. Importing it where it is keeps it as
the image's first version right away.

```bash
image-design import-image --path ~/Pictures/desk.jpeg
image-design import-image --path ~/Pictures/desk.jpeg --name photos/
image-design import-image --path ~/Pictures/desk.jpeg --name photos/my-desk.jpg
```

```python
from pathlib import Path

from image_design.lib import import_image

summary = import_image(path=Path.home() / "Pictures" / "desk.jpeg", name="photos/")
```

## Arguments

- `--path`: The image file to bring in.
- `--name`: The image's path in the directory. Leave it out for the file's own name at the top of the directory, or end
  it in a slash, such as `photos/`, for the file's name in that folder. A full name ends in the extension the file
  comes in as: `.jpg` for a JPEG, and `.png` for a format that is converted.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--numbered`: When the name is taken, take the next free name like it, such as `desk (2).jpg`, instead of failing.
- `--json` (library: the `ImageSummary` returned): the image as JSON instead of text.

## Result

The image, then its first version.

```
.image-design/photos/desk.jpg holds v1.

- v1 (in the file): 800x600, imported
```
