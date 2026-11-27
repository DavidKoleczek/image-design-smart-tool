"""A run in a process of its own, as `detach=True` starts it, with the Images API faked there by detached_openai.py and
the image's agent by detached_design.py."""

import asyncio
import os
from pathlib import Path

import detached_design
import detached_openai
from fake_openai import FakeImagesAPI
import pytest

from image_design import lib
from image_design.capabilities.design_image import design
from image_design.capabilities.openai_image import generate
from image_design.shared.images.store import alive, directories, find_image

# A detached run starts a Python process of its own, which takes a while to import the library.
DETACHED_TIMEOUT_SECONDS = 30

pytestmark = pytest.mark.detached


async def test_a_detached_run_goes_on_in_its_own_process_and_cancel_image_stops_it(
    images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generate, "BACKGROUND_COMMAND", detached_openai.command("hang"))
    hanging = await lib.generate_openai_image("A cactus.", name="cactus.png", origin="app", detach=True)
    image = find_image(*directories(None), "cactus.png")
    assert image is not None
    lib.cancel_image("cactus.png")
    cancelled = await asyncio.wait_for(hanging.result(), DETACHED_TIMEOUT_SECONDS)

    monkeypatch.setattr(generate, "BACKGROUND_COMMAND", detached_openai.command("answer"))
    answered = await lib.generate_openai_image("A cactus.", name="cactus.png", detach=True)
    done = await asyncio.wait_for(answered.result(), DETACHED_TIMEOUT_SECONDS)
    events = [event async for event in answered.events()]

    assert image.runs[0].pid != os.getpid()
    assert image.runs[0].origin == "app"
    assert cancelled.status == "cancelled"
    assert done.status == "done"
    assert done.path.is_file()
    assert [event.kind for event in events] == ["started", "version", "finished"]
    assert images_api.requests == []


async def test_delete_image_stops_a_detached_run_and_then_removes_the_image(
    images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generate, "BACKGROUND_COMMAND", detached_openai.command("hang"))
    await lib.generate_openai_image("A cactus.", name="cactus.png", detach=True)
    image = find_image(*directories(None), "cactus.png")
    assert image is not None
    [run] = image.runs

    lib.delete_image("cactus.png")

    assert not alive(run.pid)
    assert not image.folder.exists()
    assert lib.list_images().images == []


async def test_a_detached_agent_given_a_workspace_runs_there_and_not_where_it_was_started(
    images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(design, "BACKGROUND_COMMAND", detached_design.command(tmp_path / "state"))
    garden = tmp_path / "garden"
    garden.mkdir()
    monkeypatch.chdir(tmp_path)

    run = await lib.design_image("A cactus.", name="cactus.png", workspace=Path("garden"), detach=True)
    result = await asyncio.wait_for(run.result(), DETACHED_TIMEOUT_SECONDS)
    said = [event.text async for event in run.events() if event.data.get("kind") == "message"]

    assert (result.status, result.path) == ("done", garden / ".image-design" / "cactus.png")
    assert said == [str(garden)]
    assert not (tmp_path / ".image-design").exists()
