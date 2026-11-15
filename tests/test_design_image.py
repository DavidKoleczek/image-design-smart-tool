"""The image's agent with its agent provider faked: it makes its calls through the library against the faked Images
API, as the real one makes them through the CLI."""

import asyncio
from collections.abc import Callable
import json
from pathlib import Path
import re
from typing import Any

from fake_design import FakeDesignAgent, edits, fake_designer, hangs, makes, says, waits_for_a_message
from fake_openai import FakeImagesAPI
from mcp import Client
from PIL import Image
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.design_image import tooling
from image_design.cli import app
from image_design.schemas import ImageDesignError, ImageEvent, Mark
from image_design.shared.images.calls import PARENT

runner = CliRunner()
BUD = Mark(shape="circle", points=[(0.4, 0.1), (0.6, 0.3)], note="this bud")


@pytest.fixture
def agent(
    images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> FakeDesignAgent:
    """The agent provider faked, in the Images API's working directory, with the tool's state in a folder of its own."""
    return fake_designer(monkeypatch, tmp_path_factory.mktemp("state"))


async def made(name: str = "cactus.png", prompt: str = "A small cactus.", **arguments: Any) -> None:
    """An image made by a call of the person's, as from the app."""
    run = await lib.generate_openai_image(prompt=prompt, name=name, origin="app", **arguments)
    assert (await run.result()).status == "done"


async def designed(agent: FakeDesignAgent, **arguments: Any) -> lib.DesignRun:
    arguments.setdefault("prompt", "Less detail: no flower buds.")
    arguments.setdefault("name", "cactus.png")
    run = await lib.design_image(**arguments)
    result = await run.result()
    assert result.status == "done", result.error
    return run


def started(events: list[ImageEvent]) -> dict[str, dict[str, Any]]:
    return {event.run_id: event.data for event in events if event.kind == "started"}


async def test_the_agent_s_call_edits_the_image_and_names_the_agent_s_run(
    agent: FakeDesignAgent, images_api: FakeImagesAPI
) -> None:
    await made()
    agent.behavior = edits()

    run = await designed(agent)

    image = lib.view_image("cactus.png")
    assert [version.id for version in image.versions] == ["v1", "v2"]
    assert image.current == "v2"
    assert image.design is not None
    assert image.design.run_id == run.run_id
    assert image.design.status == "done"
    assert image.design.session_id == agent.runs[0].session_id
    assert images_api.requests[-1].path.endswith("/edits")
    activity = started(lib.read_image_activity("cactus.png").events)
    call = image.last_run
    assert call is not None
    assert call.parent == run.run_id
    assert activity[run.run_id]["method"] == "design"
    assert activity[run.run_id]["prompt"] == "Less detail: no flower buds."
    assert activity[call.id]["parent"] == run.run_id
    assert activity[call.id]["version"] == "v1"


async def test_the_agent_is_given_the_tool_its_skills_and_its_run(agent: FakeDesignAgent) -> None:
    await made()

    run = await designed(agent)

    request = agent.runs[0].request
    assert request.environment == {PARENT: run.run_id}
    assert request.workspace is not None
    assert request.workspace.path == Path.cwd()
    assert request.writable
    command = request.path_directories[0] / "image-design"
    assert "-m image_design.cli" in command.read_text(encoding="utf-8")
    skills = {path.parent.name for directory in request.skill_directories for path in directory.glob("*/SKILL.md")}
    assert skills == {*tooling.CRAFT_SKILLS, "image-design"}
    assert set(tooling.CRAFT_SKILLS) == {"prompting-openai-images", "prompting-chatgpt-images", "editing-images"}
    assert request.reasoning_effort == "high"
    assert "image-design --help" in request.prompt
    assert "Less detail: no flower buds." in request.prompt
    assert "holds v1" in request.prompt


async def test_the_agent_makes_its_images_with_the_image_model_it_was_given(
    agent: FakeDesignAgent, images_api: FakeImagesAPI
) -> None:
    await made()
    agent.behavior = edits()

    run = await designed(agent, image_model="gpt-image-2.6-flare")

    prompt = agent.runs[0].request.prompt
    assert "You should use `image-design generate-openai-image --model gpt-image-2.6-flare`" in prompt
    assert '<skill_content name="image-design generate-chatgpt-image">' not in prompt
    assert started(lib.read_image_activity("cactus.png").events)[run.run_id]["image_model"] == "gpt-image-2.6-flare"
    # The agent's call names no model, so it goes to the one the agent was given.
    assert images_api.requests[-1].fields["model"] == "gpt-image-2.6-flare"


async def test_the_image_model_is_the_default_openai_one_when_none_is_picked(agent: FakeDesignAgent) -> None:
    await made()

    await designed(agent)

    assert "generate-openai-image --model gpt-image-2.6-sunburst" in agent.runs[0].request.prompt


@pytest.mark.parametrize(
    ("given", "called"),
    [("gpt-image-2.6-flare", {"model": "gpt-image-2.6-sunburst"}), ("chatgpt", {})],
)
async def test_a_call_to_another_image_model_than_the_agent_was_given_is_refused(
    agent: FakeDesignAgent, images_api: FakeImagesAPI, given: str, called: dict[str, str]
) -> None:
    await made()
    sent = len(images_api.requests)
    agent.behavior = edits(**called)

    run = await lib.design_image(prompt="Less detail.", name="cactus.png", image_model=given)
    result = await run.result()

    assert result.error is not None
    assert f"This agent was given {given} to make its images with" in result.error
    assert len(images_api.requests) == sent


async def test_the_agent_is_told_the_size_and_quality_the_person_picked(agent: FakeDesignAgent) -> None:
    run = await designed(agent, name="new.png", prompt="A cactus.", size=(1536, 1024), quality="high")

    prompt = agent.runs[0].request.prompt
    assert "The user picked this method/model and the following parameters:" in prompt
    assert "   - The user picked these parameters for you to use:" in prompt
    assert "     - size: 1536x1024 (`--size 1536x1024`)" in prompt
    assert "     - quality: high (`--quality high`)" in prompt
    data = started(lib.read_image_activity("new.png").events)[run.run_id]
    assert (data["size"], data["quality"]) == ([1536, 1024], "high")


async def test_a_size_or_quality_the_image_model_cannot_take_is_refused_before_it_starts(
    agent: FakeDesignAgent,
) -> None:
    with pytest.raises(ImageDesignError, match="ChatGPT chooses the size and quality itself"):
        await lib.design_image(prompt="A cactus.", name="cactus.png", image_model="chatgpt", quality="high")
    with pytest.raises(ImageDesignError, match="The size 1000x1000 does not work"):
        await lib.design_image(prompt="A cactus.", name="cactus.png", size=(1000, 1000))
    assert agent.runs == []


async def test_an_image_model_the_agent_cannot_be_given_is_refused_before_it_starts(agent: FakeDesignAgent) -> None:
    with pytest.raises(ImageDesignError, match="not an image model the agent can be given"):
        await lib.design_image(prompt="A cactus.", name="cactus.png", image_model="gpt-image-1")
    with pytest.raises(ImageDesignError, match=r"makes only \.png images"):
        await lib.design_image(prompt="A cactus.", name="cactus.jpg", image_model="chatgpt")
    assert agent.runs == []


async def test_a_new_session_is_given_the_command_s_help_and_how_to_prompt_its_model(agent: FakeDesignAgent) -> None:
    agent.behavior = says("Which style?")
    await designed(agent, name="new.png", prompt="A cactus.")
    await made()
    await designed(agent)

    creating, editing = (run.request.prompt for run in agent.runs)
    prompting_openai = (
        f'<guidelines skill="prompting-openai-images" directory="{tooling.CRAFT / "prompting-openai-images"}">'
    )
    how_to_edit = '<guidelines skill="editing-images"'
    assert prompting_openai in creating
    assert how_to_edit not in creating
    assert prompting_openai in editing
    assert how_to_edit in editing
    assert "---" not in creating.split(prompting_openai)[1].split("</guidelines>")[0]
    assert '<skill_content name="image-design generate-openai-image">' in creating
    assert "references/openai-images-edit.md" in creating
    assert "The user picked this method/model." in creating
    assert "Its file holds v1, and its only version is v1." in editing


def test_the_guides_the_prompting_skills_point_to_are_there() -> None:
    for skill in ("prompting-openai-images", "prompting-chatgpt-images"):
        text = (tooling.CRAFT / skill / "SKILL.md").read_text(encoding="utf-8")
        named = re.findall(r"`((?:\.\./[\w-]+/)?references/[\w.-]+\.md)`", text)
        assert named
        for page in named:
            assert (tooling.CRAFT / skill / page).is_file(), page


async def test_a_new_session_with_chatgpt_is_given_its_help_and_how_to_prompt_it(agent: FakeDesignAgent) -> None:
    agent.behavior = says("Which style?")

    await designed(agent, name="new.png", prompt="A cactus.", image_model="chatgpt")

    prompt = agent.runs[0].request.prompt
    assert '<skill_content name="image-design generate-chatgpt-image">' in prompt
    assert '<guidelines skill="prompting-chatgpt-images"' in prompt
    assert '<guidelines skill="prompting-openai-images"' not in prompt
    assert "generate-openai-image --model" not in prompt
    assert "openai-images-edit.md" not in prompt


async def test_a_resumed_session_is_given_how_to_edit_and_the_help_only_for_another_command(
    agent: FakeDesignAgent,
) -> None:
    await made()
    agent.behavior = says("Done.")
    await designed(agent)
    await designed(agent, prompt="Again.", resume_session=True)
    await designed(agent, prompt="With ChatGPT.", resume_session=True, image_model="chatgpt")

    same, switched = (run.request.prompt for run in agent.runs[1:])
    for prompt in (same, switched):
        assert '<guidelines skill="editing-images"' in prompt
        assert '<guidelines skill="prompting-openai-images"' not in prompt
    assert "<tool_information>" not in same
    assert '<guidelines skill="prompting-chatgpt-images"' not in same
    assert "You should use `image-design generate-openai-image --model gpt-image-2.6-sunburst`" in same
    assert '<skill_content name="image-design generate-chatgpt-image">' in switched
    assert '<guidelines skill="prompting-chatgpt-images"' in switched


async def test_the_agent_is_given_a_work_directory_in_the_image_s_folder(agent: FakeDesignAgent) -> None:
    await made()

    run = await designed(agent)

    folder = Path(started(lib.read_image_activity("cactus.png").events)[run.run_id]["run_folder"])
    work = folder.parents[1] / "work"
    assert work.is_dir()
    assert f"its work directory: {work}." in agent.runs[0].request.prompt


async def test_a_new_image_is_created_by_the_agent_s_first_call(agent: FakeDesignAgent) -> None:
    agent.behavior = edits(name="new.png", prompt="A cactus on white.")

    await designed(agent, name="new.png", prompt="A cactus.")

    assert "The name of the image the user has asked you to create is new.png." in agent.runs[0].request.prompt
    assert [version.id for version in lib.view_image("new.png").versions] == ["v1"]


async def test_a_new_session_is_told_the_image_s_history(agent: FakeDesignAgent) -> None:
    await made(prompt="A small cactus, centered.")

    await designed(agent)

    prompt = agent.runs[0].request.prompt
    assert "## The image's history" in prompt
    assert "image-design generate-openai-image --name cactus.png" in prompt
    assert "A small cactus, centered." in prompt
    assert "It made v1. It is now the image's file." in prompt


async def test_a_new_session_is_told_only_the_last_calls_and_where_the_rest_are(agent: FakeDesignAgent) -> None:
    for said in ("Call one.", "Call two.", "Call three.", "Call four."):
        await made(prompt=said)

    run = await designed(agent)

    prompt = agent.runs[0].request.prompt
    assert "The last 3 of the 4 calls made on it, oldest first." in prompt
    assert "Call one." not in prompt
    assert all(said in prompt for said in ("Call two.", "Call three.", "Call four."))
    assert "`image-design read-image-activity --name cactus.png --json` has every call" in prompt
    runs = Path(started(lib.read_image_activity("cactus.png").events)[run.run_id]["run_folder"]).parent
    assert f"named by its id under {runs}." in prompt


async def test_a_session_that_goes_on_is_told_only_what_happened_since_its_last_turn(agent: FakeDesignAgent) -> None:
    await made()
    agent.behavior = edits(prompt="Remove the bud.")
    first = await designed(agent)
    await made(prompt="Make the pot blue.", quality="high")
    agent.behavior = says("Done.")

    second = await designed(agent, prompt="And now?", resume_session=True)

    resumed = agent.runs[1].request
    assert resumed.resume == agent.runs[0].session_id
    assert "## Since your last turn" in resumed.prompt
    assert "The person, in the app, made the call" in resumed.prompt
    assert "--name cactus.png --version v2 --model gpt-image-2.6-sunburst --quality high" in resumed.prompt
    assert "Make the pot blue." in resumed.prompt
    assert "Remove the bud." not in resumed.prompt
    assert "A small cactus." not in resumed.prompt
    data = started(lib.read_image_activity("cactus.png").events)
    assert len(data[second.run_id]["since"]) == 1
    assert data[second.run_id]["resumed"] == agent.runs[0].session_id
    assert data[first.run_id]["since"] == []


async def test_a_call_on_another_image_is_in_the_agent_s_conversation(agent: FakeDesignAgent) -> None:
    await made()
    agent.behavior = makes("cactus-variant.png")

    run = await designed(agent, prompt="A variant of its own.")

    variant = lib.view_image("cactus-variant.png")
    assert variant.last_run is not None
    assert variant.last_run.parent == run.run_id
    assert variant.last_run.parent_image == lib.view_image("cactus.png").id
    activity = lib.read_image_activity("cactus.png")
    data = started(activity.events)
    assert data[variant.last_run.id]["name"] == "cactus-variant.png"
    assert data[variant.last_run.id]["parent"] == run.run_id
    assert activity.cursor is not None
    assert activity.cursor.count("|") == 2
    times = [event.time for event in activity.events]
    assert times == sorted(times)
    assert lib.read_image_activity("cactus.png", after=activity.cursor).events == []


async def test_activity_read_from_a_cursor_has_only_what_came_after(agent: FakeDesignAgent) -> None:
    await made()
    before = lib.read_image_activity("cactus.png")
    agent.behavior = edits()

    run = await designed(agent)

    call = lib.view_image("cactus.png").last_run
    assert call is not None
    after = lib.read_image_activity("cactus.png", after=before.cursor)
    assert {event.run_id for event in after.events if event.kind == "started"} == {run.run_id, call.id}


async def test_one_agent_at_a_time_works_on_an_image(agent: FakeDesignAgent) -> None:
    await made()
    agent.behavior = hangs
    run = await lib.design_image(prompt="Go.", name="cactus.png")

    with pytest.raises(ImageDesignError, match=r"An agent is already working on cactus\.png") as raised:
        await lib.design_image(prompt="Again.", name="cactus.png")

    assert raised.value.reason == "already-running"
    await run.cancel()
    assert (await run.result()).status == "cancelled"


async def test_cancel_image_stops_the_agent(agent: FakeDesignAgent) -> None:
    await made()
    agent.behavior = hangs
    run = await lib.design_image(prompt="Go.", name="cactus.png")
    design = lib.view_image("cactus.png").design
    assert design is not None
    assert design.status == "running"

    lib.cancel_image("cactus.png")

    assert (await run.result()).status == "cancelled"
    assert agent.runs[0].cancels >= 1


async def test_a_message_reaches_the_agent_while_it_works(agent: FakeDesignAgent) -> None:
    await made()
    agent.behavior = waits_for_a_message()
    run = await lib.design_image(prompt="Go.", name="cactus.png")

    lib.steer_image("cactus.png", "Keep the open flower.", marks=[BUD])

    assert (await run.result()).status == "done"
    message, shown = agent.runs[0].steered[0]
    assert message.startswith("Keep the open flower.")
    assert "--marks" in message
    assert len(shown) == 1
    steered = [event for event in lib.read_image_activity("cactus.png").events if event.kind == "steered"]
    assert steered[0].data["message"] == "Keep the open flower."


async def test_steering_an_image_no_agent_works_on_is_refused(agent: FakeDesignAgent) -> None:
    await made()

    with pytest.raises(ImageDesignError, match=r"No agent is working on cactus\.png"):
        lib.steer_image("cactus.png", "Hello.")


async def test_marks_a_mask_and_references_go_with_the_request_as_files(agent: FakeDesignAgent, tmp_path: Path) -> None:
    await made()
    reference = tmp_path / "style.png"
    Image.new("RGB", (64, 48), "#2a9d8f").save(reference)
    mask = tmp_path / "mask.png"
    Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)).save(mask)

    run = await designed(agent, marks=[BUD], mask=mask, references=[reference])

    request = agent.runs[0].request
    folder = Path(started(lib.read_image_activity("cactus.png").events)[run.run_id]["run_folder"])
    marks = json.loads((folder / "inputs" / "marks.json").read_text(encoding="utf-8"))
    assert marks[0]["note"] == "this bud"
    assert str(folder / "inputs" / "marks.json") in request.prompt
    assert str(folder / "inputs" / "mask.png") in request.prompt
    assert str(folder / "inputs" / "reference-1.png") in request.prompt
    assert [path.name for path in request.images] == ["image.png", "marked.png", "1.png"]


async def test_an_svg_is_left_to_the_drawing_agent(agent: FakeDesignAgent) -> None:
    with pytest.raises(ImageDesignError, match="draw_svg_image"):
        await lib.design_image(prompt="A logo.", name="logo.svg")


async def test_marks_need_an_image_to_be_on(agent: FakeDesignAgent) -> None:
    with pytest.raises(ImageDesignError, match=r"no image named new\.png to edit"):
        await lib.design_image(prompt="Change it.", name="new.png", marks=[BUD])
    assert lib.list_images().images == []


async def test_a_file_a_script_made_is_kept_as_a_version(agent: FakeDesignAgent, tmp_path: Path) -> None:
    await made()
    cropped = tmp_path / "cropped.png"
    Image.new("RGB", (300, 200), "#e9c46a").save(cropped)

    summary = lib.add_image_version("cactus.png", cropped)

    assert summary.current == "v2"
    assert (summary.width, summary.height) == (300, 200)
    assert summary.versions[-1].method == "imported"
    jpeg = tmp_path / "cropped.jpg"
    Image.new("RGB", (30, 20), "#e9c46a").save(jpeg)
    assert lib.add_image_version("cactus.png", jpeg).current == "v3"
    gif = tmp_path / "moving.gif"
    frames = [Image.new("RGB", (16, 16), color) for color in ("red", "blue")]
    frames[0].save(gif, save_all=True, append_images=frames[1:])
    with pytest.raises(ImageDesignError, match="cannot be one of its versions"):
        lib.add_image_version("cactus.png", gif)


async def test_a_version_kept_from_the_agent_s_processes_names_its_run(
    agent: FakeDesignAgent, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await made()
    run = await designed(agent)
    monkeypatch.setenv(PARENT, run.run_id)
    cropped = tmp_path / "cropped.png"
    Image.new("RGB", (30, 20), "#e9c46a").save(cropped)

    summary = lib.add_image_version("cactus.png", cropped)

    assert summary.versions[-1].run_id == run.run_id


async def test_a_call_naming_no_agent_s_run_is_refused(agent: FakeDesignAgent, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PARENT, "20260101-000000-abcdef")

    with pytest.raises(ImageDesignError, match="no agent's run '20260101-000000-abcdef'") as raised:
        await lib.generate_openai_image(prompt="A cactus.", name="cactus.png")

    assert raised.value.reason == "no-such-run"


def test_the_cli_runs_the_agent_and_prints_what_it_said_last(agent: FakeDesignAgent) -> None:
    asyncio.run(made())
    agent.behavior = says("Nothing needed changing.")

    result = runner.invoke(app, ["design-image", "Check it.", "--name", "cactus.png"])

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[-2:] == ["Nothing needed changing.", str(Path(".image-design") / "cactus.png")]


async def settled(name: str, done: Callable[[lib.ImageView], bool]) -> lib.ImageView:
    """The image once `done` says so of it, for runs in the app's own event loop, which this one cannot wait on."""
    for _ in range(500):
        image = lib.view_image(name)
        if done(image):
            return image
        await asyncio.sleep(0.01)
    raise AssertionError(f"{name} did not settle: {lib.view_image(name)}")


def agent_ended(run_id: str | None = None) -> Callable[[lib.ImageView], bool]:
    """Whether the image's agent's last run has ended, and is not `run_id`."""

    def done(image: lib.ImageView) -> bool:
        return image.design is not None and image.design.status != "running" and image.design.run_id != run_id

    return done


async def test_the_app_starts_the_agent_and_goes_on_in_its_session(
    agent: FakeDesignAgent, images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    await made()
    app_server = lib.app_server()

    # In this process, as the app's tests run them; the app runs each in a process of its own.
    async def design_here(detach: bool, **arguments: Any) -> lib.DesignRun:
        return await lib.design_image(**arguments)

    monkeypatch.setattr(app_server, "_generate", {**app_server._generate, "design_image": design_here})
    agent.behavior = makes("cactus.png", "cactus-b.png")

    try:
        async with Client(f"{app_server.open().url}/mcp") as client:
            begun = await client.call_tool(
                "design_image", {"prompt": "Two ideas.", "name": "cactus.png", "resume_session": False}
            )
            turn = await settled("cactus.png", agent_ended())
            listing = (await client.call_tool("list_images", {})).structured_content or {}
            agent.behavior = says("v2 is in.")
            assert turn.design is not None
            again = await client.call_tool(
                "design_image",
                {
                    "prompt": "Keep the first.",
                    "name": "cactus.png",
                    "resume_session": True,
                    "agent_provider": "claude",
                    "model": "claude-sonnet-5-5",
                    "reasoning_effort": "medium",
                },
            )
            after = await settled("cactus.png", agent_ended(turn.design.run_id))
    finally:
        app_server.close()

    assert not begun.is_error, begun.content
    assert turn.design is not None
    assert (begun.structured_content or {})["run_id"] == turn.design.run_id
    designs = {image["name"]: image["design"] for image in listing["images"]}
    assert designs["cactus.png"]["status"] == "done"
    assert designs["cactus-b.png"] is None
    assert [version.id for version in turn.versions] == ["v1", "v2"]
    assert images_api.requests[-1].fields["prompt"] == "A variant for cactus-b.png."
    assert not again.is_error, again.content
    assert after.design is not None
    assert after.design.status == "done"
    assert agent.runs[-1].request.resume == agent.runs[0].session_id
    assert agent.runs[-1].request.reasoning_effort == "medium"
    assert lib.view_image("cactus-b.png").last_run is not None
