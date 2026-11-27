"""Listing, viewing, moving, copying, importing, relinking, and deleting images and their folders, and listing the
ways of making one, from the library and the CLI."""

import asyncio
import hashlib
import json
from pathlib import Path

from fake_openai import FakeImagesAPI, picture
from PIL import Image
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.design_image import method as design_method
from image_design.cli import app
from image_design.intelligence import interface
from image_design.schemas import ImageDesignError
from image_design.shared.images.store import IMAGES, RECORD, new_image

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
    # The folder the image left stays, though it is empty.
    assert lib.list_images().folders == ["concepts", "drafts", "photos"]
    assert [version.id for version in lib.view_image("concepts/Cactus.png").versions] == ["v1", "v2"]
    assert (recased.name, recased.current) == ("Fern.png", "v1")
    assert (filed.name, filed.versions, filed.width) == ("photos/photo.jpg", [], 800)
    assert unmoved == filed
    with pytest.raises(ImageDesignError, match=r"ends in \.webp and Fern\.png is a \.png") as converted:
        lib.move_image("Fern.png", "fern.webp")
    with pytest.raises(ImageDesignError, match=r"already exists, so Fern\.png cannot take its name") as taken:
        lib.move_image("Fern.png", "concepts/cactus.png")
    assert (converted.value.reason, taken.value.reason) == ("invalid-name", "name-in-use")
    # Numbered, a move onto a name that is taken takes the next free name like it, past a file put there by hand.
    by_hand("concepts/cactus (2).png")
    numbered = lib.move_image("Fern.png", "concepts/cactus.png", numbered=True)
    assert (numbered.name, numbered.current) == ("concepts/cactus (3).png", "v1")


async def test_a_name_a_listing_hides_or_windows_cuts_short_is_refused_unless_an_image_already_has_it(
    images_api: FakeImagesAPI,
) -> None:
    await made("A cactus.", "cactus.png")
    # Kept under such a name before the tool refused one.
    new_image(ROOT.resolve(), DATA.resolve(), ".cactus.png")
    by_hand(".cactus.png")

    with pytest.raises(ImageDesignError, match="starts with a dot") as hidden:
        lib.move_image("cactus.png", ".drafts/cactus.png")
    with pytest.raises(ImageDesignError, match="ends in a dot or a space") as cut:
        lib.move_image("cactus.png", "drafts./cactus.png")
    with pytest.raises(ImageDesignError, match="ends in a dot or a space") as folder:
        lib.create_folder("drafts ")
    renamed = lib.move_image(".cactus.png", "old-cactus.png")

    assert [error.value.reason for error in (hidden, cut, folder)] == ["invalid-name"] * 3
    assert renamed.name == "old-cactus.png"
    assert [summary.name for summary in lib.list_images().images] == ["cactus.png", "old-cactus.png"]


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
    assert sorted(path.name for path in ROOT.iterdir()) == [".agents", "concepts", "photos"]
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


async def test_folders_are_made_moved_with_their_images_and_deleted_with_them(images_api: FakeImagesAPI) -> None:
    await made("A cactus.", "plants/cactus.png")
    await made("A fern.", "plants/ferns/fern.png")
    by_hand("plants/photo.jpg")
    (ROOT / "plants/notes.txt").write_text("Water weekly.", encoding="utf-8")

    made_folder = lib.create_folder("drafts/rough")
    again = lib.create_folder("drafts", numbered=True)
    with pytest.raises(ImageDesignError, match="already exists") as taken:
        lib.create_folder("drafts")
    with pytest.raises(ImageDesignError, match="starts with a dot") as hidden:
        lib.create_folder(".hidden")
    listed = lib.list_images().folders
    with pytest.raises(ImageDesignError, match="cannot be moved into itself") as inside:
        lib.move_folder("plants", "plants/ferns/plants")
    with pytest.raises(ImageDesignError, match=r"no folder named 'gone'.*The folders there: drafts") as missing:
        lib.move_folder("gone", "elsewhere")
    moved = lib.move_folder("PLANTS", "garden/plants")
    merged = lib.move_folder("drafts", "garden/plants", numbered=True)
    after = lib.list_images()
    await made("Make the pot blue.", "garden/plants/cactus.png")
    versions = [version.id for version in lib.view_image("garden/plants/cactus.png").versions]
    images_api.hang = True
    working = await lib.generate_openai_image("Add dew.", name="garden/plants/ferns/fern.png")
    with pytest.raises(ImageDesignError, match="already being worked on") as busy:
        lib.move_folder("garden", "yard")
    with pytest.raises(ImageDesignError, match="worked on by a run in this process"):
        lib.delete_folder("garden/plants")
    still_there = [summary.name for summary in lib.list_images().images]
    await working.cancel()
    await asyncio.wait_for(working.result(), 5)
    left = lib.delete_folder("garden/plants")
    gone = lib.delete_folder("garden/plants (2)")

    assert (made_folder, again) == ("drafts/rough", "drafts (2)")
    assert listed == ["drafts", "drafts (2)", "drafts/rough", "plants", "plants/ferns"]
    assert [error.value.reason for error in (taken, hidden, inside, missing, busy)] == [
        "name-in-use",
        "invalid-name",
        "invalid-name",
        "no-such-folder",
        "already-running",
    ]
    assert (moved, merged) == ("garden/plants", "garden/plants (2)")
    assert after.folders == [
        "drafts (2)",
        "garden",
        "garden/plants",
        "garden/plants (2)",
        "garden/plants (2)/rough",
        "garden/plants/ferns",
    ]
    # Each image is under its new name with what was kept for it, and a file that is not an image went along.
    assert [(summary.name, summary.current) for summary in after.images] == [
        ("garden/plants/cactus.png", "v1"),
        ("garden/plants/ferns/fern.png", "v1"),
        ("garden/plants/photo.jpg", None),
    ]
    assert (versions, len(still_there)) == (["v1", "v2"], 3)
    # The images are gone with what was kept for them, and what is not an image keeps its folder.
    assert (left, gone) == (["garden/plants/notes.txt"], [])
    assert (lib.list_images().images, list((DATA / IMAGES).iterdir())) == ([], [])
    assert lib.list_images().folders == ["drafts (2)", "garden", "garden/plants"]


async def test_a_copy_has_everything_kept_for_the_image_and_is_its_own_image_from_then_on(
    images_api: FakeImagesAPI,
) -> None:
    await made("A cactus.", "cactus.png")
    await made("Make it bloom.", "cactus.png")
    by_hand("photo.jpg")

    copy = lib.copy_image("cactus.png", "concepts/cactus.png")
    second = lib.copy_image("cactus.png", "cactus.png", numbered=True)
    photo = lib.copy_image("photo.jpg", "photos/photo.jpg")
    with pytest.raises(ImageDesignError, match=r"so a copy of cactus\.png cannot take its name") as taken:
        lib.copy_image("cactus.png", "concepts/cactus.png")
    with pytest.raises(ImageDesignError, match=r"ends in \.webp") as converted:
        lib.copy_image("cactus.png", "cactus.webp")
    await made("Make the pot blue.", "concepts/cactus.png")
    lib.delete_image("cactus.png")
    restored = lib.restore_image_version("concepts/cactus.png", "v1")
    history = lib.read_image_activity("concepts/cactus.png")
    started = [event for event in history.events if event.kind == "started"]

    numbered, copied = lib.list_images().images[:2]
    assert (copy.name, copy.current, [version.id for version in copy.versions]) == (
        "concepts/cactus.png",
        "v2",
        ["v1", "v2"],
    )
    assert (second.name, second.current) == ("cactus (2).png", "v2")
    assert (photo.name, photo.versions, photo.width) == ("photos/photo.jpg", [], 800)
    assert (taken.value.reason, converted.value.reason) == ("name-in-use", "invalid-name")
    # Each is its own image: the copy went on to a third version, and outlived the image it was copied from.
    assert (numbered.name, copied.name, numbered.id != copied.id) == ("cactus (2).png", "concepts/cactus.png", True)
    assert ([version.id for version in restored.versions], restored.current) == (["v1", "v2", "v3"], "v1")
    assert [event.data["prompt"] for event in started] == ["A cactus.", "Make it bloom.", "Make the pot blue."]
    # The runs it was copied with are read from the copy's own folder.
    assert all(Path(event.data["run_folder"]).parents[1].name == copied.id for event in started)


async def test_an_imported_file_is_kept_from_the_start_in_a_format_the_tool_keeps(
    images_api: FakeImagesAPI, tmp_path: Path
) -> None:
    jpeg = tmp_path / "Desk Photo.JPEG"
    Image.new("RGB", (640, 480), "#336699").save(jpeg, format="JPEG")
    bitmap = tmp_path / "scan.bmp"
    Image.new("RGB", (320, 200), "#993366").save(bitmap, format="BMP")
    text = tmp_path / "notes.png"
    text.write_text("Not an image.", encoding="utf-8")
    in_place = by_hand("photos/found.png")

    desk = lib.import_image(jpeg)
    scan = lib.import_image(bitmap, name="scans/")
    named = lib.import_image(jpeg, name="photos/my-desk.jpg")
    numbered = lib.import_image(jpeg, numbered=True)
    kept = lib.import_image(in_place, name="photos/found.png")
    with pytest.raises(ImageDesignError, match="is not an image the tool can read") as unreadable:
        lib.import_image(text)
    with pytest.raises(ImageDesignError, match=r"so Desk Photo\.JPEG cannot take its name") as taken:
        lib.import_image(jpeg)
    with pytest.raises(ImageDesignError, match=r"comes in as a \.jpg") as renamed:
        lib.import_image(jpeg, name="desk.png")
    with pytest.raises(ImageDesignError, match="is not a file") as missing:
        lib.import_image(tmp_path / "gone.png")
    await made("Make it warmer.", "Desk Photo.jpg")

    assert [(image.name, image.current, image.width) for image in (desk, scan, named, numbered, kept)] == [
        ("Desk Photo.jpg", "v1", 640),
        ("scans/scan.png", "v1", 320),
        ("photos/my-desk.jpg", "v1", 640),
        ("Desk Photo (2).jpg", "v1", 640),
        ("photos/found.png", "v1", 800),
    ]
    assert [version.method for version in desk.versions] == ["imported"]
    # A format the tool keeps comes in byte for byte, and the file it came from is left as it was.
    assert desk.versions[0].sha256 == hashlib.sha256(jpeg.read_bytes()).hexdigest()
    assert (jpeg.is_file(), bitmap.is_file()) == (True, True)
    with Image.open(ROOT / "scans/scan.png") as converted:
        assert converted.format == "PNG"
    assert [error.value.reason for error in (unreadable, taken, renamed, missing)] == [
        "not-an-image",
        "name-in-use",
        "invalid-name",
        "no-such-file",
    ]
    assert [version.id for version in lib.view_image("Desk Photo.jpg").versions] == ["v1", "v2"]


async def test_an_image_moved_outside_the_tool_is_relinked_to_its_file(images_api: FakeImagesAPI) -> None:
    for name in ("cactus.png", "fern.png", "moss.png", "a/twin.png", "lost.png"):
        await made(f"Paint {name}.", name)
    lib.copy_image("a/twin.png", "b/twin.png")
    by_hand("photo.jpg")
    kept = sorted(DATA.rglob("*"))
    nothing = lib.relink_images()
    untouched = sorted(DATA.rglob("*")) == kept
    # Moved, renamed, changed and then moved, a folder renamed with the same picture in two of them, and deleted.
    (ROOT / "plants").mkdir()
    (ROOT / "cactus.png").rename(ROOT / "plants/cactus.png")
    (ROOT / "fern.png").rename(ROOT / "bracken.png")
    (ROOT / "moss.png").unlink()
    by_hand("plants/moss.png", 640, 480)
    (ROOT / "a").rename(ROOT / "c")
    (ROOT / "b").rename(ROOT / "d")
    (ROOT / "lost.png").unlink()
    broken = lib.list_images()

    found = lib.relink_images()
    with pytest.raises(ImageDesignError, match=r"lost\.png has no likely file.*have one: moss\.png") as unlikely:
        lib.relink_images(likely=["lost.png"])
    taken = lib.relink_images(likely=["moss.png"])
    listing = lib.list_images()

    assert (nothing.relinked, nothing.likely, nothing.gone, untouched) == ([], [], [], True)
    assert [summary.name for summary in broken.images if summary.modified is None] == [
        "a/twin.png",
        "b/twin.png",
        "cactus.png",
        "fern.png",
        "lost.png",
        "moss.png",
    ]
    assert sorted((move.name, move.new_name) for move in found.relinked) == [
        ("cactus.png", "plants/cactus.png"),
        ("fern.png", "bracken.png"),
    ]
    assert [(move.name, move.new_name) for move in found.likely] == [("moss.png", "plants/moss.png")]
    # The same picture is in two files with the same name, so neither is certainly either image's.
    assert found.gone == ["a/twin.png", "b/twin.png", "lost.png"]
    assert unlikely.value.reason == "no-such-image"
    assert [(move.name, move.new_name) for move in taken.relinked] == [("moss.png", "plants/moss.png")]
    assert (taken.likely, taken.gone) == ([], ["a/twin.png", "b/twin.png", "lost.png"])
    assert [(summary.name, summary.current, len(summary.versions)) for summary in listing.images] == [
        ("a/twin.png", None, 1),
        ("b/twin.png", None, 1),
        ("bracken.png", "v1", 1),
        ("c/twin.png", None, 0),
        ("d/twin.png", None, 0),
        ("lost.png", None, 1),
        ("photo.jpg", None, 0),
        ("plants/cactus.png", "v1", 1),
        # Its file was changed before it moved, which the next edit keeps as a version of its own.
        ("plants/moss.png", None, 1),
    ]
    assert "relink-images --likely moss.png" in found.describe()


async def test_a_folder_renamed_outside_the_tool_is_relinked_image_by_image_and_each_keeps_its_id(
    images_api: FakeImagesAPI,
) -> None:
    await made("A cactus.", "set/one.png")
    lib.copy_image("set/one.png", "set/two.png")
    await made("A fern.", "set/fern.png")
    by_hand("set/photo.jpg")
    before = {summary.name: summary.id for summary in lib.list_images().images}
    (ROOT / "set").rename(ROOT / "kit")

    found = lib.relink_images()
    moved = lib.move_image("kit/fern.png", "fern.png")
    after = {summary.name: summary.id for summary in lib.list_images().images}

    # Two of them hold the same picture, and each is told from the other by its file name.
    assert [(move.name, move.new_name) for move in found.relinked] == [
        ("set/fern.png", "kit/fern.png"),
        ("set/one.png", "kit/one.png"),
        ("set/two.png", "kit/two.png"),
    ]
    assert (found.likely, found.gone) == ([], [])
    assert before["set/photo.jpg"] is None
    assert len({before["set/one.png"], before["set/two.png"], before["set/fern.png"], None}) == 4
    assert (moved.id, moved.current) == (before["set/fern.png"], "v1")
    assert after == {
        "fern.png": before["set/fern.png"],
        "kit/one.png": before["set/one.png"],
        "kit/photo.jpg": None,
        "kit/two.png": before["set/two.png"],
    }


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
    assert (ready.openai.max_images, ready.openai.max_previews) == (16, 3)
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
    assert ready.design.ready
    assert ready.design.default == ready.svg.default
    assert ready.svg.default.reasoning_effort == "high"
    assert not missing.design.ready
    assert "none is installed" in (missing.design.problem or "")
    assert ready.design.default_image_model == "gpt-image-2.6-sunburst"
    assert ready.design.image_models == ["gpt-image-2.6-sunburst", "gpt-image-2.6-flare", "chatgpt"]


def test_the_agent_is_not_ready_without_a_method_to_make_its_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    methods = lib.list_image_methods()
    unset = {"ready": False, "problem": "Set it up."}

    design = design_method.describe(
        methods.openai.model_copy(update=unset), methods.chatgpt.model_copy(update=unset), []
    )
    only_chatgpt = design_method.describe(methods.openai.model_copy(update=unset), methods.chatgpt, [])

    assert not design.ready
    assert "neither is set up" in (design.problem or "")
    assert only_chatgpt.default_image_model == "chatgpt"
    with pytest.raises(ImageDesignError, match=r"which is not set up\. Set it up\."):
        design_method.image_model(
            "gpt-image-2.6-flare", "cactus.png", methods.openai.model_copy(update=unset), methods.chatgpt, []
        )


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


def test_the_cli_copies_imports_and_relinks_images_and_makes_moves_and_deletes_folders(
    images_api: FakeImagesAPI, tmp_path: Path
) -> None:
    runner.invoke(app, ["generate-openai-image", "A cactus.", "--name", "cactus.png"])
    outside = tmp_path / "desk.jpeg"
    Image.new("RGB", (640, 480), "#336699").save(outside, format="JPEG")

    copied = runner.invoke(app, ["copy-image", "--name", "cactus.png", "--new-name", "cactus.png", "--numbered"])
    imported = runner.invoke(app, ["import-image", "--path", str(outside), "--name", "photos/"])
    made_folder = runner.invoke(app, ["create-folder", "--name", "drafts"])
    moved = runner.invoke(app, ["move-folder", "--name", "photos", "--new-name", "drafts", "--numbered"])
    (ROOT / "drafts (2)/notes.txt").write_text("Keep.", encoding="utf-8")
    (ROOT / "cactus.png").rename(ROOT / "drafts/cactus.png")
    listed = runner.invoke(app, ["list-images"])
    relinked = runner.invoke(app, ["relink-images"])
    relinked_json = runner.invoke(app, ["relink-images", "--json"])
    left = runner.invoke(app, ["delete-folder", "--name", "drafts (2)"])
    deleted = runner.invoke(app, ["delete-folder", "--name", "drafts"])
    after = runner.invoke(app, ["list-images"])

    assert copied.output.splitlines()[0] == f"{ROOT / 'cactus (2).png'} holds v1."
    assert imported.output.splitlines() == [
        f"{ROOT / 'photos/desk.jpg'} holds v1.",
        "",
        "- v1 (in the file): 640x480, imported",
    ]
    assert (made_folder.output, moved.output) == ("drafts\n", "drafts (2)\n")
    assert listed.output.splitlines() == [
        "- cactus (2).png: 1024x1024, holds v1, done",
        "- cactus.png: has no file, done",
        "- drafts (2)/desk.jpg: 640x480, holds v1",
        "- drafts/cactus.png: 1024x1024, has no versions yet",
        "An image has no file. If it was moved outside the tool, find it with: image-design relink-images",
    ]
    assert relinked.output == "Relinked cactus.png to drafts/cactus.png.\n"
    assert json.loads(relinked_json.output) == {"relinked": [], "likely": [], "gone": []}
    assert left.output == (
        "Deleted the images in drafts (2). It still holds what the tool does not delete: drafts (2)/notes.txt\n"
    )
    assert (deleted.exit_code, deleted.output) == (0, "")
    assert after.output.splitlines() == ["- cactus (2).png: 1024x1024, holds v1, done", "- drafts (2)/: no images"]
