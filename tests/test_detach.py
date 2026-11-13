"""A run in a process of its own, as `detach=True` starts it, with the Images API faked there by detached_openai.py."""

import asyncio
import os

import detached_openai
from fake_openai import FakeImagesAPI
import pytest

from image_design import lib
from image_design.capabilities.openai_image import generate
from image_design.shared.images.store import directories, find_image

# A detached run starts a Python process of its own, which takes a while to import the library.
DETACHED_TIMEOUT_SECONDS = 30

pytestmark = pytest.mark.detached


async def test_a_detached_run_goes_on_in_its_own_process_and_cancel_image_stops_it(
    images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generate, "BACKGROUND_COMMAND", detached_openai.command("hang"))
    hanging = await lib.generate_openai_image("A cactus.", name="cactus.png", origin="app", detach=True)
    image = find_image(*directories(None, None), "cactus.png")
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
