`list-image-methods` lists the three ways of making an image, whether each is set up on this machine, and what each
takes. A method is set up when what it needs is installed and, for the OpenAI API, its key is set. Whether Codex or
Claude is signed in is checked when a request is sent.

```bash
image-design list-image-methods
image-design list-image-methods --json
```

```python
from image_design.lib import list_image_methods

methods = list_image_methods()
```

## Arguments

- `--json` (library: the `ImageMethods` returned): the methods as JSON instead of text.

## Result

One block per method, named by its command: `ready`, or what to set up, then what it takes.

```
generate-openai-image: ready
- Names end in: .png, .jpg, .webp, .gif
- Models: gpt-image-2.6-sunburst (default), gpt-image-2.6-flare
- Sizes: each side a multiple of 16, at most 3840; 655,360 to 8,294,400 pixels; the long side at most 3 times the short side
- Qualities: low, medium, high, xhigh, max, auto
- Complexities: low, medium, high
- Backgrounds: transparent, opaque, auto
- At most 16 images sent, 10 made, and 3 previews
- A .gif: 2 to 16 frames of 20 to 2000 ms

generate-chatgpt-image: ready
- Names end in: .png
- Codex models: gpt-6.1-sol (default), gpt-6.1-terra, gpt-6-astra
- Reasoning effort: low by default
- At most 5 images sent

draw-svg-image: ready
- Names end in: .svg
- Agent: --agent-provider codex --model gpt-6.1-sol --reasoning-effort medium by default; `image-design list-intelligence-models` lists the others
- Canvas: 512x512 by default
- Exports to: .png, .jpg, .webp
```
