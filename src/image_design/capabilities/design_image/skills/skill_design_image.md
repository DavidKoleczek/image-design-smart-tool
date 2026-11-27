`design-image` creates or edits an image with an agent that directs an image model. It looks at the image and its
history, writes each image call to the image model it is given and makes it with `generate-openai-image` or
`generate-chatgpt-image`, choosing every other setting of the call itself, then says what it made. It works in a shell
in the workspace with this tool's own commands and skills for the craft, and may make several images, write scripts
for exact work such as a crop, and read the project. It needs the `codex` or `claude` extra, and the method of
its image model set up: see `list-image-methods`.

Reach for it when what matters is the result rather than the exact request: it holds the intent across edits and
gives each reference a purpose. Use the generate commands when you have the exact prompt, images, and settings to
send.

A new `--name` creates the image, and the name of one that exists edits it. Each call the agent makes is a run of its
own, on whichever image it is for, that names the agent's run as its `parent`; `read-image-activity` has them with the
agent's run.

```bash
image-design design-image "Less detail: no flower buds or spines. Keep the shading." --name concepts/cactus.png
image-design design-image "Now a cel-shaded version." --name concepts/cactus.png --resume-session true --image-model chatgpt
```

```python
from image_design.lib import design_image

run = await design_image(prompt="Less detail: no flower buds or spines.", name="concepts/cactus.png")
result = await run.result()
```

`marks.json` holds a list of marks, as for `generate-openai-image`. The agent is shown the image with them drawn on,
and gets them as a file it can pass on with `--marks`.

## Arguments

- `PROMPT`: What you want, for the agent; not what an image model receives.
- `--name`: The image's path in `.image-design`, not an `.svg`.
- `--workspace`: The top-level directory of the user's project, where the agent runs and whose `.image-design`
  holds the images. Defaults to the working directory.
- `--reference`: An image that goes with the request. Repeatable. Any format.
- `--marks`: A JSON file of marks drawn on the image, which show what the request refers to.
- `--mask`: An image the image's size, transparent where changes may go.
- `--version`: The version the request is about. Defaults to the one in the image's file.
- `--frame`: For an animation, the frame the request is about, from 0.
- `--resume-session`: `true` to go on in the image's agent's last session, so it remembers the conversation, or a
  session ID. `false` by default. A new session is told the image's history, and one that goes on is told what
  happened since its last turn, such as a call you made yourself.
- `--image-model`: What the agent makes its images with: an OpenAI image model, through `generate-openai-image`, or
  `chatgpt`, through `generate-chatgpt-image`. Its calls to any other are refused. Defaults to the first of
  `image-design config`'s `design_image_models` that is set up and makes the image, then the rest in the tool's own
  order, which starts with the default OpenAI image model and ends with `chatgpt`.
- `--size`, `--quality`: The size, as `WIDTHxHEIGHT`, and the quality the agent is told to pass to its calls. Its own
  choice when omitted. Only with an OpenAI image model, since ChatGPT chooses its own.
- `--agent-provider`: `codex` or `claude`. Defaults to the resumed session's, else the first installed.
- `--model`, `--reasoning-effort`: The agent's model and its effort. See `image-design list-intelligence-models`.
- `--timeout-seconds`: How long the agent may work, or `none`. `none` by default.
- `--origin`: Who asked, such as `app`.
- `--detach`: Leave the agent going in a process of its own once it starts. Follow it with `read-image-activity`,
  message it with `steer-image`, and stop it with `cancel-image`, which also stops the calls it has going.
- `--json`: Print each event of the run as a line of JSON instead of text.

## Result

What the agent said last, then the image's path. What it says and the tools it calls go to stderr. The command exits 0
when the run is done and 1 when it failed, timed out, or was cancelled. Ctrl+C cancels it.

```
v2 has no buds or spines, and the shading and background match v1. The open flower is still there.
.image-design/concepts/cactus.png
```

With `--json`, each event is a line of JSON: `started`, whose `data` has the request and `method` `design`, an
`agent` event for each thing the agent does, a `steered` for each message sent to it, and last `finished` or
`failed`, whose `data` is the result. The result has the run's `status` and its `usage`: the agent's tokens, and their
cost in US dollars when the agent provider reports it. The images are made by the calls, so the result has no
`versions`.
