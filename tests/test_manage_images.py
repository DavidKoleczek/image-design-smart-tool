"""Listing, viewing, moving, and deleting images, and listing the ways of making one, from the library and the CLI."""

import asyncio
import json
from pathlib import Path

from fake_openai import FakeImagesAPI, picture
from PIL import Image
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.cli import app
from image_design.intelligence import interface
from image_design.schemas import ImageDesignError
from image_design.shared.images.store import IMAGES, RECORD

runner = CliRunner()
ROOT = Path(".image-design")
DATA = ROOT / ".agents"


async def made(prompt: str, name: str) -> None:
    run = await lib.generate_openai_image(prompt, name=name)
    assert (await run.result()).status == "done"


def by_hand(name: str, width: int = 800, height: int = 600) -> Path:
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(picture(width, height, "#336699"))
    return path


async def test_a_directory_lists_the_images_the_tool_made_and_the_files_put_there_by_hand(
    images_api: FakeImagesAPI,
) -> None:
    empty = lib.list_images()
    read_only = not DATA.exists()
    await made("A paper-cut cactus.", "concepts/cactus.png")
    by_hand("Photo.PNG")
    # Neither is an image of the directory: one is hidden, and the other is the tool's own.
    by_hand(".drafts/hidden.png")
    assert list(DATA.rglob("v1.png"))

    listing = lib.list_images()
    cactus, photo = listing.images
    (ROOT / "concepts/cactus.png").write_bytes(picture(640, 480, "#ffffff"))
    [changed, _] = lib.list_images().images

    assert (empty.images, read_only) == ([], True)
    assert (listing.directory, listing.data_directory) == (ROOT.resolve(), DATA.resolve())
    assert [summary.name for summary in listing.images] == ["concepts/cactus.png", "Photo.PNG"]
    assert (cactus.width, cactus.height, cactus.frames, cactus.current, cactus.status) == (1024, 1024, 1, "v1", "done")
    assert cactus.modified is not None
    assert cactus.last_run is not None
    assert (cactus.last_run.prompt, cactus.last_run.method) == ("A paper-cut cactus.", "openai")
    assert (photo.width, photo.height, photo.current, photo.versions, photo.status) == (800, 600, None, [], None)
    assert photo.last_run is None
    # A file changed by hand holds no version the tool knows, and the listing shows the file as it now is.
    assert (changed.current, changed.width, [version.id for version in changed.versions]) == (None, 640, ["v1"])


async def test_a_listing_leaves_out_an_image_whose_data_cannot_be_read_and_says_why(images_api: FakeImagesAPI) -> None:
    await made("A cactus.", "cactus.png")
    await made("A fern.", "fern.png")
    [record] = [path for path in (DATA / IMAGES).glob(f"*/{RECORD}") if '"cactus.png"' in path.read_text("utf-8")]
    (record.parent / "versions.json").write_text("{", encoding="utf-8")
    Path("a-file").write_text("", encoding="utf-8")

    listing = lib.list_images()

    # Its file is still an image of the directory, so it is listed as one the tool keeps nothing for.
    assert [(summary.name, len(summary.versions)) for summary in listing.images] == [("cactus.png", 0), ("fern.png", 1)]
    assert len(listing.unreadable) == 1
    assert "versions.json" in listing.unreadable[0]
    with pytest.raises(ImageDesignError, match="is a file, not a directory of images"):
        lib.list_images(directory=Path("a-file"))


async def test_viewing_an_image_only_reads_it(images_api: FakeImagesAPI) -> None:
    await made("A cactus.", "cactus.png")
    by_hand("photo.jpg")
    kept = sorted(path for path in DATA.rglob("*") if path.is_file())

    viewed = lib.view_image("CACTUS.png")
    photo = lib.view_image("photo.jpg")
    with pytest.raises(
        ImageDesignError, match=r"no image named 'gone\.png'.*The images there: cactus\.png, photo\.jpg"
    ):
        lib.view_image("gone.png")
    (ROOT / "cactus.png").unlink()
    without_file = lib.view_image("cactus.png")
    earlier = lib.view_image("cactus.png", version="v1")

    assert (viewed.name, viewed.current) == ("cactus.png", "v1")
    assert viewed.viewed is not None
    assert (viewed.viewed.version, viewed.viewed.width, len(viewed.viewed.frames)) == (None, 1024, 1)
    assert (photo.name, photo.versions, photo.viewed and photo.viewed.width) == ("photo.jpg", [], 800)
    # An image whose file is gone has nothing to view frame by frame but its versions.
    assert (without_file.modified, without_file.viewed, without_file.versions[0].id) == (None, None, "v1")
    assert earlier.viewed is not None
    assert earlier.viewed.version == "v1"
    with pytest.raises(ImageDesignError, match="has no file that can be read") as nothing:
        lib.view_image("cactus.png", frames_output=Path("out"))
    assert nothing.value.reason == "no-such-file"
    assert sorted(path for path in DATA.rglob("*") if path.is_file()) == kept


async def test_a_moved_image_keeps_its_versions_and_the_next_edit_adds_to_them(images_api: FakeImagesAPI) -> None:
    await made("A cactus.", "drafts/cactus.png")
    await made("A fern.", "fern.png")
    by_hand("photo.jpg")

    moved = lib.move_image("drafts/cactus.png", "concepts/Cactus.png")
    await made("Make the pot blue.", "concepts/cactus.png")
    recased = lib.move_image("fern.png", "Fern.png")
    filed = lib.move_image("photo.jpg", "photos/photo.jpg")
    unmoved = lib.move_image("photos/photo.jpg", "photos/photo.jpg")

    assert (moved.name, moved.current, moved.path) == (
        "concepts/Cactus.png",
        "v1",
        (ROOT / "concepts/Cactus.png").resolve(),
    )
    # The folder the image left is removed once it is empty.
    assert sorted(path.name for path in ROOT.iterdir() if not path.name.startswith(".")) == [
        "Fern.png",
        "concepts",
        "photos",
    ]
    assert [version.id for version in lib.view_image("concepts/Cactus.png").versions] == ["v1", "v2"]
    assert (recased.name, recased.current) == ("Fern.png", "v1")
    assert (filed.name, filed.versions, filed.width) == ("photos/photo.jpg", [], 800)
    assert unmoved == filed
    with pytest.raises(ImageDesignError, match=r"ends in \.webp and Fern\.png is a \.png") as converted:
        lib.move_image("Fern.png", "fern.webp")
    with pytest.raises(ImageDesignError, match=r"already exists, so Fern\.png cannot take its name") as taken:
        lib.move_image("Fern.png", "concepts/cactus.png")
    assert (converted.value.reason, taken.value.reason) == ("invalid-name", "name-in-use")


async def test_a_deleted_image_is_gone_with_everything_kept_for_it(images_api: FakeImagesAPI) -> None:
    await made("A cactus.", "concepts/cactus.png")
    by_hand("photos/photo.jpg")
    images_api.hang = True
    working = await lib.generate_openai_image("A fern.", name="fern.png")

    lib.delete_image("concepts/cactus.png")
    lib.delete_image("photos/photo.jpg")
    with pytest.raises(ImageDesignError, match="worked on by a run in this process") as busy:
        lib.delete_image("fern.png")
    with pytest.raises(ImageDesignError, match="already being worked on"):
        lib.move_image("fern.png", "plants/fern.png")
    await working.cancel()
    await asyncio.wait_for(working.result(), 5)
    lib.delete_image("fern.png")

    assert busy.value.reason == "already-running"
    assert lib.list_images().images == []
    assert [path.name for path in ROOT.iterdir()] == [".agents"]
    assert list((DATA / IMAGES).iterdir()) == []
    with pytest.raises(ImageDesignError, match=r"no image named 'fern\.png'"):
        lib.delete_image("fern.png")


async def test_viewing_an_image_gives_its_frames_and_how_long_each_shows_and_writes_them_out_as_pngs(
    images_api: FakeImagesAPI,
) -> None:
    run = await lib.generate_openai_image("A cactus swaying.", name="loops/sway.gif", frames=3, frame_ms=120)
    assert (await run.result()).status == "done"
    edit = await lib.generate_openai_image("Sway further.", name="loops/sway.gif", frames=2, frame_ms=300)
    assert (await edit.result()).status == "done"
    by_hand("photo.png")

    read = lib.view_image("loops/sway.gif").viewed
    earlier = lib.view_image("loops/sway.gif", version="v1", frames_output=Path("out/frames")).viewed
    still = lib.view_image("photo.png", frames_output=Path("out/still")).viewed
    shown = runner.invoke(app, ["view-image", "--name", "loops/sway.gif", "--frames-output", "out/shown"])
    still_shown = runner.invoke(app, ["view-image", "--name", "photo.png", "--frames-output", "out/still"])
    with pytest.raises(ImageDesignError, match="no version 'v9'") as unknown:
        lib.view_image("loops/sway.gif", version="v9")
    with pytest.raises(ImageDesignError, match=r"no image named 'fern\.gif'") as missing:
        lib.view_image("fern.gif")

    assert read is not None
    assert earlier is not None
    assert still is not None
    assert (read.version, read.width, read.height) == (None, 512, 512)
    assert [(frame.index, frame.duration_ms, frame.path) for frame in read.frames] == [(0, 300, None), (1, 300, None)]
    assert earlier.version == "v1"
    assert [(frame.index, frame.duration_ms) for frame in earlier.frames] == [(0, 120), (1, 120), (2, 120)]
    written = [frame.path for frame in earlier.frames]
    assert written == [(Path("out/frames") / f"frame-{index}.png").resolve() for index in range(3)]
    # Each frame is the whole picture as it shows then, and the fake paints each frame another color.
    colors = set()
    for path in written:
        assert path is not None
        with Image.open(path) as frame:
            assert (frame.format, frame.size) == ("PNG", (512, 512))
            colors.add(frame.convert("RGB").getpixel((0, 0)))
    assert len(colors) == 3
    assert [(frame.index, frame.duration_ms) for frame in still.frames] == [(0, 0)]
    assert (still.width, still.height, Path("out/still/frame-0.png").is_file()) == (800, 600, True)
    assert shown.output.splitlines() == [
        f"{ROOT / 'loops/sway.gif'} holds v2.",
        "",
        "- v1: 512x512, 3 frames, openai",
        "- v2 (in the file): 512x512, 2 frames, openai",
        "",
        "loops/sway.gif: 2 frames of 512x512, 600 ms in all.",
        "",
        f"- 0: 300 ms, {Path('out/shown/frame-0.png')}",
        f"- 1: 300 ms, {Path('out/shown/frame-1.png')}",
    ]
    assert still_shown.output.splitlines()[-1] == f"photo.png: 800x600. Its frame: {Path('out/still/frame-0.png')}"
    assert (unknown.value.reason, missing.value.reason) == ("no-such-version", "no-such-image")


def test_the_methods_say_what_each_takes_and_what_is_left_to_set_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    ready = lib.list_image_methods()
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(interface, "find_spec", lambda module: None)
    missing = lib.list_image_methods()

    assert (ready.openai.ready, ready.chatgpt.ready, ready.svg.ready) == (True, True, True)
    assert (ready.openai.problem, ready.chatgpt.problem, ready.svg.problem) == (None, None, None)
    assert ready.openai.formats == [".png", ".jpg", ".webp", ".gif"]
    assert [model.id for model in ready.openai.models] == ["gpt-image-2.6-sunburst", "gpt-image-2.6-flare"]
    assert ready.openai.default_model == "gpt-image-2.6-sunburst"
    assert (ready.openai.max_images, ready.openai.max_count, ready.openai.max_previews) == (16, 10, 3)
    assert (ready.chatgpt.formats, ready.chatgpt.max_images, ready.chatgpt.default_reasoning_effort) == (
        [".png"],
        5,
        "low",
    )
    assert {model.agent_provider for model in ready.chatgpt.models} == {"codex"}
    assert ready.chatgpt.default_model in [model.id for model in ready.chatgpt.models]
    assert (ready.svg.formats, ready.svg.default_canvas) == ([".svg"], (512, 512))
    assert ready.svg.default.model in [model.id for model in ready.svg.models]
    assert (missing.openai.ready, missing.chatgpt.ready, missing.svg.ready) == (False, False, False)
    assert "OPENAI_API_KEY" in (missing.openai.problem or "")
    assert "codex agent provider is not installed" in (missing.chatgpt.problem or "")
    assert "none is installed" in (missing.svg.problem or "")
    assert missing.svg.models == []


def test_the_cli_lists_views_moves_and_deletes_images(images_api: FakeImagesAPI) -> None:
    runner.invoke(app, ["generate-openai-image", "A cactus.", "--name", "cactus.png"])
    by_hand("photo.jpg")

    nothing_viewed = runner.invoke(app, ["list-images"])
    viewed = runner.invoke(app, ["view-image", "--name", "cactus.png"])
    moved = runner.invoke(app, ["move-image", "--name", "cactus.png", "--new-name", "concepts/cactus.png", "--json"])
    listed = runner.invoke(app, ["list-images"])
    as_json = runner.invoke(app, ["list-images", "--json"])
    deleted = runner.invoke(app, ["delete-image", "--name", "concepts/cactus.png"])
    missing = runner.invoke(app, ["delete-image", "--name", "concepts/cactus.png"])
    methods = runner.invoke(app, ["list-image-methods"])
    methods_json = runner.invoke(app, ["list-image-methods", "--json"])
    elsewhere = runner.invoke(app, ["list-images", "--directory", "nowhere"])

    assert nothing_viewed.output.splitlines() == [
        "- cactus.png: 1024x1024, holds v1, done",
        "- photo.jpg: 800x600, has no versions yet",
    ]
    assert viewed.output.splitlines() == [
        f"{ROOT / 'cactus.png'} holds v1.",
        "",
        "- v1 (in the file): 1024x1024, openai",
    ]
    assert json.loads(moved.output)["name"] == "concepts/cactus.png"
    assert listed.output.splitlines() == [
        "- concepts/cactus.png: 1024x1024, holds v1, done",
        "- photo.jpg: 800x600, has no versions yet",
    ]
    assert [image["name"] for image in json.loads(as_json.output)["images"]] == ["concepts/cactus.png", "photo.jpg"]
    assert (deleted.exit_code, deleted.output) == (0, "")
    assert isinstance(missing.exception, ImageDesignError)
    assert "no image named" in str(missing.exception)
    assert methods.output.startswith("generate-openai-image: ready\n- Names end in: .png, .jpg, .webp, .gif\n")
    assert "\n\ndraw-svg-image: " in methods.output
    assert json.loads(methods_json.output)["chatgpt"]["max_images"] == 5
    assert elsewhere.output == "There are no images in nowhere.\n"
