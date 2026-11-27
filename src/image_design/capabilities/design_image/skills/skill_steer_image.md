`steer-image` sends a message to the agent `design-image` started on an image while it works, from any process, such
as for a run started with `--detach`. The process running the agent delivers it within a second or so. It cannot
change a call already sent. Once the run has ended, start a new one with `design-image --resume-session true` and the
message as its prompt.

```bash
image-design steer-image --name concepts/cactus.png --message "Keep the open flower."
```

```python
from image_design.lib import steer_image

steer_image(name="concepts/cactus.png", message="Keep the open flower.")
```

## Arguments

- `--name`: The image's path in `.image-design`.
- `--message`: What the agent should do.
- `--workspace`: The top-level directory of the user's project, whose `.image-design` holds the images. Defaults
  to the working directory.
- `--origin`: Who asked, such as `app`.
- `--reference`: An image to show the agent with the message. Repeatable. Any format.
- `--marks`: A JSON file of marks, as for `design-image`, drawn on the image's file.

## Result

Prints nothing and exits 0 once the message is left for the run. The run's events then have a `steered` event, which
says whether it was delivered.
