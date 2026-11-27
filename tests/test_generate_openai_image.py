"""Creating and editing images through the Images API, faked in fake_openai.py, from the library and the CLI."""

import asyncio
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any

from conftest import MemoryKeyring
from fake_openai import COLORS, FakeImagesAPI, picture
from PIL import Image
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.openai_image import images_api as images_api_module
from image_design.capabilities.openai_image.generate import MARKS_NOTE
from image_design.cli import app
from image_design.schemas import (
    DEFAULT_OPENAI_IMAGE_MODEL,
    ImageDesignError,
    ImageEvent,
    ImageRequestImage,
    ImageResult,
    ImageUsage,
    Mark,
    OpenAIKeyStatus,
)
from image_design.shared.images import pictures
from image_design.shared.images.store import GITIGNORE, LOCKS

runner = CliRunner()
CACTUS = Mark(shape="circle", points=[(0.4, 0.5), (0.6, 0.9)], note="this pot")


async def made(**arguments: Any) -> ImageResult:
    run = await lib.generate_openai_image(**arguments)
    return await run.result()


async def sent(images_api: FakeImagesAPI, count: int = 1) -> None:
    """Wait until the API has received `count` requests."""
    while len(images_api.requests) < count:
        await asyncio.sleep(0.01)


def color_of(content: bytes, x: int = 0, y: int = 0) -> tuple[int, ...]:
    with Image.open(BytesIO(content)) as image:
        pixel = image.convert("RGB").getpixel((x, y))
    assert isinstance(pixel, tuple)
    return pixel


def described(content: bytes) -> tuple[str, int, int]:
    found = pictures.describe(content)
    assert found is not None
    return found.format, found.width, found.height


def hex_color(color: str) -> tuple[int, ...]:
    return tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))


async def test_an_image_is_created_then_edited_then_restored_and_every_version_is_kept(
    images_api: FakeImagesAPI,
) -> None:
    directory, data = Path("art"), Path("data")
    where = {"directory": directory, "data_directory": data}
    created = await made(prompt="A paper-cut cactus.", name="concepts/cactus.png", **where)
    first = created.path.read_bytes()
    # A change by hand, which the edit has to keep rather than lose.
    created.path.write_bytes(picture(1024, 1024, "#ffffff"))
    Path("palette.png").write_bytes(picture(512, 512, "#000000"))
    edited = await made(
        prompt="Make the pot blue.",
        name="concepts/cactus.png",
        references=[Path("palette.png")],
        marks=[CACTUS],
        **where,
    )
    restored = lib.restore_image_version("concepts/cactus.png", "v1", **where)

    creating, editing = images_api.requests
    assert creating.path.endswith("/images/generations")
    assert creating.fields["model"] == DEFAULT_OPENAI_IMAGE_MODEL
    assert (created.status, [version.id for version in created.versions]) == ("done", ["v1"])
    assert created.usage == ImageUsage(input_text_tokens=100, output_tokens=800, cost=0.0245)
    assert editing.path.endswith("/images/edits")
    assert [color_of(image) for image in editing.files["image[]"]] == [(255, 255, 255), (0, 0, 0)]
    markup = Image.open(BytesIO(editing.files["markup"][0]))
    assert markup.size == (1024, 1024)
    assert markup.getpixel((0, 0)) == (0, 0, 0, 0)
    assert MARKS_NOTE in editing.fields["prompt"]
    assert "Mark 1 is a red circle: this pot" in editing.fields["prompt"]
    assert editing.fields["size"] == "1024x1024"
    assert [version.id for version in edited.versions] == ["v3"]
    assert edited.usage is not None
    assert edited.usage.cost == 0.0405
    assert restored.current == "v1"
    assert [(version.id, version.method) for version in restored.versions] == [
        ("v1", "openai"),
        ("v2", "imported"),
        ("v3", "openai"),
    ]
    assert created.path.read_bytes() == first
    assert (data / ".gitignore").read_text(encoding="utf-8") == GITIGNORE.read_text(encoding="utf-8")
    assert not (directory / ".agents").exists()


def test_a_saved_key_is_used_when_the_environment_has_none_and_is_never_part_of_its_status(
    credential_store: MemoryKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    before = (lib.openai_api_key_status(), lib.list_image_methods().openai.ready)
    with pytest.raises(ImageDesignError) as spaced:
        lib.save_openai_api_key("sk-test with a space")
    lib.save_openai_api_key("  sk-test-saved\n")
    saved = (lib.openai_api_key_status(), lib.list_image_methods().openai.ready)
    sent_with = images_api_module.client(5).api_key
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-environment")
    both = lib.openai_api_key_status()
    environment_wins = images_api_module.client(5).api_key
    lib.clear_openai_api_key()
    lib.clear_openai_api_key()
    monkeypatch.delenv("OPENAI_API_KEY")
    cleared = (lib.openai_api_key_status(), lib.list_image_methods().openai.problem)

    assert before == (OpenAIKeyStatus(source=None, saved=False), False)
    assert "not an API key" in str(spaced.value)
    assert saved == (OpenAIKeyStatus(source="saved", saved=True), True)
    assert (sent_with, environment_wins) == ("sk-test-saved", "sk-test-environment")
    assert both == OpenAIKeyStatus(source="environment", saved=True)
    assert "sk-test" not in saved[0].model_dump_json()
    assert credential_store.kept == {}
    assert cleared[0] == OpenAIKeyStatus(source=None, saved=False)
    assert cleared[1] is not None
    assert "save_openai_api_key" in cleared[1]


def test_a_key_is_not_called_saved_on_a_machine_with_no_credential_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ImageDesignError) as refused:
        lib.save_openai_api_key("sk-test-saved")

    assert refused.value.reason == "no-credential-store"
    assert "OPENAI_API_KEY environment variable instead" in str(refused.value)
    assert lib.openai_api_key_status() == OpenAIKeyStatus(source=None, saved=False)


async def test_a_sketch_of_several_strokes_is_drawn_as_one_mark_with_a_stroke_that_never_moved_as_a_dot(
    images_api: FakeImagesAPI,
) -> None:
    await made(prompt="A paper-cut cactus.", name="cactus.png")
    sketch = Mark(
        shape="sketch",
        points=[(0.1, 0.1), (0.3, 0.1)],
        strokes=[[(0.1, 0.5), (0.3, 0.5)], [(0.8, 0.8), (0.8, 0.8)]],
        color="blue",
    )
    await made(prompt="Make this taller.", name="cactus.png", marks=[sketch])
    with pytest.raises(ImageDesignError) as refused:
        await made(
            prompt="Make this taller.",
            name="cactus.png",
            marks=[Mark(shape="box", points=[(0.1, 0.1), (0.3, 0.3)], strokes=[[(0.5, 0.5), (0.6, 0.6)]])],
        )

    editing = images_api.requests[1]
    markup = Image.open(BytesIO(editing.files["markup"][0]))
    blue = (0, 0, 255, 255)
    assert [markup.getpixel(point) for point in ((205, 102), (205, 511), (818, 818))] == [blue, blue, blue]
    # Nothing joins one stroke to the next.
    assert markup.getpixel((205, 300)) == (0, 0, 0, 0)
    assert editing.fields["prompt"].count("Mark ") == 1
    assert "Mark 1 is a box with strokes, which only a sketch has" in str(refused.value)


async def test_a_numbered_mark_has_its_number_on_a_badge_of_its_color_above_it_and_the_prompt_says_so(
    images_api: FakeImagesAPI,
) -> None:
    await made(prompt="A paper-cut cactus.", name="cactus.png")
    pot = Mark(shape="box", points=[(0.25, 0.5), (0.75, 0.9)], numbered=True)
    await made(prompt="Make 2 blue.", name="cactus.png", marks=[CACTUS, pot])

    editing = images_api.requests[1]
    markup = Image.open(BytesIO(editing.files["markup"][0]))
    assert markup.size == (1024, 1024)
    # The box's lines are 9 pixels wide and its badge 6 lines tall, flush with its left edge, so it starts at
    # (256, 457), with a white 2 on red.
    badge = markup.crop((258, 459, 308, 509))
    colors = {color for _, color in badge.getcolors(badge.width * badge.height) or []}
    assert {(255, 0, 0, 255), (255, 255, 255, 255)} <= colors
    # Where an unnumbered circle's badge would be, off its upper left, nothing is drawn.
    assert markup.getpixel((412, 544)) == (0, 0, 0, 0)
    assert "- Mark 1 is a red circle: this pot\n- Mark 2 is a red box with a 2 beside it." in editing.fields["prompt"]


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"name": "cactus.svg"}, "does not end in an image format"),
        ({"name": "../cactus.png"}, "cannot name an image"),
        ({"name": ".drafts/cactus.png"}, "starts with a dot, which hides the image"),
        ({"name": "drafts./cactus.png"}, "ends in a dot or a space"),
        ({"name": "sway.gif", "previews": 1}, "A .gif has no previews"),
        ({"frames": 4}, "frames and frame_ms are for a .gif"),
        ({"compression": 50}, "compression is for a .jpg or .webp"),
        ({"name": "cactus.jpg", "background": "transparent"}, "A transparent background needs a .png or .webp"),
        ({"size": (1000, 1000)}, "The nearest size that works is 992x992"),
        ({"model": "dall-e-3"}, "not an image model the tool supports"),
        ({"marks": [CACTUS]}, "no image named cactus.png to edit"),
        ({"references": [Path("missing.png")]}, "is not a file"),
        ({"quality": "ultra"}, "quality"),
        ({"without_key": True}, "OPENAI_API_KEY"),
    ],
)
async def test_a_request_the_api_would_refuse_is_refused_before_anything_is_sent_or_kept(
    images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch, arguments: dict[str, Any], refusal: str
) -> None:
    if arguments.pop("without_key", False):
        monkeypatch.delenv("OPENAI_API_KEY")

    with pytest.raises(ImageDesignError, match=refusal):
        await lib.generate_openai_image("A cactus.", name=arguments.pop("name", "cactus.png"), **arguments)

    assert images_api.requests == []
    assert not list(Path(".image-design/.agents/images").glob("*"))


async def test_references_and_a_mask_in_any_format_are_sent_in_one_the_api_takes(images_api: FakeImagesAPI) -> None:
    await made(prompt="A cactus.", name="cactus.png")
    Path("logo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30"><rect width="40" height="30"/></svg>',
        encoding="utf-8",
    )
    for name in ("photo.bmp", "scan.tiff", "art.avif"):
        Image.new("RGB", (32, 32), "#2a9d8f").save(name)
    Image.new("RGB", (32, 32), "#2a9d8f").save("misnamed.png", format="JPEG")
    mask = Image.new("RGBA", (1024, 1024), (0, 0, 0, 255))
    mask.paste((0, 0, 0, 0), (0, 0, 512, 512))
    mask.save("mask.webp", lossless=True)
    Image.new("RGBA", (1024, 1024), (0, 0, 0, 255)).save("opaque.png")
    references = [Path(name) for name in ("logo.svg", "photo.bmp", "scan.tiff", "art.avif", "misnamed.png")]

    await made(prompt="Make it teal.", name="cactus.png", references=references, mask=Path("mask.webp"))
    with pytest.raises(ImageDesignError, match="has no transparent area"):
        await lib.generate_openai_image("Make it teal.", name="cactus.png", mask=Path("opaque.png"))

    _, editing = images_api.requests
    assert [described(content) for content in editing.files["image[]"][1:]] == [
        ("PNG", 40, 30),
        ("PNG", 32, 32),
        ("PNG", 32, 32),
        ("PNG", 32, 32),
        ("JPEG", 32, 32),
    ]
    assert [described(content) for content in editing.files["mask"]] == [("PNG", 1024, 1024)]


@pytest.mark.parametrize(
    ("api", "arguments", "status", "error"),
    [
        ({"status": 400}, {}, "failed", r"refused the request \(400, about size\): Invalid size\."),
        ({"status": 500, "error": "The server had an error."}, {}, "failed", r"\(500, about size\)"),
        ({"hang": True}, {"timeout_seconds": 1}, "timed-out", "did not finish within 1 seconds"),
        ({"hang": True}, {"cancel": True}, "cancelled", None),
    ],
)
async def test_a_run_that_makes_no_image_ends_saying_why_and_leaves_the_image_free(
    images_api: FakeImagesAPI, api: dict[str, Any], arguments: dict[str, Any], status: str, error: str | None
) -> None:
    for setting, value in api.items():
        setattr(images_api, setting, value)
    cancel = arguments.pop("cancel", False)

    run = await lib.generate_openai_image("A cactus.", name="cactus.png", **arguments)
    if cancel:
        await sent(images_api)
        await run.cancel()
    result = await run.result()

    # One request each, since one that failed may still have been billed.
    assert len(images_api.requests) == 1
    assert result.status == status
    if error is None:
        assert result.error is None
    else:
        assert result.error is not None
        assert re.search(error, result.error)
    assert not result.path.exists()
    assert not list(Path(".image-design/.agents", LOCKS).glob("*"))
    images_api.status, images_api.hang = 200, False
    assert (await made(prompt="A cactus.", name="cactus.png")).status == "done"


async def test_previews_arrive_before_the_image_and_a_gif_is_made_and_edited_frame_by_frame(
    images_api: FakeImagesAPI,
) -> None:
    run = await lib.generate_openai_image("A cactus.", name="cactus.png", previews=2)
    events = [event async for event in run.events()]
    gif = await made(prompt="A swaying cactus.", name="sway.gif", frames=4, frame_ms=100)
    edited = await made(prompt="Sway faster.", name="sway.gif", frame=2)

    streamed, animating, editing = images_api.requests
    assert [event.kind for event in events] == ["started", "preview", "preview", "version", "finished"]
    assert all(Path(event.data["path"]).is_file() for event in events if event.kind == "preview")
    assert (streamed.fields["stream"], streamed.fields["partial_images"]) == (True, 2)
    assert (animating.fields["frame_count"], animating.fields["frame_duration_ms"]) == (4, 100)
    assert animating.fields["output_format"] == "gif"
    assert gif.versions[0].frames == 4
    assert color_of(editing.files["image[]"][0]) == hex_color(COLORS[2])
    # An edit of a .gif keeps its size, frames, and timing unless asked otherwise.
    assert (editing.fields["size"], editing.fields["frame_count"], editing.fields["frame_duration_ms"]) == (
        "512x512",
        "4",
        "100",
    )
    assert [version.id for version in edited.versions] == ["v2"]
    assert edited.path.read_bytes() == edited.versions[0].file.read_bytes()


async def test_only_one_run_works_on_an_image_at_a_time_and_cancel_image_stops_it(images_api: FakeImagesAPI) -> None:
    images_api.hang = True
    run = await lib.generate_openai_image("A cactus.", name="cactus.png")
    await sent(images_api)

    with pytest.raises(ImageDesignError, match="already being worked on by process"):
        await lib.generate_openai_image("Another cactus.", name="CACTUS.png")
    lib.cancel_image("cactus.png")
    result = await asyncio.wait_for(run.result(), 5)

    assert result.status == "cancelled"
    with pytest.raises(ImageDesignError, match="no run going"):
        lib.cancel_image("cactus.png")


async def test_a_request_preview_is_what_the_request_then_sends_and_nothing_is_sent_or_kept_for_it(
    images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    Path("palette.png").write_bytes(picture(512, 512, "#000000"))
    create: dict[str, Any] = {
        "prompt": "A cactus.",
        "name": "cactus.jpg",
        "quality": "low",
        "compression": 80,
        "previews": 2,
    }
    edit: dict[str, Any] = {
        "prompt": "Make the pot blue.",
        "name": "cactus.jpg",
        "references": [Path("palette.png")],
    }
    # A preview sends nothing, so it needs no key.
    monkeypatch.delenv("OPENAI_API_KEY")
    creating = lib.preview_openai_image_request(**create)
    kept_for_a_preview = Path(".image-design").exists()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    await made(**create)
    before = sorted(Path(".image-design").rglob("*"))
    editing = lib.preview_openai_image_request(marks=[CACTUS], **edit)
    kept_for_an_edit = sorted(Path(".image-design").rglob("*")) != before
    await made(marks=[CACTUS], **edit)

    created, edited = images_api.requests
    assert (kept_for_a_preview, kept_for_an_edit) == (False, False)
    assert (creating.method, creating.name, creating.edits, creating.images) == ("openai", "cactus.jpg", False, [])
    assert (creating.prompt, creating.added) == ("A cactus.", None)
    assert creating.parameters == {
        "model": DEFAULT_OPENAI_IMAGE_MODEL,
        "quality": "low",
        "output_format": "jpeg",
        "output_compression": 80,
        "partial_images": 2,
    }
    assert {name: created.fields[name] for name in creating.parameters} == creating.parameters
    assert set(created.fields) - set(creating.parameters) == {"prompt", "stream"}
    assert editing.edits
    assert editing.images == [
        ImageRequestImage(role="source", path=Path(".image-design/cactus.jpg").resolve()),
        ImageRequestImage(role="reference", path=Path("palette.png")),
        ImageRequestImage(role="marks", path=None),
    ]
    assert editing.prompt == edited.fields["prompt"]
    assert editing.added == f"{MARKS_NOTE}\n- Mark 1 is a red circle: this pot"
    # An edit asks for the size of the image it edits, which the preview has worked out.
    assert editing.parameters["size"] == "1024x1024"
    assert {name: edited.fields[name] for name in editing.parameters} == {
        name: str(value) for name, value in editing.parameters.items()
    }
    assert set(edited.fields) - set(editing.parameters) == {"prompt"}


def test_the_cli_prints_each_image_made_and_exits_with_the_run_s_status(images_api: FakeImagesAPI) -> None:
    Path("marks.json").write_text(json.dumps([{"shape": "box", "points": [[0.1, 0.1], [0.5, 0.5]]}]), encoding="utf-8")

    made = runner.invoke(app, ["generate-openai-image", "A cactus.", "--name", "cactus.jpg"])
    edited = runner.invoke(
        app, ["generate-openai-image", "A blue pot.", "--name", "cactus.jpg", "--marks", "marks.json", "--json"]
    )
    restored = runner.invoke(app, ["restore-image-version", "--name", "cactus.jpg", "--version", "v1"])
    images_api.status = 400
    refused = runner.invoke(app, ["generate-openai-image", "A cactus.", "--name", "other.png", "--size", "1024x1024"])

    assert made.exit_code == 0, made.output
    assert made.stdout.splitlines() == [str(Path(".image-design", "cactus.jpg"))]
    assert "Saved v1 of cactus.jpg" in made.stderr
    assert edited.exit_code == 0, edited.output
    events = [ImageEvent.model_validate_json(line) for line in edited.stdout.splitlines()]
    assert [event.kind for event in events] == ["started", "version", "finished"]
    assert restored.exit_code == 0, restored.output
    assert "holds v1." in restored.stdout
    assert refused.exit_code == 1
    assert "Invalid size." in refused.stderr
    assert refused.stdout == ""
