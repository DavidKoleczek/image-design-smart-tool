# Library Reference

Every capability of Image Design is in `image_design.lib`. All other surfaces, including the CLI, are thin wrappers over the library.

## Design an image with an agent

`design_image` creates or edits an image by running an agent that directs an image model.
The agent has a shell in the working directory, this installation's `image-design` on its PATH, the tool's own skill, and skills for the craft of writing image calls.
It looks at the image, its history, and the references, writes each call to the image model it is given, and makes it with `generate-openai-image` or `generate-chatgpt-image`, choosing every other setting of the call itself.
It may make several images, write scripts for exact work such as a crop or a composite, and read the project to learn what the image is for.

```python
async def design_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    mask: Path | None = None,
    version: str | None = None,
    frame: int | None = None,
    resume_session: bool | str = False,
    image_model: str | None = None,
    size: tuple[int, int] | None = None,
    quality: OpenAIImageQuality | None = None,
    agent_provider: AgentProvider | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int | None = None,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
) -> DesignRun
```

```python
run = await design_image(
    prompt="Less detail: no flower buds or spines. Keep the shading.",
    name="concepts/cactus.png",
)
result = await run.result()
```

`prompt` is what the person wants, for the agent, not what an image model receives. A new `name` creates the image, and the name of one that exists edits it. It cannot be an `.svg`, which `draw_svg_image` draws.

- `references`, `marks`, `mask`: What goes with the request. The agent is shown the references and the image with the marks drawn on it, and is given each as a file it can pass on to a call.
- `version`, `frame`: The version, and for an animation the frame, the request is about.
- `resume_session`: Pass `True` to continue the image's agent's last session, or a session ID to continue that one. A new session is told the image's history: each call made on it, written as the command that would make it again, with what it made. A session that goes on is told only what happened since its last turn, such as a call the person made themselves.
- `image_model`: What the agent makes its images with: an OpenAI image model's ID, through `generate_openai_image`, or `chatgpt`, through `generate_chatgpt_image`. The agent's calls to any other are refused before anything is sent, and a call to `generate_openai_image` that names no model goes to this one. When it is None, the default OpenAI image model when that method is set up, else `chatgpt`. Its method must be set up, and `chatgpt` makes only a `.png`.
- `size`, `quality`: What the person wants the image's calls to pass. The agent is told them with the flags that pass them, and chooses its own when they are None. Only with an OpenAI image model, since ChatGPT chooses its own.
- `agent_provider`, `model`, `reasoning_effort`: The agent. See [Agent providers](#agent-providers).
- `timeout_seconds`: How long the agent may work. None, the default, sets no limit.

Each call is a run of its own that names the agent's run as its `parent`. A call on another image is linked from the agent's image, so `read_image_activity` on the agent's image has it.

The returned `DesignRun` is an `ImageRun` with a `session_id` and a `steer(message, origin, references, marks)` method. Its events are `started`, whose `data` has `method` `design`, an `agent` event for each thing the agent does, a `steered` event for each message sent to it, and the last event. Its result has no versions, since the calls make the images.

The agent's run is kept in the image's `designs.json`, beside its `runs.json`, and one agent at a time works on an image. Each of its calls claims the image only while it runs, as any call does.

```python
def steer_image(
    name: str,
    message: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    origin: str | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
) -> None
```

`steer_image` sends a message to the agent while it works, from any process. `cancel_image` stops the agent and the calls it has going.

## Generate an image with the OpenAI API

`generate_openai_image` creates or edits an image with an OpenAI image model through the Images API. It requires an OpenAI API key, from the `OPENAI_API_KEY` environment variable or [saved on the machine](#openai-api-key).

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
    frames: int | None = None,
    frame_ms: int | None = None,
    previews: int = 0,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
    parent: str | None = None,
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

- `references`: Other images to send with the prompt, for example to copy a style or a subject. A PNG, JPEG, or WebP is sent as it is. Any other image, such as an SVG, GIF, or TIFF, is sent as a PNG.
- `marks`: Shapes drawn over the image to show what the prompt refers to. They are sent as a separate layer, so the image itself is sent unmarked.
- `mask`: An image the same size as the image, transparent where the model may make changes. It is sent as a PNG, and works only for edits of still images. Cannot be used with `marks`.
- `version`: The version to edit. By default, the version in the image's file.
- `frame`: When the image being edited is an animation, the frame to send, counting from 0. By default, the first. `view_image` returns an image's frames.
- `model`: `gpt-image-2.6-sunburst`, the default, or the faster `gpt-image-2.6-flare`.
- `size`, `quality`, `complexity`, `background`, `compression`: Passed to the API. A parameter you leave out uses the API's default, except `size` on an edit, which defaults to the size of the image being edited, rounded to the nearest size the model accepts. `list_image_methods` returns the values each model accepts.
- `frames`, `frame_ms`: For a `.gif`, the number of frames and the duration of each in milliseconds. An edit of a `.gif` keeps the image's own.
- `previews`: The number of in-progress images the API sends before the final one, up to 3. Fewer can arrive if the image finishes first. Each adds 100 output tokens to the cost. A `.gif` has none.
- `origin`: A label for who sent the request, such as `app`.
- `detach`: Run the request in a separate process that keeps going if the caller exits.
- `parent`: The run of the [image's agent](#design-an-image-with-an-agent) that makes the call. When it is None, the run that the `IMAGE_DESIGN_PARENT` environment variable names, which the agent's processes have. A call with neither stands on its own.

A mark is a shape with an optional note:

```python
class Mark(BaseModel):
    shape: Literal["circle", "box", "arrow", "sketch"]
    points: list[tuple[float, float]]  # fractions of the image's width and height
    strokes: list[list[tuple[float, float]]] = []  # for a sketch, each stroke after the first
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
    folder: Path  # the image's folder in the data directory; the run's files are in runs/<run_id> there

    def events(self) -> AsyncIterator[ImageEvent]: ...
    async def cancel(self) -> None: ...
    async def result(self) -> ImageResult: ...
```

`events()` yields each step of the run as it happens. A `preview` event has the path of an in-progress image, so a viewer can show the image as it forms. Previews are kept with the run's data and do not become versions.

`result()` returns an `ImageResult` with the run's `status`, the `versions` it made, and its `usage`: the tokens the API reported and what they cost in dollars at the model's published prices.
Each `ImageVersion` records its file, its size, and the request that made it.

Only one run can work on an image at a time. A request for an image that already has a run raises `ImageDesignError`.
A request that fails or times out is not retried, because it may still have been billed.

A process that waits on a run it started can make sure the run does not outlive it:

```python
def stopped_by_signals(run: ImageRun) -> AbstractContextManager[None]
```

While the block runs, every signal that ends the process, such as Ctrl+C or its console closing, cancels the run. The CLI waits on its runs this way.

### OpenAI API key

```python
def openai_api_key_status() -> OpenAIKeyStatus
def save_openai_api_key(key: str) -> None
def clear_openai_api_key() -> None
```

```python
class OpenAIKeyStatus(BaseModel):
    source: Literal["environment", "saved"] | None
    saved: bool
```

A request is sent with the key in `OPENAI_API_KEY` when the environment has one, and otherwise with the saved key.
`save_openai_api_key` keeps a key in the platform's credential store: Windows Credential Manager, the macOS Keychain, or the Secret Service on Linux. It is written to no file of the tool. On a machine with no such store it raises `ImageDesignError`, and the environment variable is the way.
`openai_api_key_status` says which key is used and whether one is saved. Nothing returns the key itself.
`clear_openai_api_key` forgets the saved key.

## Generate an image with ChatGPT

`generate_chatgpt_image` creates or edits an image with the image generation built into Codex. A Codex agent passes the request to its image tool.
It uses the ChatGPT account that Codex is signed in with, so it counts against that plan and needs no API key.
If Codex is signed in with an API key instead, the function raises `ImageDesignError` rather than bill the API. It needs the `codex` extra.

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
    reasoning_effort: ReasoningEffort = DEFAULT_CHATGPT_REASONING_EFFORT,
    timeout_seconds: int = 600,
    origin: str | None = None,
    detach: bool = False,
    intelligence: Intelligence | None = None,
) -> ImageRun
```

It creates, edits, and returns a run the same way as `generate_openai_image`, but it has fewer options.
ChatGPT chooses the image model, the size, and the quality, so an edit can come back at a different size than the image it changes. Masks and animations are not supported, and the output is always a `.png`.
Each run makes one image. The agent is stopped as soon as the image arrives.

The parameters that differ:

- `prompt`: Passed to the image tool as written. The run's record keeps the prompt the image tool received.
- `references`: A request can include at most five images, counting the image being edited.
- `marks`: Drawn on a copy of the image. The copy is sent second, so with marks the references start at image 3. It counts toward the five images.
- `transparent`: Ask for a transparent background.
- `model`, `reasoning_effort`: The Codex model that runs the request, which defaults to `low` effort. This is not the image model.
- `intelligence`: An agent to use in place of Codex. Tests use it to pass a fake. It cannot be combined with `detach`.

The result's `usage` is None, since the run counts against the ChatGPT plan rather than being billed by the token.

## Preview a request

`preview_openai_image_request` and `preview_chatgpt_image_request` return what a request would send, without sending it.

```python
def preview_openai_image_request(prompt: str, name: str, ...) -> ImageRequestPreview
def preview_chatgpt_image_request(prompt: str, name: str, ...) -> ImageRequestPreview
```

Each takes the arguments of the function it previews, except `timeout_seconds`, `origin`, `detach`, and `intelligence`.
The arguments are checked the same way, so a preview raises `ImageDesignError` for whatever the request would.
Nothing is sent and nothing is kept for the image. A preview needs no API key, and does not check that Codex is signed in.

```python
class ImageRequestPreview(BaseModel):
    method: ImageMethod
    name: str
    edits: bool  # whether an image with that name exists
    prompt: str  # as the image model receives it
    added: str | None  # what the tool adds after the prompt as written
    images: list[ImageRequestImage]  # in the order they are sent
    parameters: dict[str, str | int | bool]


class ImageRequestImage(BaseModel):
    role: Literal["source", "marked-copy", "reference", "marks", "mask"]
    path: Path | None  # None for what the tool draws from the marks
```

- `added`: The tool adds to a prompt only when the request has marks, to say what they are. Otherwise the prompt is sent as written and `added` is None.
- `images`: `source` is the image being edited. The OpenAI API receives the marks as `marks`, a layer beside the image. ChatGPT receives them as `marked-copy`, a copy of the image with the marks drawn on it.
- `parameters`: For the OpenAI API, each parameter the request sets, under the name the Images API gives it. A parameter that is left out takes the API's default. On an edit, `size` is the size worked out from the image. For ChatGPT, `transparent_background`, and the `codex_model` and `reasoning_effort` that carry the request.

## Draw an SVG image

`draw_svg_image` creates or edits an SVG image by running an agent that draws it with code.
The agent writes a Python script, `image.py`, with its dependencies declared inline, and runs it with `uv run --script` to build the SVG. 
It then renders the SVG with [resvg](https://github.com/linebender/resvg), looks at the render, and fixes what does not match the request.

```python
async def draw_svg_image(
    prompt: str,
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    references: list[Path] | None = None,
    marks: list[Mark] | None = None,
    canvas: tuple[int, int] | NotGiven = NOT_GIVEN,
    max_bytes: int | NotGiven | None = NOT_GIVEN,
    resume_session: bool | str = False,
    agent_provider: AgentProvider | None = None,
    model: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
    timeout_seconds: int | None = 600,
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
- `canvas`, `max_bytes`: The drawing's budgets. They are not sent to a service. The agent is told what they are, and `check_svg_image` measures the drawing against them. A new drawing defaults to a 512 x 512 canvas with no other limits. On an edit, a budget you leave out keeps its earlier value.
- `resume_session`: Pass `True` to continue the image's last agent session, so the agent remembers the earlier requests. Pass a session ID to continue that session.
- `agent_provider`, `model`, `reasoning_effort`: The agent that draws. See [Agent providers](#agent-providers).
- `timeout_seconds`: How long the agent may work, or None for no limit.
- `intelligence`: An agent to use in place of the agent provider. Tests use it to pass a fake.

The returned `SvgRun` is an `ImageRun` that also has a `session_id` and a `steer(message, origin, references, marks)` method, which works as `steer_svg_image` does.
Its events also include an `agent` event for each thing the agent does, a `preview` with the path of each render it builds, and a `steered` event for each message sent to it.

The agent is told to put each part of the drawing in a named group, so a later request can change one part without redrawing the rest.
When the agent finishes, the tool runs `image.py` once more and keeps what it builds, so the kept SVG is always one that `image.py` builds. If the agent finishes without building `image.py` as it last changed it, the tool builds it and gives the agent the result once.
`image.py` and the `image.py.lock` that uv writes for it are kept with the image's data and committed with the project, so anyone who clones the project can continue to change the drawing. Each version keeps its own copy.
An agent that stops before it finishes keeps its work, and `resume_session=True` goes on from there.

resvg renders static SVG only. It skips what it does not support, such as animation and scripts, without reporting an error, so `check_svg_image` finds them in the SVG itself. Text renders with the fonts installed on the machine that renders it, so the check also counts the text elements.

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

`list_intelligence_models` returns the models to choose from and the reasoning efforts each one accepts. Both agents run at `high` effort by default:

```python
def list_intelligence_models(structured: bool = False) -> str | IntelligenceModels
```

A continued session must use the agent provider it started with.

Both agent providers implement the `Intelligence` protocol in `image_design.intelligence.interface`. To run a different agent, pass your own implementation as `intelligence`.

## Manage images

These functions work on any image, whichever function made it. None of them calls a model.

```python
def list_images(directory: Path | None = None, data_directory: Path | None = None) -> ImageListing
def view_image(
    name: str,
    version: str | None = None,
    frames_output: Path | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
) -> ImageView
def restore_image_version(name: str, version: str, directory: Path | None = None, data_directory: Path | None = None) -> ImageSummary
def move_image(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary
def copy_image(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary
def import_image(
    path: Path,
    name: str | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> ImageSummary
def add_image_version(
    name: str,
    path: Path,
    directory: Path | None = None,
    data_directory: Path | None = None,
    parent: str | None = None,
) -> ImageSummary
def delete_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None
def create_folder(name: str, directory: Path | None = None, data_directory: Path | None = None, numbered: bool = False) -> str
def move_folder(
    name: str,
    new_name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    numbered: bool = False,
) -> str
def delete_folder(name: str, directory: Path | None = None, data_directory: Path | None = None) -> list[str]
def relink_images(
    likely: list[str] | None = None,
    directory: Path | None = None,
    data_directory: Path | None = None,
) -> ImageRelinking
def cancel_image(name: str, directory: Path | None = None, data_directory: Path | None = None) -> None
def read_image_activity(
    name: str,
    directory: Path | None = None,
    data_directory: Path | None = None,
    after: str | None = None,
) -> ImageActivity
def list_image_methods() -> ImageMethods
```

- `list_images` returns every image in the directory with its versions and the status of its last run, and every folder in `folders`, including empty ones. An image's `id` names what the tool keeps for it and stays the same when the image moves. It is None for a file the tool keeps nothing for.
- `view_image` returns one image with its versions, and in `viewed` the image's file, or the `version` you pass, frame by frame with how long each frame is shown. A still image has one frame. Pass a folder as `frames_output` to also write each frame there as a PNG named `frame-<index>.png`. Nothing else is written.
- `restore_image_version` replaces the image's file with an earlier version. For an SVG image, it also restores that version's `image.py`.
- `move_image` renames an image or moves it to another folder. The image keeps its versions. The new name must keep the extension.
- `copy_image` makes another image with a copy of the image's file and of everything kept for it: its versions, its runs, and for an SVG image its script and sessions. It is refused while a run is working on the image.
- `import_image` copies an image file from anywhere on the machine into the directory as a new image, with the file as its first version. A PNG, JPEG, WebP, GIF, or SVG is kept as it is. Any other still image, such as a BMP or TIFF, is kept as a PNG. Without `name` the image has the file's name. A `name` that ends in a slash is the folder to put it in.
- `add_image_version` keeps a file, such as a crop or a composite a script made, as the image's next version and puts it in the image's file. The file must be in the image's format, except that any still image is kept as a PNG for a `.png`. `parent` is as for `generate_openai_image`.
- `delete_image` deletes an image and everything kept for it. If a run is working on the image, it's stopped first.
- `create_folder` makes a folder and returns its name. A folder stays until `delete_folder` removes it, even when a move or a delete leaves it empty.
- `move_folder` renames a folder or moves it into another, with everything in it, and returns its name. Its images keep their versions. It is refused while a run is working on an image in the folder.
- `delete_folder` deletes every image in a folder, then the folder. It never deletes a file that is not an image. It returns the paths of those files, and the folder stays to hold them.
- `relink_images` finds the images whose files were moved or renamed outside the tool, and keeps each under the name its file has. An image is relinked when a file the tool keeps nothing for has exactly the content of the image's current version. A file that only has the image's file name is returned in `likely`. Pass the image's name in `likely` to relink it as well.
- With `numbered`, a name that is taken becomes the first free one of `name (2)`, `name (3)`, and so on, as in `cactus (2).png`. Without it, a name that is taken is refused.
- `cancel_image` stops the run that is working on an image. It can be called from any process.
- `read_image_activity` returns the history of an image: each request, what the agent did, and how each run ended. Pass the `cursor` from an earlier call as `after` to get only what is new. Each run's `started` event has its request, which names the files the run was given relative to the event's `run_folder`.
- `list_image_methods` returns the three ways of making an image and, as `design`, the agent that directs the first two: whether each is set up on this machine, and the models and options each supports. Set up means installed, and for the OpenAI API that the key is set. The agent is set up when an agent provider is installed and one of the first two methods is set up.

```python
class ImageView(ImageSummary):
    viewed: ImageFrames | None  # None when the image has no file that can be read and no version was asked for


class ImageFrames(BaseModel):
    version: str | None  # None for the image's file
    path: Path
    width: int
    height: int
    frames: list[ImageFrame]


class ImageFrame(BaseModel):
    index: int  # from 0, as `frame` names it in generate_openai_image
    duration_ms: int  # 0 for a still image
    path: Path | None  # the PNG written for it, when `frames_output` was passed


class ImageRelinking(BaseModel):
    relinked: list[ImageMove]
    likely: list[ImageMove]  # not relinked
    gone: list[str]  # the images that still have no file, and no file that could be theirs


class ImageMove(BaseModel):
    name: str  # the name the tool had for the image
    new_name: str  # where its file is
```

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
      image.py.lock
      versions/
      runs/
      work/
      sessions/
```

`data_directory` has a `.gitignore` that ignores everything except each image's `image.json`, `image.py`, and `image.py.lock`.
If you set `data_directory`, pass the same one in every call. The tool does not record where it is.
An image file that you put in the directory yourself is listed like any other. The tool keeps nothing for it until the first request on it, which keeps the file as the image's first version.
Move and rename images and folders with these functions. A file manager moves the file but not the name the tool keeps for the image, which `relink_images` then repairs.

## App

Its view is an [MCP App](https://github.com/modelcontextprotocol/ext-apps): one HTML file that speaks only to its host. Hosts that render MCP Apps show it inline; for those that do not, `app_server` serves it in a browser page.

```python
def app_view() -> str
```

The view's HTML, compiled from `app/` and offered as the `ui://image-design/app` resource in the MCP server. Raises `ImageDesignError` naming the build command when the view is not compiled.

```python
def app_server(directory: Path | None = None, data_directory: Path | None = None) -> AppServer
```

```python
class AppServer:
    server: Server
    directory: Path
    data_directory: Path

    def open(self, port: int | None = None) -> App: ...
    def show(self, name: str) -> str: ...
    def close(self) -> None: ...
```

- `directory`, `data_directory`: The images the app shows, and where the tool keeps their data. The defaults are the same as for the functions that work on images.
- `port`: The port for the browser page, on `127.0.0.1`. If you do not give a port, the tool selects a free port. If another program uses the port, `open` raises `ImageDesignError`.

`server` is an MCP SDK low-level server to run over any transport; several at once share the state.
`open` serves the browser host page on `127.0.0.1` from daemon threads and returns once it listens, or returns the one already open. The page reaches the same server at its own `/mcp` and renders the view behind a sandbox proxy on a second port, a separate origin as the MCP Apps spec requires. `close` stops serving. `App.url` is where to open the page. `show` brings an image up in the app: an open app switches to it, and one opened later opens on it.

The server has one tool for an agent, `open_app`. It opens the browser page and returns its URL. It also takes `directory` and `data_directory`, and switches the app to them when the directory can be listed, and `name`, an image to bring up as `show` does.
The other tools are for the view. They are listed only to hosts that render MCP Apps, and marked for the app alone. The view and the resource templates are listed to the same hosts.

- `list_images`, `view_image`, `move_image`, `copy_image`, `delete_image`, `create_folder`, `move_folder`, `delete_folder`, `restore_image_version`, `read_image_activity`, `cancel_image`, and `list_image_methods` call the library function of the same name on the app's directory.
  - `list_images` first calls `relink_images`, so an image moved outside the app is listed where its file is. It also returns `shown`, the image the app showed last, and `likely`, the images `relink_images` left as likely.
- `relink_image` relinks one of those images to its likely file.
- `import_image` brings an upload into the app's directory as a new image, in a `folder` or at the top. `choose_image_files` asks the user for files in the platform's file dialog and imports each. It returns the images, and the reason for each file it refused.
- `show_image` records the image the user is looking at, which the app opens on next time.
- `generate_openai_image` and `generate_chatgpt_image` start a run on the app's directory with `detach=True` and `origin="app"`, so the image goes on being made when the app closes. They return the image's name and the run's ID once the run has started. They take the prompt, the name, the version to edit, the model and output options, and what guides the request: `references`, `marks`, and for the OpenAI API a `mask`. For the OpenAI API they also take `frame`, `frames`, and `frame_ms`. Each reference is a `path` the app offers or an `upload`, and the mask is an upload. A `path` can have a `frame`, which sends that one frame of an animation as a still image. A started run has copied what it was given, so the uploads it took are cleared, and the result's `references` says where each is offered from now.
- `preview_openai_image_request` and `preview_chatgpt_image_request` take the same arguments and return the `ImageRequestPreview`.
- `draw_svg_image` starts a drawing the same way. It takes the prompt, the name, `references`, `marks`, the budgets, `resume_session`, the agent provider, model, and reasoning effort, and `timeout_seconds`.
- `steer_svg_image` leaves a message for the agent drawing an image, with `references` and `marks`. The message holds copies of what it was given, so the uploads it took are cleared.
- `design_image` starts the image's agent the same way. It takes the prompt, the name, `references`, `marks`, a `mask`, the `version` and `frame` the request is about, `resume_session`, the image model and a new image's size and quality, the agent provider, model, and reasoning effort, and `timeout_seconds`. `steer_image` leaves a message for it, as `steer_svg_image` does.
- `list_images` gives each image its agent's last run as `design`, which is None when it has had none.
- `export_svg_image` asks the user where to save in the platform's save dialog, then renders the drawing, or one of its versions, there at a `scale` of its canvas.
- `upload_file` takes a file from the view in base64 pieces, under an ID the view makes up: a reference dropped or pasted into the app, an image file dropped on Your images, or the mask painted in it. Uploads wait in `image-design-uploads` in the system's temp folder. One that nothing takes is cleared when the app closes, or by the next app to start a day later.
- `read_reference_library` returns the references the app offers besides the images in its directory: the pinned files, and what requests sent from the app were given before. A version kept for an image is named after the image and the version.
- `list_reference_folder` returns a page of the images in a folder pinned to show its files and in the folders inside it, each with the folder it is in. Hidden files and folders, and links to folders, are left out. A page ends at 500 images or after 1,000 folders, so even a whole drive answers quickly. Pass its `after` to get the next page.
- `choose_reference_files` and `choose_reference_folder` ask the user in the platform's own file dialog, which needs Tk in the Python that runs the app.
- `keep_reference` copies an upload into `app/pins` in the data directory, so a dropped image can be pinned. The copy is cleared once the state is saved without it among the pins.
- `read_openai_key`, `enter_openai_key`, and `clear_openai_key` are over `openai_api_key_status`, `save_openai_api_key`, and `clear_openai_api_key`. None takes or returns the key. `enter_openai_key` has the user type it into a window on the machine the server runs on, so the key is in no message between the view, its host, and the server.
- `read_app_settings` and `save_app_settings` keep the theme, how Your images is listed, whether a request's advanced options show, and the pane sizes.
- `read_app_state` and `save_app_state` keep what was last picked for the images in the app's directory, such as the image model and its output options, whether a new image is a still image or an animation, the agent and budgets for a new drawing, the image's agent and its image model, the pinned references and folders, and the images open in tabs, each with whether it is a preview that the next image opened takes.

The view reads images as resources, each as base64. A read is refused unless the listing has that image or version, the version has that frame, or the image's activity has that preview.

- `image-design://images/{+name}` is an image's file.
- `image-design://versions/{version}/{+name}` is a version kept for an image, such as `v2`.
- `image-design://thumbnails/{version}/{+name}` is a WebP of a version that fits 256 by 256 pixels. Use `file` as the version for the image's file.
- `image-design://frames/{version}/{index}/{+name}` is one frame of a version as a PNG, by its index from 0. Use `file` as the version for the image's file.
- `image-design://frame-thumbnails/{version}/{index}/{+name}` is a WebP of one frame that fits 256 by 256 pixels.
- `image-design://previews/{run}/{index}/{+name}` is an in-progress image of a run. `run` is the run's ID, and `index` is the one its `preview` event has.
- `image-design://references/{+path}` is a WebP that fits 256 by 256 pixels of an image the app offers as a reference, by its path on the machine. It is refused unless the file is an image in the app's directory, pinned, anywhere inside a folder pinned to show its files, used before, chosen in the file dialog, or kept in the data directory as a version or as a copy of what a run was given. A request's references are held to the same rule.
- `image-design://reference-files/{+path}` is the same reference as a request sends it, so the view can show it large: a PNG, JPEG, or WebP as it is, and any other image as a PNG. It is held to the same rule.

The app keeps what it remembers in these files:

- `app-settings.json` is the same for every directory. It is in `image-design` in the user's config folder: `%APPDATA%` on Windows, `~/Library/Application Support` on macOS, and `$XDG_CONFIG_HOME` or `~/.config` on Linux.
- `app/app.json` is in the data directory, so each directory has its own. The data directory's `.gitignore` ignores the `app` folder.
- `app/used.json` lists the references that requests sent from the app were given, newest first.

## MCP server

The app's MCP server over stdio, a thin surface over the library like the CLI, in `image_design.adapters.mcp`.

```python
def run_stdio(directory: Path | None = None, data_directory: Path | None = None) -> None
```

It runs `app_server(directory, data_directory).server` over stdio until the client disconnects, then stops the browser page if `open_app` opened it.

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
