`steer-svg-image` sends a message to the agent drawing an SVG image while it works, from any process, such as for a
run started with `--detach`. The process running the drawing delivers it within a second or so.
Once the run has ended, start a new one with `draw-svg-image --resume-session true` and the message as its prompt.

```bash
image-design steer-svg-image --name sailboat.svg --message "Make the sail red."
```

```python
from image_design.lib import steer_svg_image

steer_svg_image(name="sailboat.svg", message="Make the sail red.")
```

## Arguments

- `--name`: The image's path in the directory.
- `--message`: What the agent should change.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--origin`: Who asked, such as `app`.
- `--reference`: An image to show the agent with the message. Repeatable. Any format.
- `--marks`: A JSON file of marks, as for `draw-svg-image`, drawn on the agent's latest render.

## Result

Prints nothing and exits 0 once the message is left for the run. The run's events then have a `steered` event, which
says whether it was delivered.
