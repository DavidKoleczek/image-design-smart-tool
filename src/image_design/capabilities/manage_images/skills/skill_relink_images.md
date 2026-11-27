`relink-images` finds the images whose files were moved or renamed outside the tool, in a file manager or from a
shell, and keeps each under the name its file now has. Such an image is listed with no file, and its file is listed as
another image with no versions, until it is relinked.

An image is relinked when a file the tool keeps nothing for holds exactly what the image's current version does. A file
that only has the image's file name, as after it was changed and then moved, is reported as likely and left alone
until you name the image with `--likely`.

```bash
image-design relink-images
image-design relink-images --likely cactus.png
```

```python
from image_design.lib import relink_images

relinking = relink_images()
```

## Arguments

- `--likely`: An image to relink to its likely file as well, by the name it is kept under. Repeat it for each.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--json` (library: the `ImageRelinking` returned): what was relinked, what is likely, and what is still gone, as JSON
  instead of text.

## Result

One line per image whose file was gone.

```
Relinked cactus.png to concepts/cactus.png.
fern.png has no file, and plants/fern.png may be it, with other content than its current version. To take it: image-design relink-images --likely fern.png
logo.svg has no file, and no file in the directory could be it.
```

When no image is missing its file:

```
Every image has its file.
```
