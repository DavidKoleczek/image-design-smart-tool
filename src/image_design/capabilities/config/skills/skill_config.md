`config` shows your defaults for the tool, or changes those given and leaves the rest as they are. They are the same
in every directory, kept in `config.json` in `image-design` in your config folder, and the app's Settings change them
too.

- `design_image_models`: the image models `design-image` picks from, in order, when it is given no `--image-model`.
  The first whose method is set up and that makes the image's format is picked, so a `.gif` passes over `chatgpt`,
  which makes only a `.png`. Those left out follow in the tool's own order: the default OpenAI image model first,
  `chatgpt` last. `list-image-methods` shows the whole order and the model it picks now.

```bash
image-design config
image-design config --design-image-models chatgpt,gpt-image-2.6-sunburst
image-design config --design-image-models ""
```

```python
from image_design.lib import read_config, update_config

config = read_config()
config = update_config(design_image_models=["chatgpt", "gpt-image-2.6-sunburst"])
```

## Arguments

- `--design-image-models` (library: `design_image_models`): the image models, comma separated, each an OpenAI image
  model's ID or `chatgpt`. An empty list goes back to the tool's own order. Omit it to leave the order as it is.
- `--json` (library: the `ImageDesignConfig` returned): the config as JSON instead of text.

## Result

Where the config is kept, then each default.

```
Kept in C:\Users\you\AppData\Roaming\image-design\config.json
- design_image_models: chatgpt, gpt-image-2.6-sunburst
```
