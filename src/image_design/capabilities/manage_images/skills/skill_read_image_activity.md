`read-image-activity` reads the history of an image, whichever method made it: each run's request, what its agent did,
and how it ended. Use it to follow a run started with `--detach`, passing the cursor it prints to read only what came
since.

```bash
image-design read-image-activity --name sailboat.svg
image-design read-image-activity --name sailboat.svg --after 20261113-142301-a1b2c3:5120
```

```python
from image_design.lib import read_image_activity

activity = read_image_activity(name="sailboat.svg")
later = read_image_activity(name="sailboat.svg", after=activity.cursor)
```

## Arguments

- `--name`: The image's path in the directory.
- `--directory`: Where images are kept. Defaults to `.image-design` in the working directory.
- `--data-directory`: Where the tool keeps versions and runs. Defaults to `.agents` in the directory.
- `--after`: The cursor an earlier call printed, to read only what came since.
- `--json` (library: the `ImageActivity` returned): every event, with its data, as JSON instead of text.

## Result

A line for each event that has text: the request starting, what the agent said and called, renders and versions kept,
and how the run ended. Then the last run's status and the cursor to pass next.

```
2026-11-13 14:23:01 started: Making sailboat.svg with gpt-6.1-sol.
2026-11-13 14:23:09 message: I'll draw the sea, then the boat.
2026-11-13 14:23:20 tool_call: commandExecution {"command": "... image_design.capabilities.svg_image.build ..."}
2026-11-13 14:24:02 version: Saved v1 of sailboat.svg: .image-design/sailboat.svg
2026-11-13 14:24:02 finished: Done: .image-design/sailboat.svg.
Status: done. To read only what comes next, pass --after 20261113-142301-a1b2c3:5120
```

With `--json`, the events are those `--json` prints as a run goes. A run's first event, `started`, has its request.
