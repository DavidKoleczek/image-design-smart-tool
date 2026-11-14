import asyncio
from collections.abc import Callable, Coroutine
import contextlib
import io
import json as json_module
from pathlib import Path
import re
import sys
import time
from typing import Annotated, Any

from pydantic import TypeAdapter, ValidationError
import typer

# Typer 0.27 vendors Click, so a command that overrides Click's own hooks has to speak the vendored types.
from typer._click import Context, Parameter
from typer.core import TyperCommand, TyperOption
from typer.models import CommandFunctionType

from image_design import lib
from image_design.adapters import mcp as mcp_adapter
from image_design.core.skill import DISTRIBUTION
from image_design.schemas import (
    DEFAULT_CHATGPT_REASONING_EFFORT,
    DEFAULT_REASONING_EFFORT,
    NOT_GIVEN,
    AgentProvider,
    ImageDesignError,
    ImageEvent,
    ImageResult,
    ImageSummary,
    Mark,
    NotGiven,
    OpenAIImageBackground,
    OpenAIImageComplexity,
    OpenAIImageQuality,
    ReasoningEffort,
)

DIRECTORY_HELP = "Where images are kept; .image-design here when omitted."
DATA_DIRECTORY_HELP = "Where the tool keeps versions and runs; .agents in the directory when omitted."
JSON_HELP = "Print JSON instead of text."


class CapabilityCommand(TyperCommand):
    """Every capability answers `-h` with the generated summary and `--help` with its skill from the library."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["add_help_option"] = False
        super().__init__(*args, **kwargs)

    def get_params(self, ctx: Context) -> list[Parameter]:
        def short(ctx: Context, param: Parameter, value: bool) -> None:
            if value and not ctx.resilient_parsing:
                typer.echo(ctx.get_help())
                ctx.exit()

        def capability_skill(ctx: Context, param: Parameter, value: bool) -> None:
            if value and not ctx.resilient_parsing:
                typer.echo(lib.skill(self.name))
                ctx.exit()

        return [
            *super().get_params(ctx),
            TyperOption(
                param_decls=["-h"],
                is_flag=True,
                is_eager=True,
                expose_value=False,
                callback=short,
                help="Terse summary of this capability.",
            ),
            TyperOption(
                param_decls=["--help"],
                is_flag=True,
                is_eager=True,
                expose_value=False,
                callback=capability_skill,
                help="This capability's skill, for an agent about to call it.",
            ),
        ]


class SmartToolTyper(typer.Typer):
    """A Typer whose commands are CapabilityCommand by default, so a capability added later inherits the help split."""

    def command(
        self, *args: Any, cls: type[TyperCommand] = CapabilityCommand, **kwargs: Any
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        return super().command(*args, cls=cls, **kwargs)


app = SmartToolTyper(
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    # `-h` is the terse summary and `--help` is the skill, at both scopes. On the root, the callback's parameter
    # claims `--help` and Click drops a help option name a parameter already took, which leaves the generated
    # summary on `-h`; on a capability, CapabilityCommand splits the two itself.
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _print_skill(value: bool) -> None:
    """Answer the root `--help` with the skill the library composes, leaving `-h` to Typer."""
    if value:
        typer.echo(lib.skill())
        raise typer.Exit()


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"{DISTRIBUTION} {lib.version()}")
        raise typer.Exit()


@app.callback()
def cli(
    version: Annotated[
        bool,
        typer.Option("--version", "-V", is_eager=True, callback=_print_version, help="Print the version and exit."),
    ] = False,
    help: Annotated[
        bool,
        typer.Option(
            "--help", is_eager=True, callback=_print_skill, help="This tool's skill, for an agent driving it."
        ),
    ] = False,
) -> None:
    """Image creation and editing workspace"""


@app.command()
def generate_openai_image(
    prompt: Annotated[str, typer.Argument(help="What to make, or what to change.", show_default=False)],
    name: Annotated[
        str,
        typer.Option(
            "--name", help="The image's path in the directory, such as concepts/cactus.png; one that exists is edited."
        ),
    ],
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
    references: Annotated[
        list[Path] | None, typer.Option("--reference", help="Another image to send with the prompt; repeatable.")
    ] = None,
    marks: Annotated[
        Path | None,
        typer.Option("--marks", help="A JSON file with a list of marks to draw over the image being edited."),
    ] = None,
    mask: Annotated[
        Path | None,
        typer.Option("--mask", help="An image the image's size, transparent where the model may make changes."),
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", help="The version to edit; the one in the image's file when omitted.")
    ] = None,
    frame: Annotated[
        int | None,
        typer.Option("--frame", min=0, help="When editing an animation, the frame to send; the first when omitted."),
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="gpt-image-2.6-sunburst when omitted, or gpt-image-2.6-flare.")
    ] = None,
    size: Annotated[
        str | None,
        typer.Option(
            "--size", metavar="WIDTHxHEIGHT", help="The API's default when omitted, and the image's own for an edit."
        ),
    ] = None,
    quality: Annotated[OpenAIImageQuality | None, typer.Option("--quality")] = None,
    complexity: Annotated[OpenAIImageComplexity | None, typer.Option("--complexity")] = None,
    background: Annotated[OpenAIImageBackground | None, typer.Option("--background")] = None,
    compression: Annotated[
        int | None, typer.Option("--compression", min=0, max=100, help="For a .jpg or .webp.")
    ] = None,
    count: Annotated[int, typer.Option("--count", min=1, max=10, help="How many images to make.")] = 1,
    frames: Annotated[int | None, typer.Option("--frames", min=2, max=16, help="For a .gif.")] = None,
    frame_ms: Annotated[
        int | None, typer.Option("--frame-ms", min=20, max=2000, help="For a .gif, how long each frame shows.")
    ] = None,
    previews: Annotated[
        int, typer.Option("--previews", min=0, max=3, help="In-progress images to receive before the final one.")
    ] = 0,
    timeout_seconds: Annotated[int, typer.Option("--timeout-seconds", min=1)] = 600,
    origin: Annotated[str | None, typer.Option("--origin", help="Who asked, such as app.")] = None,
    detach: Annotated[
        bool, typer.Option("--detach", help="Leave the run going in a process of its own once it is sent.")
    ] = False,
    json: Annotated[bool, typer.Option("--json", help="Print each event as a line of JSON instead.")] = False,
) -> None:
    """Create or edit an image with an OpenAI image model. Model-backed, and billed to OPENAI_API_KEY.

    Prints the path of each image made, with progress on stderr. Exits 0 when the run is done.
    """
    code = asyncio.run(
        _follow(
            lib.generate_openai_image(
                prompt=prompt,
                name=name,
                directory=directory,
                data_directory=data_directory,
                references=references,
                marks=_marks(marks),
                mask=mask,
                version=version,
                frame=frame,
                model=model,
                size=_size(size),
                quality=quality,
                complexity=complexity,
                background=background,
                compression=compression,
                count=count,
                frames=frames,
                frame_ms=frame_ms,
                previews=previews,
                timeout_seconds=timeout_seconds,
                origin=origin,
                detach=detach,
            ),
            detach,
            json,
        )
    )
    raise typer.Exit(code)


@app.command()
def generate_chatgpt_image(
    prompt: Annotated[str, typer.Argument(help="What to make, or what to change.", show_default=False)],
    name: Annotated[
        str,
        typer.Option(
            "--name", help="The image's path in the directory, such as concepts/cactus.png; one that exists is edited."
        ),
    ],
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
    references: Annotated[
        list[Path] | None, typer.Option("--reference", help="Another image to send with the prompt; repeatable.")
    ] = None,
    marks: Annotated[
        Path | None,
        typer.Option("--marks", help="A JSON file with a list of marks to draw on a copy of the image being edited."),
    ] = None,
    version: Annotated[
        str | None, typer.Option("--version", help="The version to edit; the one in the image's file when omitted.")
    ] = None,
    transparent: Annotated[bool, typer.Option("--transparent", help="Ask for a transparent background.")] = False,
    model: Annotated[
        str | None, typer.Option("--model", help="The Codex model that passes the request on, not the image model.")
    ] = None,
    reasoning_effort: Annotated[
        ReasoningEffort, typer.Option("--reasoning-effort", help="That model's reasoning effort.")
    ] = DEFAULT_CHATGPT_REASONING_EFFORT,
    timeout_seconds: Annotated[int, typer.Option("--timeout-seconds", min=1)] = 600,
    origin: Annotated[str | None, typer.Option("--origin", help="Who asked, such as app.")] = None,
    detach: Annotated[
        bool, typer.Option("--detach", help="Leave the run going in a process of its own once it is sent.")
    ] = False,
    json: Annotated[bool, typer.Option("--json", help="Print each event as a line of JSON instead.")] = False,
) -> None:
    """Create or edit an image with the image generation built into Codex. Agentic, on Codex's ChatGPT plan.

    Prints the path of the image made, with progress on stderr. Exits 0 when the run is done.
    """
    code = asyncio.run(
        _follow(
            lib.generate_chatgpt_image(
                prompt=prompt,
                name=name,
                directory=directory,
                data_directory=data_directory,
                references=references,
                marks=_marks(marks),
                version=version,
                transparent=transparent,
                model=model,
                reasoning_effort=reasoning_effort,
                timeout_seconds=timeout_seconds,
                origin=origin,
                detach=detach,
            ),
            detach,
            json,
        )
    )
    raise typer.Exit(code)


@app.command()
def draw_svg_image(
    prompt: Annotated[str, typer.Argument(help="What to draw, or what to change.", show_default=False)],
    name: Annotated[
        str,
        typer.Option("--name", help="The image's path in the directory, such as logo.svg; one that exists is edited."),
    ],
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
    references: Annotated[
        list[Path] | None, typer.Option("--reference", help="An image to show the agent with the prompt; repeatable.")
    ] = None,
    marks: Annotated[
        Path | None,
        typer.Option("--marks", help="A JSON file with a list of marks to draw on the render the agent is shown."),
    ] = None,
    canvas: Annotated[
        str | None,
        typer.Option("--canvas", metavar="WIDTHxHEIGHT", help="512x512 for a new drawing; an edit keeps its own."),
    ] = None,
    max_shapes: Annotated[
        str | None, typer.Option("--max-shapes", metavar="N|none", help="The most elements that draw.")
    ] = None,
    max_colors: Annotated[
        str | None, typer.Option("--max-colors", metavar="N|none", help="The most distinct colors.")
    ] = None,
    max_bytes: Annotated[
        str | None, typer.Option("--max-bytes", metavar="N|none", help="The largest the SVG file may be.")
    ] = None,
    resume_session: Annotated[
        str,
        typer.Option(
            "--resume-session", metavar="true|false|ID", help="Go on in the image's last agent session, or this one."
        ),
    ] = "false",
    agent_provider: Annotated[AgentProvider | None, typer.Option("--agent-provider")] = None,
    model: Annotated[str | None, typer.Option("--model", help="See image-design list-intelligence-models.")] = None,
    reasoning_effort: Annotated[
        ReasoningEffort, typer.Option("--reasoning-effort", help="The model's reasoning effort.")
    ] = DEFAULT_REASONING_EFFORT,
    timeout_seconds: Annotated[int, typer.Option("--timeout-seconds", min=1)] = 600,
    origin: Annotated[str | None, typer.Option("--origin", help="Who asked, such as app.")] = None,
    detach: Annotated[
        bool, typer.Option("--detach", help="Leave the agent going in a process of its own once it starts.")
    ] = False,
    json: Annotated[bool, typer.Option("--json", help="Print each event as a line of JSON instead.")] = False,
) -> None:
    """Create or edit an SVG image with an agent that draws it with code. Agentic.

    Prints the path of the image drawn, with the agent's progress on stderr. Exits 0 when the run is done.
    """
    code = asyncio.run(
        _follow(
            lib.draw_svg_image(
                prompt=prompt,
                name=name,
                directory=directory,
                data_directory=data_directory,
                references=references,
                marks=_marks(marks),
                canvas=_canvas(canvas),
                max_shapes=_budget(max_shapes, "--max-shapes"),
                max_colors=_budget(max_colors, "--max-colors"),
                max_bytes=_budget(max_bytes, "--max-bytes"),
                resume_session=_resume_session(resume_session),
                agent_provider=agent_provider,
                model=model,
                reasoning_effort=reasoning_effort,
                timeout_seconds=timeout_seconds,
                origin=origin,
                detach=detach,
            ),
            detach,
            json,
        )
    )
    raise typer.Exit(code)


@app.command()
def steer_svg_image(
    name: Annotated[str, typer.Option("--name", help="The image's path in the directory.")],
    message: Annotated[str, typer.Option("--message", help="What the agent should change.")],
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
    origin: Annotated[str | None, typer.Option("--origin", help="Who asked, such as app.")] = None,
    references: Annotated[
        list[Path] | None, typer.Option("--reference", help="An image to show the agent with it; repeatable.")
    ] = None,
    marks: Annotated[
        Path | None,
        typer.Option("--marks", help="A JSON file with a list of marks to draw on the agent's latest render."),
    ] = None,
) -> None:
    """Send a message to the agent drawing an SVG image while it works. Deterministic."""
    lib.steer_svg_image(
        name=name,
        message=message,
        directory=directory,
        data_directory=data_directory,
        origin=origin,
        references=references,
        marks=_marks(marks),
    )


@app.command()
def check_svg_image(
    name: Annotated[str, typer.Option("--name", help="The image's path in the directory.")],
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
    json: Annotated[bool, typer.Option("--json", help=JSON_HELP)] = False,
) -> None:
    """Measure an SVG image against its budgets. Deterministic."""
    check = lib.check_svg_image(name=name, directory=directory, data_directory=data_directory)
    typer.echo(check.model_dump_json(indent=2) if json else check.describe())


@app.command()
def export_svg_image(
    name: Annotated[str, typer.Option("--name", help="The image's path in the directory.")],
    output: Annotated[Path, typer.Option("--output", help="The file to write: a .png, .jpg, or .webp.")],
    scale: Annotated[float, typer.Option("--scale", help="Times the canvas size.")] = 1,
    version: Annotated[
        str | None, typer.Option("--version", help="The version to render; the one in the image's file when omitted.")
    ] = None,
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
) -> None:
    """Render an SVG image to a raster file. Deterministic."""
    written = lib.export_svg_image(
        name=name, output=output, scale=scale, version=version, directory=directory, data_directory=data_directory
    )
    typer.echo(_shown(written))


@app.command()
def restore_image_version(
    name: Annotated[str, typer.Option("--name", help="The image's path in the directory.")],
    version: Annotated[str, typer.Option("--version", help="The version to put back, such as v1.")],
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
    json: Annotated[bool, typer.Option("--json", help=JSON_HELP)] = False,
) -> None:
    """Put an earlier version of an image back in its file. Deterministic."""
    summary = lib.restore_image_version(name=name, version=version, directory=directory, data_directory=data_directory)
    typer.echo(summary.model_dump_json(indent=2) if json else _describe(summary))


@app.command()
def cancel_image(
    name: Annotated[str, typer.Option("--name", help="The image's path in the directory.")],
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
) -> None:
    """Stop the run working on an image. Deterministic."""
    lib.cancel_image(name=name, directory=directory, data_directory=data_directory)


@app.command()
def read_image_activity(
    name: Annotated[str, typer.Option("--name", help="The image's path in the directory.")],
    directory: Annotated[Path | None, typer.Option("--directory", help=DIRECTORY_HELP)] = None,
    data_directory: Annotated[Path | None, typer.Option("--data-directory", help=DATA_DIRECTORY_HELP)] = None,
    after: Annotated[
        str | None, typer.Option("--after", help="The cursor an earlier call printed, to read only what came since.")
    ] = None,
    json: Annotated[bool, typer.Option("--json", help=JSON_HELP)] = False,
) -> None:
    """The history of an image: each request, what its agent did, and how each run ended. Deterministic."""
    activity = lib.read_image_activity(name=name, directory=directory, data_directory=data_directory, after=after)
    if json:
        typer.echo(activity.model_dump_json(indent=2))
        return
    for event in activity.events:
        if event.text:
            kind = event.data.get("kind", event.kind) if event.kind == "agent" else event.kind
            typer.echo(f"{event.time:%Y-%m-%d %H:%M:%S} {kind}: {event.text}")
    if activity.cursor is None:
        typer.echo(f"{activity.name} has had no run.")
    else:
        typer.echo(f"Status: {activity.status}. To read only what comes next, pass --after {activity.cursor}")


@app.command("app")
def app_(
    port: Annotated[int | None, typer.Option(help="The port to bind; a free one is chosen when omitted.")] = None,
) -> None:
    """Serve the app in a browser page on this machine and print its URL.

    Keeps serving until Ctrl+C. Exits 1 with the cause and remedy when the port is held.
    """
    app_server = lib.app_server()
    typer.echo(app_server.open(port).url)
    with contextlib.suppress(KeyboardInterrupt):
        while True:
            time.sleep(1)
    app_server.close()


@app.command()
def mcp() -> None:
    """Serve the app's MCP server on stdio, with the app as an MCP App.

    For MCP clients that launch the server themselves. Reads and writes MCP messages on stdin and stdout until the
    client disconnects; prints nothing else to stdout.
    """
    mcp_adapter.run_stdio()


@app.command()
def manifest() -> None:
    """Print the tool's manifest as JSON."""
    typer.echo(lib.load_manifest().model_dump_json(indent=2))


@app.command()
def list_intelligence_models(
    json: Annotated[
        bool, typer.Option("--json", help="Print the listing as JSON instead of one model per line.")
    ] = False,
) -> None:
    """List the AI models and reasoning efforts to pick from for agentic capabilities."""
    if json:
        typer.echo(lib.list_intelligence_models(structured=True).model_dump_json(indent=2))
    else:
        typer.echo(lib.list_intelligence_models())


async def _follow(starting: Coroutine[Any, Any, lib.ImageRun], detach: bool, as_json: bool) -> int:
    """Follow a run to its end, and the exit code its end calls for."""
    run = await starting
    if detach:
        # The run goes on in its own process, so its start is all there is to print.
        _print_event(await anext(run.events()), as_json)
        return 0
    with lib.stopped_by_signals(run):
        async for event in run.events():
            _print_event(event, as_json)
        result = await run.result()
    if not as_json:
        for path in _made(result):
            typer.echo(_shown(path))
    return 0 if result.status == "done" else 1


def _print_event(event: ImageEvent, as_json: bool) -> None:
    if as_json:
        # ASCII-escaped JSON is UTF-8 on any console encoding, and echo writes the line in one call and flushes it.
        typer.echo(json_module.dumps(event.model_dump(mode="json")))
    elif event.text:
        typer.echo(event.text, err=True)


def _made(result: ImageResult) -> list[Path]:
    """The image's file for the first image a run made, and the version's own file for each after it."""
    if not result.versions:
        return []
    return [result.path, *(version.file for version in result.versions[1:])]


def _shown(path: Path) -> str:
    """A path relative to the working directory when it is inside it, as a person would type it."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _describe(summary: ImageSummary) -> str:
    holds = f"holds {summary.current}" if summary.current else "was changed by hand"
    lines = [f"{_shown(summary.path)} {holds}.", ""]
    for version in summary.versions:
        current = " (in the file)" if version.id == summary.current else ""
        frames = f", {version.frames} frames" if version.frames > 1 else ""
        lines.append(f"- {version.id}{current}: {version.width}x{version.height}{frames}, {version.method}")
    return "\n".join(lines)


def _marks(path: Path | None) -> list[Mark] | None:
    """The marks in a JSON file, which holds a list of them."""
    if path is None:
        return None
    try:
        return TypeAdapter(list[Mark]).validate_json(path.read_bytes())
    except OSError as error:
        raise typer.BadParameter(f"{path} cannot be read: {error.strerror}.", param_hint="--marks") from None
    except ValidationError as error:
        problem = error.errors()[0]
        where = ".".join(str(part) for part in problem["loc"])
        raise typer.BadParameter(
            f"{path} is not a JSON list of marks: at {where or 'the top'}, {problem['msg']}.", param_hint="--marks"
        ) from None


def _size(typed: str | None, hint: str = "--size") -> tuple[int, int] | None:
    """A size as typed: WIDTHxHEIGHT."""
    if typed is None:
        return None
    match = re.fullmatch(r"(\d+)x(\d+)", typed.strip().lower())
    if match is None:
        raise typer.BadParameter(f"{typed!r} is not WIDTHxHEIGHT, such as 1024x1024.", param_hint=hint)
    return int(match[1]), int(match[2])


def _canvas(typed: str | None) -> tuple[int, int] | NotGiven:
    """A canvas as typed, or NOT_GIVEN when left out, so an edit keeps its own."""
    size = _size(typed, "--canvas")
    return NOT_GIVEN if size is None else size


def _budget(typed: str | None, hint: str) -> int | NotGiven | None:
    """A budget as typed: a number, or `none` for no limit; NOT_GIVEN when left out, so an edit keeps its own."""
    if typed is None:
        return NOT_GIVEN
    if typed.strip().lower() == "none":
        return None
    if not typed.strip().isdigit():
        raise typer.BadParameter(f"{typed!r} is not a number or none.", param_hint=hint)
    return int(typed)


def _resume_session(typed: str) -> bool | str:
    """`true`, `false`, or a session ID, as typed."""
    lowered = typed.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    return typed.strip()


def main() -> int:
    # A pipe on Windows defaults to the ANSI code page, which cannot encode much of what an agent writes.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    try:
        app()
    except ImageDesignError as error:
        typer.echo(error, err=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
