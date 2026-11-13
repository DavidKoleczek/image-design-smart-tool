# Library Reference

Every capability of Image Design is in `image_design.lib`. All other surfaces, including the CLI, are thin wrappers over the library.

## Generate an image with the OpenAI API

`generate_openai_image` creates or edits an image with an OpenAI image model through the Images API. It requires an `OPENAI_API_KEY`.

```python
async def generate_openai_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    mask: Path | None = None,
    version: str | None = None,
    frame: int | None = None,
    model: str | None = None,
    size: tuple[int, int] | None = None,
    quality: OpenAIImageQuality | None = None,
    complexity: OpenAIImageComplexity | None = None,
    background: OpenAIImageBackground | None = None,
    compression: int | None = None,
    count: int = 1,
    frames: int | None = None,
    frame_ms: int | None = None,
    previews: int = 0,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
) -> ImageRun
```

To create an image, pass a prompt and unique name:

```python
run = await generate_openai_image(
    prompt="A paper-cut cactus in a terracotta pot on a cream background.",
    name="concepts/cactus.png",
)
result = await run.result()
```

Images are saved in `directory`, which defaults to `.image-design` in the working directory.
Their earlier versions and the tool's other data are kept in `data_directory`, which defaults to `.agents` in `directory`.
`name` is the image's path in `directory`. Its extension sets the output format: `.png`, `.jpg`, `.webp`, or `.gif` for an animation.

To edit an image, pass the name of an image that exists:

```python
run = await generate_openai_image(
    prompt="Make the pot blue. Keep everything else unchanged.",
    name="concepts/cactus.png",
)
```

An edit overwrites the image's file. The previous version is kept in `data_directory`, and `restore_image_version` brings it back.

The other parameters:

- `references`: Other images to send with the prompt, for example to copy a style or a subject. An SVG file is sent as a PNG render.
- `marks`: Shapes drawn over the image to show what the prompt refers to. They are sent as a separate layer, so the image itself is sent unmarked.
- `mask`: A PNG the same size as the image, transparent where the model may make changes. It works only for edits of still images, and not together with `marks`. The model treats it as guidance, so other areas can still change.
- `version`: The version to edit. By default, the version in the image's file.
- `frame`: When the image being edited is an animation, the frame to send.
- `model`: `gpt-image-2.6-sunburst`, the default, or the faster `gpt-image-2.6-flare`.
- `size`, `quality`, `complexity`, `background`, `compression`: Passed to the API. A parameter you leave out uses the API's default, except `size` on an edit, which defaults to the size of the image being edited, rounded to the nearest size the model accepts. `list_image_methods` returns the values each model accepts.
- `count`: The number of images to make. Each is saved as its own version, and the first becomes the image's file.
- `frames`, `frame_ms`: For a `.gif`, the number of frames and the duration of each in milliseconds. An edit of a `.gif` keeps the image's own.
- `previews`: The number of in-progress images the API sends before the final one, up to 3. Fewer can arrive if the image finishes first. Each adds 100 output tokens to the cost. Previews work only with a `count` of 1, and a `.gif` has none.
- `origin`: A label for who sent the request, such as `app`.
- `detach`: Run the request in a separate process that keeps going if the caller exits.

A mark is a shape with an optional note:

```python
class Mark(BaseModel):
    shape: Literal["circle", "box", "arrow", "sketch"]
    points: list[tuple[float, float]]  # fractions of the image's width and height
    color: str = "red"
    note: str = ""
```

The function returns as soon as the request is sent. Use the returned `ImageRun` to follow it:

```python
class ImageRun(Protocol):
    name: str
    directory: Path
    data_directory: Path
    run_id: str

    def events(self) -> AsyncIterator[ImageEvent]: ...
    async def cancel(self) -> None: ...
    async def result(self) -> ImageResult: ...
```

`events()` yields each step of the run as it happens. A `preview` event has the path of an in-progress image, so a viewer can show the image as it forms. Previews are kept with the run's data and do not become versions.

`result()` returns an `ImageResult` with the run's `status`, the `versions` it made, and its `usage`: the tokens the API reported and what they cost in dollars at the model's published prices.
Each `ImageVersion` records its file, its size, and the request that made it.

Only one run can work on an image at a time. A request for an image that already has a run raises `ImageDesignError`.
A request that fails or times out is not retried, because it may still have been billed.

## Generate an image with ChatGPT

`generate_chatgpt_image` creates or edits an image with the image generation built into Codex.
It uses the ChatGPT account that Codex is signed in with, so it counts against that plan and needs no API key.
If Codex is signed in with an API key instead, the function raises `ImageDesignError` rather than bill the API.

```python
async def generate_chatgpt_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    version: str | None = None,
    transparent: bool = False,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
) -> ImageRun
```

It creates, edits, and returns a run the same way as `generate_openai_image`, but it has fewer options.
ChatGPT chooses the image model, the size, and the quality. Masks and animations are not supported, and the output is always a `.png`.

The parameters that differ:

- `references`: A request can include at most five images, counting the image being edited.
- `marks`: Drawn on a copy of the image. The copy is sent after the original and counts toward the five images.
- `transparent`: Ask for a transparent background.
- `model`, `reasoning_effort`: The Codex model that runs the request. This is not the image model.
- `intelligence`: An agent to use in place of Codex. Tests use it to pass a fake.

## Draw an SVG image

`draw_svg_image` creates or edits an SVG image by running an agent that draws it with code.
The agent writes a Python script, `image.py`, and runs it to build the SVG. It then renders the SVG with [resvg](https://github.com/linebender/resvg), looks at the render, and fixes what does not match the request.

```python
async def draw_svg_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    canvas: tuple[int, int] | NotGiven = NOT_GIVEN,
    max_shapes: int | NotGiven | None = NOT_GIVEN,
    max_colors: int | NotGiven | None = NOT_GIVEN,
    max_bytes: int | NotGiven | None = NOT_GIVEN,
    resume_session: bool | str = False,
    agent_provider: AgentProvider | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
) -> SvgRun
```

As with the other two functions, a new name creates an image and an existing name edits it:

```python
run = await draw_svg_image(
    prompt="A flat vector sailboat on calm water at sunset. No text.",
    name="sailboat.svg",
)
```

`name` must end in `.svg`. To redraw a PNG as an SVG, pass the PNG in `references` and use a new name.

The parameters that differ from `generate_openai_image`:

- `references`: Shown to the agent with the prompt.
- `marks`: Drawn on the render that the agent is shown. The agent is also told which parts of the drawing are under each mark.
- `canvas`, `max_shapes`, `max_colors`, `max_bytes`: The drawing's budgets. They are not sent to a service. The agent is told what they are, and `check_svg_image` measures the drawing against them. A new drawing defaults to a 512 x 512 canvas with no other limits. On an edit, a budget you leave out keeps its earlier value.
- `resume_session`: Pass `True` to continue the image's last agent session, so the agent remembers the earlier requests. Pass a session ID to continue that session.
- `agent_provider`, `model`, `reasoning_effort`: The agent that draws. See [Agent providers](#agent-providers).
- `intelligence`: An agent to use in place of the agent provider. Tests use it to pass a fake.

The returned `SvgRun` is an `ImageRun` that also has a `session_id` and a `steer(message)` method.

The agent is told to put each part of the drawing in a named group, so a later request can change one part without redrawing the rest.
`image.py` is kept with the image's data and committed with the project, so anyone who clones the project can continue to change the drawing.

resvg renders static SVG only. It skips what it does not support, such as animation, scripts, and text with no matching font, without reporting an error. `check_svg_image` lists what was skipped.

### Steer, check, and export

```python
def steer_svg_image(
    name: str,
    message: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    origin: str | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
) -> None
def check_svg_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> SvgCheck
def export_svg_image(
    name: str,
    output: Path,
    scale: float = 1,
    version: str | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
) -> Path
```

- `steer_svg_image` sends a message to the agent while it works. It can be called from any process.
- `check_svg_image` measures the drawing against its budgets. It also lists the drawing's named parts and anything resvg skipped. It only reports, and nothing passes or fails. The agent runs it before it finishes.
- `export_svg_image` renders the drawing to a `.png`, `.jpg`, or `.webp` file at `scale` times the canvas size.

None of the three calls a model.

### Agent providers

The agent runs on one of two agent providers. Each is installed through the extra of the same name:

- `codex`: Built on the [OpenAI Codex SDK](https://github.com/openai/codex/tree/main/sdk/python). It uses the user's Codex sign-in and `~/.codex/config.toml`.
- `claude`: Built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python). It uses the user's Claude Code settings and credentials: `ANTHROPIC_API_KEY`, or a cloud provider's.

`list_intelligence_models` returns the models to choose from and the reasoning efforts each one accepts:

```python
def list_intelligence_models(structured: bool = False) -> str | IntelligenceModels
```

A continued session must use the agent provider it started with.

Both agent providers implement the `Intelligence` protocol in `image_design.intelligence.interface`. To run a different agent, pass your own implementation as `intelligence`.

## Manage images

These functions work on any image, whichever function made it. None of them calls a model.

```python
def list_images(directory: Path | None = None, data_directory: Path | None = None) -> ImageListing
def view_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> ImageSummary
def restore_image_version(name: str, version: str, directory: Path | None = None, data_directory: Path | None = None) -> ImageSummary
def move_image(name: str, new_name: str, directory: Path | None = None, data_directory: Path | None = None) -> ImageSummary
def delete_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None
def cancel_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None
def read_image_activity(
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    after: str | None = None,
) -> ImageActivity
def list_image_methods() -> ImageMethods
```

- `list_images` returns every image in the directory with its versions and the status of its last run.
- `view_image` returns one image and records it as the last one viewed. The app opens on that image.
- `restore_image_version` replaces the image's file with an earlier version. For an SVG image, it also restores that version's `image.py`.
- `move_image` renames an image or moves it to another folder. The image keeps its versions.
- `delete_image` deletes an image and everything kept for it.
- `cancel_image` stops the run that is working on an image. It can be called from any process.
- `read_image_activity` returns the history of an image: each request, what the agent did, and how each run ended. Pass the `cursor` from an earlier call as `after` to get only what is new.
- `list_image_methods` returns the three ways of making an image, whether each is set up on this machine, and the models and options each supports.

An image's file is kept apart from the tool's data for it. With the default `data_directory`, the layout is:

```text
.image-design/
  logo.svg
  concepts/
    cactus.png
  .agents/
    images/<id>/
      image.json
      image.py
      versions/
      runs/
      sessions/
```

`data_directory` has a `.gitignore` that ignores everything except each image's `image.json` and `image.py`.
If you set `data_directory`, pass the same one in every call. The tool does not record where it is.
An image file that you put in the directory yourself is listed like any other.

## Manifest

The tool's `SMART_TOOL.md` as structured data: the frontmatter as fields, the Markdown below it as `Manifest.body`.

```python
def load_manifest() -> Manifest
```

## Skill

What an agent reads once it has decided to drive the tool: the manifest body, its `requires` as prerequisites, and the capability list, wrapped so the reader knows where the tool's files are.
Naming a capability returns that capability's own skill instead: the same wrapper, a heading carrying the capability's name, whether it is deterministic or model-backed, and the Markdown in its folder's `skills/`, which covers its arguments, a worked invocation, and its result.
The CLI's `--help` prints exactly this, the tool's at the root and the capability's on a command.

```python
def skill(capability: str | None = None) -> str
```

The capabilities the skill lists, one entry each, driven by the same table the CLI is built from:

```python
class Capability(NamedTuple):
    name: str
    summary: str
    model_backed: bool
    skill: str
    resources: tuple[str, ...] = ()
```

- `name` and `summary`: the command's name and its line in the tool's capability list.
- `model_backed`: whether it calls an AI model, agentic or not, which decides the kind shown in both skills.
- `skill`: the capability's skill body, a Markdown file relative to the installed package root, written without frontmatter, title, or kind line because the renderer supplies them.
- `resources`: the files that body refers to, relative to the installed package root, listed under `<skill_resources>` in the capability's skill. The block is omitted when there are none.

## Version

The installed package's version, from its metadata. The CLI's `--version` prints it.

```python
def version() -> str
```
