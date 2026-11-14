"""Drawing SVG images with the agent faked and image.py run in this process, from the library and the CLI."""

from io import BytesIO
import json
from pathlib import Path
from typing import Any

from fake_drawing import Behavior, FakeAgentRun, FakeDrawingAgent, draws, fake_agent, hangs, sailboat, steered_to
from PIL import Image
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.svg_image import build, prompting
from image_design.cli import app
from image_design.intelligence.schemas import AgentResult
from image_design.schemas import ImageDesignError, ImageEvent, ImageResult, Mark, SvgBudgets
from image_design.shared.images.store import LOCKS, SCRIPT, lock_path

runner = CliRunner()
IMAGES = Path(".image-design/.agents/images")
SAIL = Mark(shape="circle", points=[(0.45, 0.05), (0.8, 0.55)], note="this sail")
SWATCH = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30" fill="#457b9d"/></svg>'
)
BROKEN = 'raise RuntimeError("The sail is missing.")\n'


def writes_only(script: str) -> Behavior:
    """An agent that writes image.py and finishes without building it."""

    async def behave(run: FakeAgentRun) -> None:
        run.writes(script)
        await run.finishes()

    return behave


def stops(error: str) -> Behavior:
    """An agent that writes and builds a drawing, then stops with an error before it finishes."""

    async def behave(run: FakeAgentRun) -> None:
        run.writes(sailboat("#2a9d8f"))
        await run.builds()
        run.end(AgentResult(error=error, session_id=run.session_id))

    return behave


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> FakeDrawingAgent:
    """The agent provider faked, also for the CLI, in a working directory of its own."""
    fake = fake_agent(monkeypatch)
    monkeypatch.chdir(tmp_path_factory.mktemp("work"))
    return fake


async def drawn(agent: FakeDrawingAgent, **arguments: Any) -> tuple[ImageResult, list[ImageEvent]]:
    arguments.setdefault("prompt", "A sailboat.")
    arguments.setdefault("name", "sailboat.svg")
    run = await lib.draw_svg_image(intelligence=agent, **arguments)
    events = [event async for event in run.events()]
    return await run.result(), events


def folder() -> Path:
    [only] = IMAGES.iterdir()
    return only.resolve()


def runs_kept() -> list[dict[str, Any]]:
    return json.loads((folder() / "runs.json").read_text(encoding="utf-8"))["runs"]


async def test_a_drawing_is_created_then_edited_with_marks_and_a_reference_each_version_kept_with_its_script(
    agent: FakeDrawingAgent,
) -> None:
    created, events = await drawn(agent)
    Path("palette.svg").write_text(SWATCH, encoding="utf-8")
    agent.behavior = draws("#457b9d", finding=sailboat())
    edited, _ = await drawn(agent, prompt="Make the sail blue.", references=[Path("palette.svg")], marks=[SAIL])

    work = folder() / "work"
    creating, editing = agent.runs
    assert creating.request.workspace is not None
    assert (creating.request.workspace.path, creating.request.writable) == (work, True)
    assert (creating.request.images, creating.request.resume) == ([], None)
    assert creating.request.session_directory == folder() / "sessions"
    assert build.command(work) in creating.request.prompt
    assert "<request>\nA sailboat.\n</request>" in creating.request.prompt
    assert "A canvas of 512 by 512" in creating.request.prompt
    kinds = [event.kind for event in events]
    assert kinds[0] == "started"
    assert kinds[-2:] == ["version", "finished"]
    assert {"agent", "preview"} <= set(kinds)
    assert "Making sailboat.svg with fake-model." in events[0].text
    assert events[0].data["prompt"] == "A sailboat."
    assert events[0].data["run_folder"] == str(folder() / "runs" / created.run_id)
    assert [run["request"]["marks"] for run in runs_kept()] == [[], [SAIL.model_dump(mode="json")]]
    assert (created.status, [(version.id, version.method) for version in created.versions]) == ("done", [("v1", "svg")])
    assert created.usage is not None
    assert (created.usage.output_tokens, created.usage.cost) == (20, 0.01)
    current, marked, palette = editing.request.images
    assert [path.name for path in (current, marked, palette)] == ["current.png", "marked.png", "reference-1.png"]
    assert Image.open(palette).size == (40, 30)
    prompt = editing.request.prompt
    assert "Read image.py first and change it rather than starting over." in prompt
    assert "- Mark 1 is a red circle: this sail. Under it: boat (" in prompt
    assert "), boat/sail (" in prompt
    assert f"References for this request (also attached):\n- {palette}" in prompt
    assert [version.id for version in edited.versions] == ["v2"]
    assert "#457b9d" in edited.path.read_text(encoding="utf-8")
    assert (folder() / SCRIPT).read_text(encoding="utf-8") == sailboat("#457b9d")
    assert lock_path(folder() / SCRIPT).is_file()
    [first, second] = (version for version in lib.restore_image_version("sailboat.svg", "v1").versions)
    assert first.script is not None
    assert second.script is not None
    assert (first.script.name, lock_path(first.script).is_file()) == ("v1.py", True)
    assert (folder() / SCRIPT).read_text(encoding="utf-8") == sailboat()
    assert "#e63946" in created.path.read_text(encoding="utf-8")
    record = json.loads((folder() / "image.json").read_text(encoding="utf-8"))
    assert record["budgets"] == {"canvas": [512, 512]}


async def test_budgets_are_told_the_agent_kept_on_an_edit_and_cleared_with_none(agent: FakeDrawingAgent) -> None:
    await drawn(agent, canvas=(64, 48), max_bytes=4000)
    agent.behavior = draws("#457b9d")
    await drawn(agent, prompt="Make the sail blue.")
    agent.behavior = draws("#e9c46a")
    await drawn(agent, prompt="Make the sail yellow.", max_bytes=None, timeout_seconds=None)

    creating, editing, cleared = agent.runs
    assert "A canvas of 64 by 48" in creating.request.prompt
    assert "At most 4,000 bytes of SVG" in creating.request.prompt
    assert "At most 4,000 bytes of SVG" in editing.request.prompt
    assert "bytes of SVG" not in cleared.request.prompt
    # No time limit for the run is none for its agent either.
    assert (editing.request.timeout_seconds, cleared.request.timeout_seconds) == (660, None)
    check = lib.check_svg_image("sailboat.svg")
    assert (check.budgets.canvas, check.budgets.max_bytes) == ((64, 48), None)
    assert (check.shapes, check.colors) == (3, ["#1d3557", "#8d5524", "#e9c46a"])
    assert [(part.id, part.shapes) for part in check.parts] == [("sea", 1), ("boat", 2), ("boat/sail", 1)]
    assert check.describe().splitlines()[1:3] == ["Shapes: 3.", "Colors: 3: #1d3557, #8d5524, #e9c46a."]


async def test_a_copied_drawing_is_edited_on_its_own_from_its_script_and_its_agent_s_session(
    agent: FakeDrawingAgent,
) -> None:
    await drawn(agent)
    copy = lib.copy_image("sailboat.svg", "boats/sailboat.svg")
    agent.behavior = draws("#457b9d", finding=sailboat())
    edited, _ = await drawn(agent, prompt="Make the sail blue.", name="boats/sailboat.svg", resume_session=True)

    creating, editing = agent.runs
    original, copied = lib.view_image("sailboat.svg"), lib.view_image("boats/sailboat.svg")
    assert (copy.current, edited.status) == ("v1", "done")
    assert editing.request.resume == creating.session_id
    # It is drawn in the copy's own folders, so the drawing it was copied from stays as it was.
    assert creating.request.workspace is not None
    assert editing.request.workspace is not None
    assert editing.request.workspace.path == IMAGES.resolve() / str(copied.id) / "work"
    assert editing.request.workspace.path != creating.request.workspace.path
    assert editing.request.session_directory == IMAGES.resolve() / str(copied.id) / "sessions"
    assert ([version.id for version in copied.versions], copied.current) == (["v1", "v2"], "v2")
    assert ([version.id for version in original.versions], original.current) == (["v1"], "v1")


async def test_a_resumed_session_goes_on_from_an_unfinished_run_s_work_and_keeps_its_agent_provider(
    agent: FakeDrawingAgent,
) -> None:
    agent.behavior = stops("The model is overloaded.")
    stopped, _ = await drawn(agent, agent_provider="claude")
    agent.behavior = draws("#e9c46a", finding=sailboat("#2a9d8f"))
    resumed, _ = await drawn(agent, prompt="Go on.", resume_session=True)
    agent.behavior = draws("#e63946", finding=sailboat("#e9c46a"))
    again, _ = await drawn(agent, prompt="Make the sail red.", resume_session=agent.runs[0].session_id)

    assert stopped.status == "failed"
    assert stopped.error is not None
    assert "The model is overloaded. Its work is kept; go on with resume_session=True." in stopped.error
    first, second, third = agent.runs
    assert second.request.resume == third.request.resume == first.session_id
    assert prompting.KEPT in second.request.prompt
    assert prompting.RESET in third.request.prompt
    assert (resumed.status, again.status) == ("done", "done")
    assert [run["agent_provider"] for run in runs_kept()] == ["claude", "claude", "claude"]
    with pytest.raises(ImageDesignError, match="goes on only on the one it started on"):
        await drawn(agent, resume_session=True, agent_provider="codex")
    with pytest.raises(
        ImageDesignError, match=f"has no session 'nope'. Its sessions, latest first: {first.session_id}"
    ):
        await drawn(agent, resume_session="nope")


async def test_steering_reaches_the_agent_with_references_and_marks_on_its_latest_render(
    agent: FakeDrawingAgent,
) -> None:
    agent.behavior = steered_to("#457b9d")
    Path("palette.svg").write_text(SWATCH, encoding="utf-8")

    run = await lib.draw_svg_image("A sailboat.", name="sailboat.svg", intelligence=agent)
    async for event in run.events():
        if event.kind == "preview":
            break
    lib.steer_svg_image("sailboat.svg", "Make the sail blue.", references=[Path("palette.svg")], marks=[SAIL])
    result = await run.result()
    events = [event async for event in run.events()]

    assert result.status == "done"
    [(message, images)] = agent.runs[0].steered
    assert [image.name for image in images] == ["marked.png", "reference-1.png"]
    assert message.startswith("Make the sail blue.\nReferences for this request (also attached):")
    assert "- Mark 1 is a red circle: this sail. Under it: boat (" in message
    [steered] = [event for event in events if event.kind == "steered"]
    assert (steered.text, steered.data["error"], steered.data["steering"]) == (
        "Steered: Make the sail blue.",
        None,
        "queued",
    )
    assert run.session_id == agent.runs[0].session_id
    with pytest.raises(ImageDesignError, match="has no drawing going"):
        lib.steer_svg_image("sailboat.svg", "Too late.")
    with pytest.raises(ImageDesignError, match="has ended"):
        await run.steer("Too late.")


async def test_an_agent_that_finishes_without_building_is_handed_the_build_once(agent: FakeDrawingAgent) -> None:
    agent.behavior = writes_only(sailboat())
    built, _ = await drawn(agent)
    agent.behavior = writes_only(BROKEN)
    broken, _ = await drawn(agent, prompt="Change it.")

    [checked] = agent.runs[0].follow_ups
    assert checked.startswith("The tool built image.py as you were finishing")
    assert "Named parts:\n- sea (1 shape)" in checked
    assert built.status == "done"
    [failed] = agent.runs[1].follow_ups
    assert "The build failed." in failed
    assert "RuntimeError: The sail is missing." in failed
    assert broken.status == "failed"
    assert broken.error is not None
    assert "did not build as the agent finished" in broken.error
    assert (folder() / SCRIPT).read_text(encoding="utf-8") == sailboat()


@pytest.mark.parametrize(
    ("behavior", "arguments", "status", "error"),
    [
        (stops("The model is overloaded."), {}, "failed", "The agent did not finish: The model is overloaded."),
        (hangs, {"timeout_seconds": 1}, "timed-out", "did not finish within 1 seconds"),
        (hangs, {"cancel": True}, "cancelled", None),
    ],
)
async def test_a_drawing_that_does_not_finish_ends_saying_why_stops_its_agent_and_leaves_the_image_free(
    agent: FakeDrawingAgent, behavior: Behavior, arguments: dict[str, Any], status: str, error: str | None
) -> None:
    agent.behavior = behavior
    cancel = arguments.pop("cancel", False)

    run = await lib.draw_svg_image("A sailboat.", name="sailboat.svg", intelligence=agent, **arguments)
    if cancel:
        await run.cancel()
    result = await run.result()

    assert result.status == status
    assert result.error == error or (error is not None and result.error is not None and error in result.error)
    assert agent.runs[0].cancels == 1
    assert not result.path.exists()
    agent.behavior = draws()
    assert (await drawn(agent))[0].status == "done"


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"name": "sailboat.png"}, "does not end in .svg"),
        ({"prompt": " "}, "The prompt is empty"),
        ({"canvas": (0, 10)}, "canvas is 0x10"),
        ({"max_bytes": 0}, "max_bytes is 0"),
        ({"timeout_seconds": 0}, "timeout_seconds must be more than 0"),
        ({"marks": [SAIL]}, "no image named sailboat.svg to edit"),
        ({"resume_session": True}, "no agent session to resume"),
        ({"references": [Path("notes.txt")]}, "is not an image the tool can read"),
        ({"detach": True}, "cannot be used by a detached run"),
    ],
)
async def test_a_request_the_drawing_cannot_take_is_refused_before_anything_starts_or_is_kept(
    agent: FakeDrawingAgent, arguments: dict[str, Any], refusal: str
) -> None:
    Path("notes.txt").write_text("Not an image.", encoding="utf-8")

    with pytest.raises(ImageDesignError, match=refusal):
        await drawn(agent, **arguments)

    assert agent.runs == []
    assert not list(IMAGES.glob("*"))
    assert not list(Path(".image-design/.agents", LOCKS).glob("*"))


async def test_check_lists_what_resvg_skips_and_export_renders_each_format(agent: FakeDrawingAgent) -> None:
    Path(".image-design").mkdir()
    Path(".image-design/logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><script>go()</script>'
        '<rect width="40" height="20" fill="#ff000080"><animate attributeName="x" to="5"/></rect>'
        '<text x="2" y="12" direction="rtl">Hi</text></svg>',
        encoding="utf-8",
    )
    await drawn(agent)

    check = lib.check_svg_image("logo.svg")
    written = [
        lib.export_svg_image("sailboat.svg", Path(f"exports/sailboat.{suffix}"), scale=2) for suffix in ("png", "jpg")
    ]
    earlier = lib.export_svg_image("sailboat.svg", Path("exports/v1.webp"), version="v1")

    assert check.budgets.canvas == (40, 20)
    assert (check.shapes, check.texts, check.colors) == (2, 1, ["#ff000080"])
    assert check.skipped == ["<animate> (1)", "<script> (1)", "the direction attribute (1)"]
    assert "Text elements: 1." in check.describe()
    assert [Image.open(path).size for path in (*written, earlier)] == [(128, 96), (128, 96), (64, 48)]
    assert Image.open(written[1]).mode == "RGB"
    with pytest.raises(ImageDesignError, match="does not end in a format to export to"):
        lib.export_svg_image("sailboat.svg", Path("exports/sailboat.gif"))
    with pytest.raises(ImageDesignError, match="is not an SVG"):
        lib.check_svg_image("cactus.png")


async def test_activity_reads_each_run_s_events_and_then_only_what_came_since(agent: FakeDrawingAgent) -> None:
    await drawn(agent)
    activity = lib.read_image_activity("sailboat.svg")
    nothing_new = lib.read_image_activity("sailboat.svg", after=activity.cursor)
    await drawn(agent, prompt="Make the sail blue.")
    since = lib.read_image_activity("sailboat.svg", after=activity.cursor)

    assert activity.status == "done"
    assert activity.events[0].kind == "started"
    assert activity.events[-1].kind == "finished"
    assert nothing_new.events == []
    assert nothing_new.cursor == activity.cursor
    assert [event.data["prompt"] for event in since.events if event.kind == "started"] == ["Make the sail blue."]
    with pytest.raises(ImageDesignError, match="is not a cursor"):
        lib.read_image_activity("sailboat.svg", after="elsewhere:12")


def test_the_cli_draws_checks_exports_and_reads_activity(agent: FakeDrawingAgent) -> None:
    made = runner.invoke(
        app, ["draw-svg-image", "A sailboat.", "--name", "sailboat.svg", "--canvas", "64x48", "--max-bytes", "none"]
    )
    checked = runner.invoke(app, ["check-svg-image", "--name", "sailboat.svg"])
    exported = runner.invoke(app, ["export-svg-image", "--name", "sailboat.svg", "--output", "out/boat.png"])
    activity = runner.invoke(app, ["read-image-activity", "--name", "sailboat.svg"])
    steered = runner.invoke(app, ["steer-svg-image", "--name", "sailboat.svg", "--message", "Too late."])
    bad = runner.invoke(app, ["draw-svg-image", "A boat.", "--name", "boat.svg", "--timeout-seconds", "lots"])

    assert made.exit_code == 0, made.output
    assert made.stdout.splitlines() == [str(Path(".image-design", "sailboat.svg"))]
    assert "Making sailboat.svg with fake-model." in made.stderr
    assert "I drew a sailboat." in made.stderr
    assert "A canvas of 64 by 48" in agent.runs[0].request.prompt
    assert checked.stdout.startswith("Canvas: 64x48.")
    assert exported.stdout.strip() == str(Path("out", "boat.png"))
    assert activity.stdout.splitlines()[-1].startswith("Status: done. To read only what comes next, pass --after ")
    assert isinstance(steered.exception, ImageDesignError)
    assert "has no drawing going" in str(steered.exception)
    assert bad.exit_code == 2


@pytest.mark.uv
def test_a_drawing_s_script_runs_with_uv_locked_and_rendered(tmp_path: Path) -> None:
    build.write_drawing(tmp_path, build.Drawing(name="sailboat.svg", budgets=SvgBudgets(canvas=(64, 48))))
    (tmp_path / SCRIPT).write_text(sailboat(), encoding="utf-8")

    check = build.build(tmp_path)

    assert lock_path(tmp_path / SCRIPT).is_file()
    assert (check.size, [part.id for part in check.parts]) == ((64.0, 48.0), ["sea", "boat", "boat/sail"])
    with Image.open(BytesIO((tmp_path / build.RENDER).read_bytes())) as render:
        assert render.size == (64, 48)
    assert build.built(tmp_path)
    (tmp_path / SCRIPT).write_text(BROKEN, encoding="utf-8")
    with pytest.raises(ImageDesignError, match=r"RuntimeError: The sail is missing."):
        build.build(tmp_path)
    assert not build.built(tmp_path)
