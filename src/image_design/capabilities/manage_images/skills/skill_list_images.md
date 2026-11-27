`list-images` lists every image in a workspace's `.image-design`, in name order. An image file you put there yourself
is listed too, with no versions until the tool changes it. Folders are listed as well, in `--json` as `folders`. A
workspace with no `.image-design` yet lists as empty.

```bash
image-design list-images
image-design list-images --workspace ~/projects/garden --json
```

```python
from image_design.lib import list_images

listing = list_images()
```

## Arguments

- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--json` (library: the `ImageListing` returned): the listing as JSON instead of text, with every version of every
  image, its last run, and every folder.

## Result

One line per image: its size, which version its file holds, and the status of its last run. Then one line per folder
with no image in it.

```
- concepts/cactus.png: 1024x1024, holds v2, done
- photo.jpg: 800x600, has no versions yet
- sailboat.svg: 512x512, holds v1, running
- drafts/: no images
```

An image listed as `has no file` may have been moved outside the tool, and the listing then names `relink-images`,
which finds it.
