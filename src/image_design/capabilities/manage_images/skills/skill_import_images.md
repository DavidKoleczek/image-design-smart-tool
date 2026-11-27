`import-images` brings image files, and folders of them, from anywhere on this machine into the workspace as new
images. Each file is copied and left as it is, and kept as `import-image` keeps it: the copy is the image's first
version, a PNG, JPEG, WebP, GIF, or SVG as it is, and any other still image as a PNG. Use it to bring a project's
existing images, wherever they are kept, into its `.image-design`.

A folder comes in under its own name, with the folders in it. Of its files only images come in, by their extensions,
and hidden files and folders are left out. A name that is taken takes the next free one like it, such as
`cactus (2).png` or `photos (2)`, so nothing in the workspace is overwritten. A file or folder that cannot come in is
left out with why, and the rest still come in.

```bash
image-design import-images ~/Pictures/desk.jpeg ~/Pictures/lamp.png
image-design import-images ~/Pictures/trip --folder photos
image-design import-images art/ --workspace ~/projects/garden --json
```

```python
from pathlib import Path

from image_design.lib import import_images

imports = import_images(paths=[Path.home() / "Pictures" / "trip"], folder="photos")
```

## Arguments

- `PATHS`: The image files and folders to bring in, one or more.
- `--folder`: The folder in `.image-design` to bring them into, made if need be. Defaults to its top.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--json` (library: the `ImageImports` returned): what came in as JSON instead of text.

## Result

The path of each image brought in, one per line, and on stderr each file or folder left out, with why. Exits 1 when
nothing came in.

```
.image-design/photos/trip/beach.png
.image-design/photos/trip/day 2/pier.jpg
```

With `--json`, `images` is each new image's summary, `folders` each folder made, by its path in `.image-design`, and
`refused` each file or folder left out, with its `name`, its `reason`, and the `message` saying what to do:

```json
{
  "images": [{"name": "photos/trip/beach.png", "path": "/home/me/project/.image-design/photos/trip/beach.png", ...}],
  "folders": ["photos/trip", "photos/trip/day 2"],
  "refused": [
    {"name": "trip/broken.png", "reason": "not-an-image", "message": "/home/me/Pictures/trip/broken.png is not an ..."}
  ]
}
```
