`add-image-version` keeps a file as the next version of an image that exists, and puts it in the image's file, as a
run's first image is. It is for what a script makes of an image, such as an exact crop, a merge of an approved edit or
of several drafts into the original, or a background made transparent, which no image call should redo. The file is
copied and left as it is, and `restore-image-version` can put the version before back.

The file has to be in the image's format: a PNG for a `.png`, and so on, except that any still image becomes a PNG for a
`.png`. A file in another format is refused; bring it in as an image of its own with `import-image`. A version kept
from the processes of the agent `design-image` started names that agent's run.

It also keeps a draft, which `generate-openai-image --draft` or `generate-chatgpt-image --draft` made, as the next
version, as if the draft's call had made it. A draft is named by its run id, which is the name of the folder its file
is in.

```bash
image-design add-image-version --name concepts/cactus.png --path cropped.png
image-design add-image-version --name concepts/cactus.png --draft 20260101-120000-a1b2c3
image-design add-image-version --name concepts/cactus.png --path merged.png --draft 20260101-120000-a1b2c3 --draft 20260101-120005-d4e5f6
```

```python
from pathlib import Path

from image_design.lib import add_image_version

summary = add_image_version(name="concepts/cactus.png", path=Path("cropped.png"))
```

## Arguments

- `--name`: The image's path in the directory.
- `--path`: The file to keep as its next version. Leave it out to keep a draft as it is.
- `--draft`: A draft of the image, by its run id. Alone, the draft to keep. With `--path`, a draft the file was made
  from, such as by merging drafts, which the version names. Repeatable with `--path`.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--json` (library: the `ImageSummary` returned): the image as JSON instead of text.

## Result

The version now in the file, then every version of the image. A kept file's method is `imported`, and a kept draft's is
the method of the call that made it.

```
.image-design/concepts/cactus.png holds v3.

- v1: 1024x1024, openai
- v2: 1024x1024, openai
- v3 (in the file): 812x904, imported
```
