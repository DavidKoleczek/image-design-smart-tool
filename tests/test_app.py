import asyncio
import base64
from collections.abc import Callable, Iterator
from io import BytesIO
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from conftest import MemoryKeyring
import detached_openai
from fake_drawing import fake_agent, steered_to
from fake_openai import FakeImagesAPI, picture
from mcp import Client, MCPError
from mcp.types import BlobResourceContents, TextContent, TextResourceContents
from PIL import Image
import pytest
from typer.testing import CliRunner

from image_design import lib
from image_design.capabilities.app import library as library_module
from image_design.capabilities.app import server as server_module
from image_design.capabilities.app import uploads
from image_design.capabilities.app.tools import VIEW_URI
from image_design.capabilities.openai_image import generate
from image_design.cli import app as cli_app
from image_design.schemas import (
    AppImageRequest,
    AppImages,
    AppLayout,
    AppSettings,
    AppState,
    AppTab,
    AppWorkspaces,
    ImageActivity,
    ImageDesignConfig,
    ImageDesignError,
    ImageImports,
    ImageListing,
    ImageMethods,
    ImageMove,
    ImageRequestPreview,
    ImageSummary,
    ImageView,
    PaneLayout,
    RecentWorkspace,
    ReferenceEntry,
    ReferenceLibrary,
    UsedReference,
)

TIMEOUT_SECONDS = 5
# A detached run starts a Python process of its own, which takes a while to import the library.
DETACHED_TIMEOUT_SECONDS = 30


@pytest.fixture
def open_app() -> Iterator[Callable[..., lib.AppServer]]:
    opened: list[lib.AppServer] = []

    def open_with(workspace: Path | None = None) -> lib.AppServer:
        # The working directory when none is given, as `mcp` shows, which a test that makes images makes its own.
        app_server = lib.app_server(workspace or Path.cwd())
        app_server.open()
        opened.append(app_server)
        return app_server

    yield open_with
    for app_server in opened:
        app_server.close()


def get(url: str, origin: str | None = None) -> tuple[int, dict[str, str], str]:
    request = Request(url, headers={"Origin": origin} if origin else {})
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read().decode("utf-8")


def sandbox_url(app: server_module.App) -> str:
    _, _, page = get(app.url)
    port = re.search(r'name="image-design-sandbox-port" content="(\d+)"', page)
    assert port is not None
    return f"http://127.0.0.1:{port[1]}"


def text_of(result: Any) -> str:
    return "\n".join(block.text for block in result.content if isinstance(block, TextContent))


def test_the_host_page_points_at_a_sandbox_on_another_origin_and_only_its_own_pages_reach_mcp(
    open_app: Callable[..., lib.AppServer],
) -> None:
    app = open_app().open()
    sandbox = sandbox_url(app)
    status, headers, page = get(f"{sandbox}/sandbox.html")

    assert sandbox != app.url
    assert status == 200
    assert "connect-src 'none'" in headers["content-security-policy"]
    assert f'content="{app.url.rsplit(":", 1)[1]}"' in page
    assert get(f"{sandbox}/")[0] == 404
    assert get(f"{app.url}/mcp", origin="https://example.com")[0] == 403


async def test_the_host_page_reaches_the_same_server_and_view_at_its_own_mcp(
    open_app: Callable[..., lib.AppServer],
) -> None:
    app_server = open_app()

    async with Client(f"{app_server.open().url}/mcp") as client:
        view = (await client.read_resource(VIEW_URI)).contents[0]
        tools = (await client.list_tools()).tools

    assert isinstance(view, TextResourceContents)
    assert view.text == lib.app_view()
    assert [tool.name for tool in tools] == ["open_app"]


def test_opening_the_app_again_returns_the_same_page(open_app: Callable[..., lib.AppServer]) -> None:
    app_server = open_app()

    assert app_server.open().url == app_server.open().url


def test_the_view_names_the_build_command_until_compiled_and_then_carries_the_tool_s_version_and_docs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = tmp_path / "mcp_app.html"
    monkeypatch.setattr(server_module, "VIEW", page)

    with pytest.raises(ImageDesignError, match=r"uv run build-app\.py"):
        lib.app_view()
    page.write_text(
        '<meta name="image-design-version" content="{{version}}"><meta name="image-design-repository" '
        'content="{{repository}}">',
        encoding="utf-8",
    )
    monkeypatch.setattr(server_module, "repository_url", lambda: "https://example.com/tool?a=1&b=2")

    assert lib.app_view() == (
        f'<meta name="image-design-version" content="{lib.version()}"><meta name="image-design-repository" '
        'content="https://example.com/tool?a=1&amp;b=2">'
    )


def test_the_committed_view_is_compiled() -> None:
    assert "{{version}}" not in lib.app_view()
    assert (server_module.HOST_STATIC / "index.html").is_file()
    assert (server_module.HOST_STATIC / "sandbox.html").is_file()


def test_a_held_port_is_a_named_failure_until_close_frees_it() -> None:
    first = lib.app_server()
    port = int(first.open().url.rsplit(":", 1)[1])

    with pytest.raises(ImageDesignError, match="could not bind"):
        lib.app_server().open(port)

    first.close()
    second = lib.app_server()
    second.open(port)
    second.close()


async def test_the_view_lists_the_images_of_the_app_s_workspace_until_open_app_names_another(
    open_app: Callable[..., lib.AppServer], tmp_path: Path
) -> None:
    (tmp_path / "first" / ".image-design").mkdir(parents=True)
    (tmp_path / "first" / ".image-design" / "photo.png").write_bytes(picture(800, 600, "#336699"))
    (tmp_path / "second").mkdir()
    (tmp_path / "file").write_text("", encoding="utf-8")
    app_server = open_app(tmp_path / "first")

    async with Client(f"{app_server.open().url}/mcp") as client:
        started = await client.call_tool("list_images", {})
        opened = await client.call_tool("open_app", {"workspace": str(tmp_path / "second")})
        switched = await client.call_tool("list_images", {})
        refused = await client.call_tool("open_app", {"workspace": str(tmp_path / "file")})
        kept = await client.call_tool("list_images", {})
        unknown = await client.call_tool("draw", {})

    first = ImageListing.model_validate(started.structured_content)
    second = ImageListing.model_validate(switched.structured_content)
    assert (first.workspace, first.directory, first.data_directory) == (
        tmp_path / "first",
        tmp_path / "first" / ".image-design",
        tmp_path / "first" / ".image-design" / ".agents",
    )
    assert [(image.name, image.width, image.height) for image in first.images] == [("photo.png", 800, 600)]
    assert f"It shows the images in the workspace {tmp_path / 'second'}." in text_of(opened)
    assert f'Pass `--workspace "{tmp_path / "second"}"`' in text_of(opened)
    assert (second.workspace, second.images) == (tmp_path / "second", [])
    assert not (tmp_path / "second" / ".image-design").exists()
    assert refused.structured_content == {"reason": "no-such-workspace", "image": None}
    assert "is not a folder, so it cannot be the workspace" in text_of(refused)
    assert ImageListing.model_validate(kept.structured_content) == second
    assert app_server.workspace == tmp_path / "second"
    assert unknown.structured_content == {"reason": "no-such-tool", "image": None}
    assert "The tools are: open_app, list_images, " in text_of(unknown)


async def test_the_view_keeps_the_person_s_settings_in_their_config_directory_for_every_workspace(
    open_app: Callable[..., lib.AppServer], tmp_path: Path, config_directory: Path
) -> None:
    (tmp_path / "logos").mkdir()
    (tmp_path / "photos").mkdir()
    logos = open_app(tmp_path / "logos")
    photos = open_app(tmp_path / "photos")
    settings = AppSettings(theme="dark", wide=AppLayout(images=PaneLayout(open=False), request=PaneLayout(size=420)))
    kept = config_directory / "image-design" / "app-settings.json"

    async with Client(f"{logos.open().url}/mcp") as client:
        before = await client.call_tool("read_app_settings", {})
        saved = await client.call_tool("save_app_settings", {"settings": settings.model_dump(mode="json")})
    async with Client(f"{photos.open().url}/mcp") as client:
        elsewhere = await client.call_tool("read_app_settings", {})
        bad = await client.call_tool("save_app_settings", {"settings": {"wide": {"images": {"size": -1}}}})
        untouched = kept.read_text(encoding="utf-8")
        kept.write_text("{not json", encoding="utf-8")
        unreadable = await client.call_tool("read_app_settings", {})

    assert AppSettings.model_validate(before.structured_content) == AppSettings()
    assert AppSettings.model_validate(saved.structured_content) == settings
    assert AppSettings.model_validate(elsewhere.structured_content) == settings
    assert AppSettings.model_validate_json(untouched) == settings
    assert bad.structured_content == {"reason": "bad-settings", "image": None}
    assert "The app setting wide.images.size is not valid" in text_of(bad)
    assert AppSettings.model_validate(unreadable.structured_content) == AppSettings()


async def test_the_view_changes_the_order_the_agent_picks_an_image_model_in(
    open_app: Callable[..., lib.AppServer], tmp_path: Path
) -> None:
    app_server = open_app(tmp_path)

    async with Client(f"{app_server.open().url}/mcp") as client:
        before = await client.call_tool("read_config", {})
        changed = await client.call_tool("update_config", {"design_image_models": ["chatgpt"]})
        methods = await client.call_tool("list_image_methods", {})
        refused = await client.call_tool("update_config", {"design_image_models": ["gpt-image-1"]})

    assert ImageDesignConfig.model_validate(before.structured_content) == ImageDesignConfig()
    assert ImageDesignConfig.model_validate(changed.structured_content).design_image_models == ["chatgpt"]
    assert ImageMethods.model_validate(methods.structured_content).design.image_models[0] == "chatgpt"
    assert refused.structured_content == {"reason": "bad-config", "image": None}
    assert lib.read_config().design_image_models == ["chatgpt"]
    assert not list(tmp_path.rglob("app-settings.json"))


async def test_what_was_picked_in_the_app_is_kept_with_each_workspace_s_data(
    open_app: Callable[..., lib.AppServer], tmp_path: Path, config_directory: Path
) -> None:
    (tmp_path / "logos").mkdir()
    (tmp_path / "photos").mkdir()
    app_server = open_app(tmp_path / "logos")
    data = tmp_path / "logos" / ".image-design" / ".agents"

    async with Client(f"{app_server.open().url}/mcp") as client:
        before = await client.call_tool("read_app_state", {})
        read_only = not (tmp_path / "logos" / ".image-design").exists()
        saved = await client.call_tool("save_app_state", {"state": {"method": "svg"}})
        picked = AppImageRequest(model="chatgpt", size=(1536, 1024), format=".webp", reasoning_effort="high")
        request = await client.call_tool("save_app_state", {"state": {"request": picked.model_dump(mode="json")}})
        await client.call_tool("save_app_state", {"state": {"method": "svg"}})
        bad = await client.call_tool("save_app_state", {"state": {"method": "paint"}})
        await client.call_tool("open_app", {"workspace": str(tmp_path / "photos")})
        elsewhere = await client.call_tool("read_app_state", {})
        await client.call_tool("open_app", {"workspace": str(tmp_path / "logos")})
        back = await client.call_tool("read_app_state", {})

    assert (AppState.model_validate(before.structured_content), read_only) == (AppState(), True)
    assert AppState.model_validate(saved.structured_content) == AppState(method="svg")
    assert AppState.model_validate(request.structured_content) == AppState(request=picked)
    assert AppState.model_validate_json((data / "app" / "app.json").read_text(encoding="utf-8")) == AppState(
        method="svg"
    )
    # The data directory's .gitignore comes with it, so what the app keeps there stays out of a project's commits.
    assert (data / ".gitignore").is_file()
    assert bad.structured_content == {"reason": "bad-state", "image": None}
    assert "The app state method is not valid" in text_of(bad)
    assert AppState.model_validate(elsewhere.structured_content) == AppState()
    assert AppState.model_validate(back.structured_content) == AppState(method="svg")
    assert not any(config_directory.rglob("app.json"))


async def made(prompt: str, name: str) -> None:
    run = await lib.generate_openai_image(prompt, name=name)
    assert (await run.result()).status == "done"


async def test_the_view_views_restores_moves_and_deletes_images_and_reads_their_history(
    open_app: Callable[..., lib.AppServer], images_api: FakeImagesAPI
) -> None:
    await made("A paper-cut cactus.", "cactus.png")
    await made("Make it bloom.", "cactus.png")
    (Path(".image-design") / "photo.png").write_bytes(picture(800, 600, "#336699"))
    app_server = open_app()

    async with Client(f"{app_server.open().url}/mcp") as client:
        first = await client.call_tool("list_images", {})
        opened = await client.call_tool("open_app", {"name": "CACTUS.png"})
        # A view saving what it picked, read before the image was brought up, leaves the image as it is.
        await client.call_tool("save_app_state", {"state": {"method": "svg"}})
        brought_up = await client.call_tool("list_images", {})
        missing = await client.call_tool("open_app", {"name": "fern.png"})
        await client.call_tool("show_image", {"name": "photo.png"})
        picked = await client.call_tool("list_images", {})
        await client.call_tool("show_image", {"name": "cactus.png"})
        viewed = await client.call_tool("view_image", {"name": "cactus.png", "version": "v1"})
        restored = await client.call_tool("restore_image_version", {"name": "cactus.png", "version": "v1"})
        history = await client.call_tool("read_image_activity", {"name": "cactus.png"})
        cursor = (history.structured_content or {})["cursor"]
        since = await client.call_tool("read_image_activity", {"name": "cactus.png", "after": cursor})
        converted = await client.call_tool("move_image", {"name": "cactus.png", "new_name": "cactus.jpg"})
        moved = await client.call_tool("move_image", {"name": "cactus.png", "new_name": "plants/cactus.png"})
        followed = await client.call_tool("list_images", {})
        deleted = await client.call_tool("delete_image", {"name": "plants/cactus.png"})
        gone = await client.call_tool("view_image", {"name": "plants/cactus.png"})
        emptied = await client.call_tool("list_images", {})

    activity = ImageActivity.model_validate(history.structured_content)
    assert AppImages.model_validate(first.structured_content).shown is None
    assert "with cactus.png in view." in text_of(opened)
    assert AppImages.model_validate(brought_up.structured_content).shown == "cactus.png"
    assert missing.structured_content == {"reason": "no-such-image", "image": "fern.png"}
    assert AppImages.model_validate(picked.structured_content).shown == "photo.png"
    view = ImageView.model_validate(viewed.structured_content)
    assert (view.current, view.viewed and view.viewed.version) == ("v2", "v1")
    assert ImageSummary.model_validate(restored.structured_content).current == "v1"
    assert [event.data["prompt"] for event in activity.events if event.kind == "started"] == [
        "A paper-cut cactus.",
        "Make it bloom.",
    ]
    assert ImageActivity.model_validate(since.structured_content).events == []
    assert converted.structured_content == {"reason": "invalid-name", "image": "cactus.png"}
    summary = ImageSummary.model_validate(moved.structured_content)
    assert (summary.name, [version.id for version in summary.versions]) == ("plants/cactus.png", ["v1", "v2"])
    assert AppImages.model_validate(followed.structured_content).shown == "plants/cactus.png"
    assert not deleted.is_error
    assert gone.structured_content == {"reason": "no-such-image", "image": "plants/cactus.png"}
    emptied_listing = AppImages.model_validate(emptied.structured_content)
    assert ([image.name for image in emptied_listing.images], emptied_listing.shown) == (["photo.png"], None)


async def listed(client: Client) -> AppImages:
    return AppImages.model_validate((await client.call_tool("list_images", {})).structured_content)


async def test_the_view_files_images_in_folders_copies_and_imports_them_and_follows_one_moved_outside_the_app(
    open_app: Callable[..., lib.AppServer],
    images_api: FakeImagesAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(uploads, "UPLOADS", tmp_path / "uploads")
    await made("A paper-cut cactus.", "cactus.png")
    root = Path(".image-design").resolve()
    (root / "photo.png").write_bytes(picture(800, 600, "#336699"))
    outside = tmp_path / "desk.jpeg"
    outside.write_bytes(picture(640, 480, "#336699", "jpeg"))
    text = tmp_path / "notes.png"
    text.write_text("Not an image.", encoding="utf-8")
    library_module.remember_used(root / ".agents", [UsedReference(name="cactus.png", path=root / "cactus.png")])
    app_server = open_app()
    monkeypatch.setattr(app_server, "_choose_files", lambda directory, title, instead: [outside, text])

    async with Client(f"{app_server.open().url}/mcp") as client:
        folder = await client.call_tool("create_folder", {"name": "plants"})
        again = await client.call_tool("create_folder", {"name": "plants", "numbered": True})
        taken = await client.call_tool("create_folder", {"name": "plants"})
        await client.call_tool("show_image", {"name": "cactus.png"})
        tabs = [{"name": "cactus.png", "preview": True}, {"name": "photo.png"}]
        await client.call_tool("save_app_state", {"state": {"pins": [str(root / "cactus.png")], "tabs": tabs}})
        moved = await client.call_tool("move_image", {"name": "cactus.png", "new_name": "plants/cactus.png"})
        numbered = await client.call_tool(
            "move_image", {"name": "photo.png", "new_name": "plants/cactus.png", "numbered": True}
        )
        renamed = await client.call_tool("move_folder", {"name": "plants", "new_name": "garden"})
        followed = await listed(client)
        state = AppState.model_validate((await client.call_tool("read_app_state", {})).structured_content)
        offered = ReferenceLibrary.model_validate(
            (await client.call_tool("read_reference_library", {})).structured_content
        )
        copied = await client.call_tool(
            "copy_image", {"name": "garden/cactus.png", "new_name": "garden/cactus.png", "numbered": True}
        )
        await upload(client, "a" * 32, "desk.jpeg", outside.read_bytes())
        imported = await client.call_tool("import_image", {"upload": "a" * 32, "folder": "garden"})
        cleared = await client.call_tool("import_image", {"upload": "a" * 32, "folder": "garden"})
        chosen = await client.call_tool("choose_image_files", {"folder": "plants (2)"})
        # As a file manager would: one image moved as it is, and one changed and then moved.
        (root / "garden/cactus.png").rename(root / "cactus-moved.png")
        (root / "garden/desk.jpg").unlink()
        (root / "desk.jpg").write_bytes(picture(320, 200, "#993366", "jpeg"))
        relinked = await listed(client)
        again_listed = await listed(client)
        took = await client.call_tool("relink_image", {"name": "garden/desk.jpg"})
        settled = await listed(client)
        left = await client.call_tool("delete_folder", {"name": "garden"})
        emptied = await listed(client)

    assert (folder.structured_content, again.structured_content) == ({"name": "plants"}, {"name": "plants (2)"})
    assert taken.structured_content == {"reason": "name-in-use", "image": None}
    assert ImageSummary.model_validate(moved.structured_content).name == "plants/cactus.png"
    assert ImageSummary.model_validate(numbered.structured_content).name == "plants/cactus (2).png"
    assert renamed.structured_content == {"name": "garden"}
    # What the app keeps by an image's name or path went with it: the image shown, the tabs, a pin, and a reference
    # used before.
    assert (followed.shown, followed.folders) == ("garden/cactus.png", ["garden", "plants (2)"])
    assert state.tabs == [AppTab(name="garden/cactus.png", preview=True), AppTab(name="garden/cactus (2).png")]
    assert state.pins == [root / "garden/cactus.png"]
    assert [(entry.name, entry.path) for entry in offered.used] == [("cactus.png", root / "garden/cactus.png")]
    assert ImageSummary.model_validate(copied.structured_content).name == "garden/cactus (3).png"
    desk = ImageSummary.model_validate(imported.structured_content)
    assert (desk.name, desk.current, desk.width) == ("garden/desk.jpg", "v1", 640)
    assert cleared.structured_content == {"reason": "bad-upload", "image": None}
    picked = chosen.structured_content or {}
    assert [image["name"] for image in picked["images"]] == ["plants (2)/desk.jpg"]
    assert [(refused["name"], refused["reason"]) for refused in picked["refused"]] == [("notes.png", "not-an-image")]
    # The image moved as it is keeps its versions under its file's name, and the other is offered, not taken.
    moved_by_hand = next(image for image in relinked.images if image.name == "cactus-moved.png")
    assert (relinked.shown, moved_by_hand.current) == ("cactus-moved.png", "v1")
    assert relinked.likely == [ImageMove(name="garden/desk.jpg", new_name="desk.jpg")]
    assert again_listed == relinked
    assert (took.structured_content or {})["relinked"] == [{"name": "garden/desk.jpg", "new_name": "desk.jpg"}]
    assert settled.likely == []
    assert [(image.name, len(image.versions)) for image in settled.images] == [
        ("cactus-moved.png", 1),
        ("desk.jpg", 1),
        ("garden/cactus (2).png", 0),
        ("garden/cactus (3).png", 1),
        ("plants (2)/desk.jpg", 1),
    ]
    assert left.structured_content == {"left": []}
    assert ([image.name for image in emptied.images], emptied.folders) == (
        ["cactus-moved.png", "desk.jpg", "plants (2)/desk.jpg"],
        ["plants (2)"],
    )


async def test_the_view_shows_an_image_a_folder_or_the_image_directory_in_the_file_manager_and_nothing_outside_it(
    open_app: Callable[..., lib.AppServer], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / ".image-design"
    (root / "plants").mkdir(parents=True)
    (root / "plants" / "fern.png").write_bytes(picture(64, 64, "#008000"))
    (tmp_path / "elsewhere.png").write_bytes(picture(64, 64, "#00ff00"))
    shown: list[Path] = []
    app_server = open_app(tmp_path)
    monkeypatch.setattr(app_server, "_show_in_file_manager", shown.append)

    async with Client(f"{app_server.open().url}/mcp") as client:
        for named in ({"name": "plants/fern.png"}, {"name": "plants"}, {}):
            await client.call_tool("show_in_file_manager", named)
        refused = [
            await client.call_tool("show_in_file_manager", {"name": name})
            for name in ("plants/cactus.png", "../elsewhere.png", str(tmp_path / "elsewhere.png"))
        ]

    assert shown == [root / "plants" / "fern.png", root / "plants", root]
    assert [result.structured_content for result in refused] == [{"reason": "no-such-file", "image": None}] * 3


async def test_the_view_names_the_settings_folder_and_opens_it_even_before_anything_is_kept_there(
    monkeypatch: pytest.MonkeyPatch, config_directory: Path, tmp_path: Path
) -> None:
    shown: list[Path] = []
    app_server = lib.app_server(tmp_path)
    monkeypatch.setattr(app_server, "_show_in_file_manager", shown.append)
    settings = config_directory / "image-design"

    async with Client(app_server.server) as client:
        folders = await client.call_tool("read_app_folders", {})
        opened = await client.call_tool("open_app_folder", {"folder": "settings"})

    assert folders.structured_content == {"settings": str(settings)}
    assert opened.structured_content == {"opened": str(settings)}
    assert shown == [settings]
    assert settings.is_dir()


async def test_the_view_reads_an_image_s_file_its_versions_and_small_copies_of_them_and_no_other_file(
    open_app: Callable[..., lib.AppServer], images_api: FakeImagesAPI
) -> None:
    root = Path(".image-design")
    await made("A paper-cut cactus.", "my art/cactus.png")
    await made("Make it bloom.", "my art/cactus.png")
    drawing = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32"><rect width="64" height="32"/></svg>'
    (root / "mark.svg").write_text(drawing, encoding="utf-8")
    (root.parent / "outside.png").write_bytes(picture(800, 600, "#336699"))
    app_server = open_app()

    def size(contents: object) -> tuple[str | None, tuple[int, int]]:
        assert isinstance(contents, BlobResourceContents)
        with Image.open(BytesIO(base64.b64decode(contents.blob))) as image:
            return contents.mime_type, image.size

    async def read(uri: str) -> BlobResourceContents:
        [contents] = (await client.read_resource(uri)).contents
        assert isinstance(contents, BlobResourceContents)
        return contents

    async with Client(f"{app_server.open().url}/mcp") as client:
        listing = ImageListing.model_validate((await client.call_tool("list_images", {})).structured_content)
        [_, cactus] = listing.images
        file = await read("image-design://images/my%20art/cactus.png")
        first = await read("image-design://versions/v1/my%20art/cactus.png")
        small = await read("image-design://thumbnails/file/my%20art/cactus.png")
        small_first = await read("image-design://thumbnails/v1/my%20art/cactus.png")
        vector = await read("image-design://images/mark.svg")
        small_vector = await read("image-design://thumbnails/file/mark.svg")
        # Put there since the view last listed the images, as one an agent just made is.
        (root / "new.png").write_bytes(picture(640, 480, "#ffffff"))
        fresh = await read("image-design://images/new.png")
        refused: list[str] = []
        for uri in (
            "image-design://images/../outside.png",
            "image-design://images/.agents/.gitignore",
            "image-design://versions/v9/my%20art/cactus.png",
            "image-design://thumbnails/file/missing.png",
            "image-design://elsewhere/cactus.png",
        ):
            with pytest.raises(MCPError) as failure:
                await client.read_resource(uri)
            refused.append(str(failure.value))

    assert base64.b64decode(file.blob) == (root / "my art/cactus.png").read_bytes()
    assert (file.mime_type, cactus.current) == ("image/png", "v2")
    assert base64.b64decode(first.blob) == cactus.versions[0].file.read_bytes()
    assert size(small) == ("image/webp", (256, 256))
    assert size(small_first) == ("image/webp", (256, 256))
    assert small.blob != small_first.blob
    assert (vector.mime_type, base64.b64decode(vector.blob).decode("utf-8")) == ("image/svg+xml", drawing)
    # A drawing is rendered at the size of the thumbnail, not shrunk or left small.
    assert size(small_vector) == ("image/webp", (256, 128))
    assert size(fresh) == ("image/png", (640, 480))
    assert "no image named '../outside.png'" in refused[0]
    assert "no image named '.agents/.gitignore'" in refused[1]
    assert "has no version 'v9'. Its versions: v1, v2." in refused[2]
    assert "no image named 'missing.png'" in refused[3]
    assert "is not a resource of this server" in refused[4]


async def test_the_view_reads_an_animation_frame_by_frame_and_sends_one_frame_of_it(
    open_app: Callable[..., lib.AppServer],
    images_api: FakeImagesAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(uploads, "UPLOADS", tmp_path / "uploads")
    run = await lib.generate_openai_image("A cactus swaying.", name="loops/sway.gif", frames=3, frame_ms=120)
    assert (await run.result()).status == "done"
    edit = await lib.generate_openai_image("Sway further.", name="loops/sway.gif", frames=2, frame_ms=300)
    assert (await edit.result()).status == "done"
    app_server = open_app()

    def color(contents: object) -> tuple[str | None, tuple[int, int], object]:
        assert isinstance(contents, BlobResourceContents)
        with Image.open(BytesIO(base64.b64decode(contents.blob))) as image:
            return contents.mime_type, image.size, image.convert("RGB").getpixel((0, 0))

    async with Client(f"{app_server.open().url}/mcp") as client:
        listing = ImageListing.model_validate((await client.call_tool("list_images", {})).structured_content)
        [sway] = listing.images
        frames = ((await client.call_tool("view_image", {"name": "loops/sway.gif"})).structured_content or {})["viewed"]
        earlier = await client.call_tool("view_image", {"name": "loops/sway.gif", "version": "v1"})
        # Out of order, as when a frame is picked on the timeline.
        read = [
            color((await client.read_resource(f"image-design://frames/v1/{index}/loops/sway.gif")).contents[0])
            for index in (2, 0, 1)
        ]
        [small] = (await client.read_resource("image-design://frame-thumbnails/file/1/loops/sway.gif")).contents
        refused: list[str] = []
        for uri in (
            "image-design://frames/file/2/loops/sway.gif",
            "image-design://frames/v9/0/loops/sway.gif",
            "image-design://frames/file/0/missing.gif",
        ):
            with pytest.raises(MCPError) as failure:
                await client.read_resource(uri)
            refused.append(str(failure.value))
        request = {"prompt": "Only the top sways.", "name": "loops/sway.gif"}
        marked = await client.call_tool(
            "preview_openai_image_request",
            {**request, "frame": 1, "marks": [{"shape": "box", "points": [[0.1, 0.1], [0.4, 0.4]]}]},
        )
        longer = await client.call_tool("preview_openai_image_request", {**request, "frames": 6, "frame_ms": 80})
        still = await client.call_tool(
            "preview_openai_image_request",
            {"prompt": "As a poster.", "name": "poster.png", "references": [{"path": str(sway.path), "frame": 1}]},
        )
        beyond = await client.call_tool(
            "preview_openai_image_request",
            {"prompt": "As a poster.", "name": "poster.png", "references": [{"path": str(sway.path), "frame": 5}]},
        )

    assert [(frame["index"], frame["duration_ms"], frame["path"]) for frame in frames["frames"]] == [
        (0, 300, None),
        (1, 300, None),
    ]
    assert len((earlier.structured_content or {})["viewed"]["frames"]) == 3
    assert [(kind, size) for kind, size, _ in read] == [("image/png", (512, 512))] * 3
    assert len({pixel for _, _, pixel in read}) == 3
    assert color(small)[:2] == ("image/webp", (256, 256))
    assert "has 2 frame(s), so there is no frame at that index" in refused[0]
    assert "has no version 'v9'" in refused[1]
    assert "no image named 'missing.gif'" in refused[2]
    kept = ImageRequestPreview.model_validate(marked.structured_content)
    asked = ImageRequestPreview.model_validate(longer.structured_content)
    poster = ImageRequestPreview.model_validate(still.structured_content)
    # An edit of an animation keeps its own length unless the request says another.
    assert (kept.parameters["frame_count"], kept.parameters["frame_duration_ms"]) == (2, 300)
    assert [image.role for image in kept.images] == ["source", "marks"]
    assert (asked.parameters["frame_count"], asked.parameters["frame_duration_ms"]) == (6, 80)
    [sent] = poster.images
    assert (sent.role, sent.path is not None and sent.path.name) == ("reference", "sway-frame-2.png")
    assert sent.path is not None
    with Image.open(sent.path) as frame:
        assert (frame.format, frame.size) == ("PNG", (512, 512))
    assert beyond.structured_content == {"reason": "invalid-request", "image": None}
    # The frame made for a request no one sent goes when the app closes.
    app_server.close()
    assert not sent.path.exists()


async def test_the_view_reads_what_each_method_takes_and_previews_a_request_without_sending_it(
    open_app: Callable[..., lib.AppServer], images_api: FakeImagesAPI
) -> None:
    await made("A paper-cut cactus.", "cactus.png")
    app_server = open_app()

    async with Client(f"{app_server.open().url}/mcp") as client:
        methods = await client.call_tool("list_image_methods", {})
        editing = await client.call_tool(
            "preview_openai_image_request",
            {"prompt": "Make it bloom.", "name": "cactus.png", "version": "v1", "size": [1536, 1024], "quality": "low"},
        )
        creating = await client.call_tool(
            "preview_chatgpt_image_request", {"prompt": "A fern.", "name": "fern.png", "transparent": True}
        )
        refused = await client.call_tool("preview_openai_image_request", {"prompt": " ", "name": "fern.png"})
        idle = await client.call_tool("cancel_image", {"name": "cactus.png"})
        listed = await client.call_tool("list_images", {})

    [cactus] = ImageListing.model_validate(listed.structured_content).images
    edit = ImageRequestPreview.model_validate(editing.structured_content)
    create = ImageRequestPreview.model_validate(creating.structured_content)
    assert ImageMethods.model_validate(methods.structured_content) == lib.list_image_methods()
    assert (edit.method, edit.edits, [image.path for image in edit.images]) == (
        "openai",
        True,
        [cactus.versions[0].file],
    )
    assert (edit.parameters["size"], edit.parameters["quality"]) == ("1536x1024", "low")
    assert (create.method, create.edits, create.images) == ("chatgpt", False, [])
    assert create.parameters["transparent_background"] is True
    assert refused.structured_content == {"reason": "invalid-request", "image": "fern.png"}
    assert idle.structured_content == {"reason": "not-running", "image": None}
    # Only the image made before the app opened was ever asked of the API.
    assert (len(images_api.requests), cactus.status, len(cactus.versions)) == (1, "done", 1)


async def upload(client: Client, upload_id: str, name: str, content: bytes, piece: int = 4096) -> int:
    received = 0
    for offset in range(0, len(content), piece):
        data = base64.b64encode(content[offset : offset + piece]).decode("ascii")
        sent = await client.call_tool(
            "upload_file", {"upload": upload_id, "name": name, "offset": offset, "data": data}
        )
        received = (sent.structured_content or {})["received"]
    return received


async def test_the_view_guides_a_request_with_uploads_marks_and_the_references_the_app_offers(
    open_app: Callable[..., lib.AppServer],
    images_api: FakeImagesAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(uploads, "UPLOADS", tmp_path / "uploads")
    await made("A paper-cut cactus.", "cactus.png")
    await made("A paper-cut fern.", "fern.png")
    folder = tmp_path / "moodboard"
    folder.mkdir()
    (folder / "palette.png").write_bytes(picture(640, 480, "#ff0000"))
    (folder / "notes.txt").write_text("Not an image.", encoding="utf-8")
    (folder / "swatches").mkdir()
    (folder / "swatches" / "teal.png").write_bytes(picture(48, 32, "#008080"))
    (folder / ".cache").mkdir()
    (folder / ".cache" / "hidden.png").write_bytes(picture(16, 16, "#000000"))
    elsewhere = tmp_path / "elsewhere.png"
    elsewhere.write_bytes(picture(64, 64, "#00ff00"))
    chosen = tmp_path / "chosen.png"
    chosen.write_bytes(picture(32, 32, "#0000ff"))
    app_server = open_app()
    monkeypatch.setattr(app_server, "_choose_files", lambda directory, title, instead: [chosen])
    monkeypatch.setattr(app_server, "_choose_folder", lambda directory, title, instead: folder)
    dropped = picture(800, 600, "#123456")
    mask = Image.new("RGBA", (1024, 1024), (0, 0, 0, 255))
    mask.paste((0, 0, 0, 0), (100, 100, 400, 400))
    painted = BytesIO()
    mask.save(painted, format="PNG")
    edit = {"prompt": "Make it bloom.", "name": "cactus.png"}

    async with Client(f"{app_server.open().url}/mcp") as client:
        listing = ImageListing.model_validate((await client.call_tool("list_images", {})).structured_content)
        fern = next(image for image in listing.images if image.name == "fern.png")
        received = await upload(client, "a" * 32, "dropped.png", dropped)
        await upload(client, "b" * 32, "mask.png", painted.getvalue())
        bad = [
            await client.call_tool("upload_file", {"upload": "nope", "name": "a.png", "offset": 0, "data": ""}),
            await client.call_tool("upload_file", {"upload": "c" * 32, "name": "../a.png", "offset": 0, "data": ""}),
            await client.call_tool("upload_file", {"upload": "a" * 32, "name": "other.png", "offset": 0, "data": ""}),
        ]
        picked_folder = await client.call_tool("choose_reference_folder", {})
        state = (await client.call_tool("read_app_state", {})).structured_content or {}
        kept = ReferenceEntry.model_validate(
            (await client.call_tool("keep_reference", {"upload": "a" * 32})).structured_content
        )
        kept_content = kept.path.read_bytes()
        pinned = {**state, "pins": [str(kept.path)], "folders": [{"path": str(folder), "shows": "files"}]}
        await client.call_tool("save_app_state", {"state": pinned})
        in_folder = await client.call_tool("list_reference_folder", {"path": str(folder)})
        not_pinned = await client.call_tool("list_reference_folder", {"path": str(tmp_path)})
        picked = await client.call_tool("choose_reference_files", {})
        library = ReferenceLibrary.model_validate(
            (await client.call_tool("read_reference_library", {})).structured_content
        )
        references = [
            {"upload": "a" * 32},
            {"path": str(kept.path)},
            {"path": str(folder / "palette.png")},
            {"path": str(chosen)},
            {"path": str(fern.path)},
        ]
        sketch = {"shape": "sketch", "points": [[0.1, 0.1], [0.2, 0.2]], "strokes": [[[0.5, 0.5], [0.6, 0.6]]]}
        marked = await client.call_tool(
            "preview_chatgpt_image_request", {**edit, "references": references[:3], "marks": [sketch]}
        )
        masked = await client.call_tool(
            "preview_openai_image_request", {**edit, "references": references, "mask": "b" * 32}
        )
        outside = await client.call_tool(
            "preview_openai_image_request", {**edit, "references": [{"path": str(elsewhere)}]}
        )
        [small] = (await client.read_resource(f"image-design://references/{quote(str(chosen), safe='')}")).contents
        teal = folder / "swatches" / "teal.png"
        [large] = (await client.read_resource(f"image-design://reference-files/{quote(str(teal), safe='')}")).contents
        with pytest.raises(MCPError) as unread:
            await client.read_resource(f"image-design://references/{quote(str(elsewhere), safe='')}")
        climbed = folder / "swatches" / ".." / ".." / elsewhere.name
        with pytest.raises(MCPError) as climbed_out:
            await client.read_resource(f"image-design://reference-files/{quote(str(climbed), safe='')}")
        await client.call_tool("save_app_state", {"state": {**pinned, "pins": []}})
        unpinned = await client.call_tool("read_reference_library", {})

    assert received == len(dropped)
    assert [each.structured_content for each in bad] == [{"reason": "bad-upload", "image": None}] * 3
    assert picked_folder.structured_content == {"path": str(folder)}
    assert (kept.name, kept.width, kept.height, kept_content) == ("dropped.png", 800, 600, dropped)
    assert kept.path.is_relative_to(Path.cwd() / ".image-design" / ".agents" / "app" / "pins")
    assert in_folder.structured_content == {
        "entries": [
            {"name": "palette.png", "path": str(folder / "palette.png"), "width": 640, "height": 480, "folder": ""},
            {"name": "teal.png", "path": str(teal), "width": 48, "height": 32, "folder": "swatches"},
        ],
        "after": None,
    }
    assert not_pinned.structured_content == {"reason": "missing-folder", "image": None}
    assert [entry["path"] for entry in (picked.structured_content or {})["entries"]] == [str(chosen)]
    assert ([entry.path for entry in library.pinned], library.used) == ([kept.path], [])
    with_marks = ImageRequestPreview.model_validate(marked.structured_content)
    with_mask = ImageRequestPreview.model_validate(masked.structured_content)
    assert [image.role for image in with_marks.images] == [
        "source",
        "marked-copy",
        "reference",
        "reference",
        "reference",
    ]
    assert with_marks.added is not None
    assert with_marks.added.count("Mark ") == 1
    assert [(image.role, image.path) for image in with_mask.images[1:]] == [
        ("reference", tmp_path / "uploads" / ("a" * 32) / "dropped.png"),
        ("reference", kept.path),
        ("reference", folder / "palette.png"),
        ("reference", chosen),
        ("reference", fern.path),
        ("mask", tmp_path / "uploads" / ("b" * 32) / "mask.png"),
    ]
    assert outside.structured_content == {"reason": "not-a-reference", "image": None}
    assert isinstance(small, BlobResourceContents)
    assert small.mime_type == "image/webp"
    assert isinstance(large, BlobResourceContents)
    assert (large.mime_type, base64.b64decode(large.blob)) == ("image/png", teal.read_bytes())
    assert "is not an image the app offers as a reference" in str(unread.value)
    assert "is not an image the app offers as a reference" in str(climbed_out.value)
    assert ReferenceLibrary.model_validate(unpinned.structured_content).pinned == []
    assert not kept.path.exists()
    # Closing the app clears the uploads no request took.
    app_server.close()
    assert not (tmp_path / "uploads" / ("a" * 32)).exists()
    assert len(images_api.requests) == 2


async def test_a_version_given_as_a_reference_is_offered_again_under_its_image_s_name(
    open_app: Callable[..., lib.AppServer], images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    await made("A paper-cut cactus.", "cactus.png")
    await made("Make it bloom.", "cactus.png")
    app_server = open_app()
    runs: list[lib.ImageRun] = []

    # In this process, so the run can be waited on here; a run in a process of its own is the detached tests'.
    async def generate_here(detach: bool, **arguments: Any) -> lib.ImageRun:
        run = await lib.generate_openai_image(**arguments)
        runs.append(run)
        return run

    monkeypatch.setattr(app_server, "_generate", {**app_server._generate, "generate_openai_image": generate_here})

    async with Client(f"{app_server.open().url}/mcp") as client:
        [cactus] = (await listed(client)).images
        first = cactus.versions[0]
        started = await client.call_tool(
            "generate_openai_image",
            {"prompt": "A fern in its style.", "name": "fern.png", "references": [{"path": str(first.file)}]},
        )
        await runs[0].result()
        library = ReferenceLibrary.model_validate(
            (await client.call_tool("read_reference_library", {})).structured_content
        )

    assert (started.structured_content or {})["references"] == [str(first.file)]
    assert [(entry.name, entry.path) for entry in library.used] == [("cactus-v1.png", first.file)]
    assert len(images_api.requests) == 3


@pytest.mark.parametrize(("entries", "visits"), [(2, 1000), (500, 1)])
def test_a_pinned_folder_lists_the_folders_in_it_a_page_at_a_time_and_each_page_goes_on_where_the_last_ended(
    entries: int, visits: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    names = ["b10.png", "b2.png", "A.png", "west/utah/arches.png", "west/canyon.jpg", "east/maine.png"]
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(picture(8, 8, "#336699"))
    (tmp_path / "empty").mkdir()
    monkeypatch.setattr(library_module, "FOLDER_ENTRIES", entries)
    monkeypatch.setattr(library_module, "FOLDER_VISITS", visits)

    pages = [library_module.list_folder(tmp_path)]
    while (after := pages[-1].after) is not None and len(pages) < 20:
        pages.append(library_module.list_folder(tmp_path, after))

    listed = [(entry.folder, entry.name) for page in pages for entry in page.entries]
    assert listed == [
        ("", "A.png"),
        ("", "b2.png"),
        ("", "b10.png"),
        ("east", "maine.png"),
        ("west", "canyon.jpg"),
        ("west/utah", "arches.png"),
    ]
    assert len(pages) > 1
    assert all(len(page.entries) <= entries for page in pages)


async def test_the_view_has_the_key_typed_on_the_machine_and_never_sees_it(
    open_app: Callable[..., lib.AppServer],
    credential_store: MemoryKeyring,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app_server = open_app(tmp_path)
    answers: list[str | None] = [None, "sk-test-typed"]
    monkeypatch.setattr(app_server, "_ask_secret", lambda title, label: answers.pop(0))

    async with Client(f"{app_server.open().url}/mcp") as client:
        results = [
            await client.call_tool("read_openai_key", {}),
            await client.call_tool("enter_openai_key", {}),
            await client.call_tool("enter_openai_key", {"key": "sk-test-argument"}),
            await client.call_tool("list_image_methods", {}),
            await client.call_tool("clear_openai_key", {}),
        ]

    none, cancelled, entered, methods, cleared = (result.structured_content or {} for result in results)
    assert none == {"source": None, "saved": False}
    assert cancelled == {"source": None, "saved": False, "entered": False}
    assert entered == {"source": "saved", "saved": True, "entered": True}
    assert methods["openai"]["ready"] is True
    assert cleared == {"source": None, "saved": False}
    # Neither what was typed nor anything passed as an argument is in any answer.
    assert "sk-test" not in "".join(text_of(result) for result in results)
    assert credential_store.kept == {}


async def test_the_view_draws_steers_and_exports_a_drawing_and_reads_what_its_runs_were_given(
    open_app: Callable[..., lib.AppServer], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    agent = fake_agent(monkeypatch)
    agent.behavior = steered_to("#457b9d")
    monkeypatch.setattr(uploads, "UPLOADS", tmp_path / "uploads")
    app_server = open_app(tmp_path)

    # In this process with the agent faked; a run in a process of its own is the detached tests'.
    async def draw_here(detach: bool, **arguments: Any) -> lib.ImageRun:
        return await lib.draw_svg_image(**arguments, intelligence=agent)

    monkeypatch.setattr(app_server, "_generate", {**app_server._generate, "draw_svg_image": draw_here})
    asked: list[str] = []
    exported = tmp_path / "exports" / "boat.png"

    def save_where(folder: Path, title: str, name: str) -> Path:
        asked.append(name)
        return exported

    monkeypatch.setattr(app_server, "_choose_save_path", save_where)
    circle = {"shape": "circle", "points": [[0.4, 0.1], [0.8, 0.6]], "color": "blue"}

    async def activity(client: Client) -> ImageActivity:
        read = await client.call_tool("read_image_activity", {"name": "sailboat.svg"})
        return ImageActivity.model_validate(read.structured_content)

    async def until(client: Client, kind: str) -> ImageActivity:
        while True:
            read = await activity(client)
            if any(event.kind == kind for event in read.events):
                return read
            await asyncio.sleep(0.02)

    async with Client(f"{app_server.open().url}/mcp") as client:
        await upload(client, "a" * 32, "palette.png", picture(40, 30, "#457b9d"))
        started = await client.call_tool(
            "draw_svg_image",
            {
                "prompt": "A sailboat.",
                "name": "sailboat.svg",
                "references": [{"upload": "a" * 32}],
                "canvas": [64, 48],
                "max_bytes": None,
                "timeout_seconds": None,
                "agent_provider": "claude",
                "reasoning_effort": "high",
            },
        )
        await asyncio.wait_for(until(client, "preview"), TIMEOUT_SECONDS)
        await upload(client, "b" * 32, "sail.png", picture(20, 20, "#e9c46a"))
        misdrawn = await client.call_tool(
            "steer_svg_image", {"name": "sailboat.svg", "message": "Blue.", "marks": [{"shape": "star"}]}
        )
        steered = await client.call_tool(
            "steer_svg_image",
            {
                "name": "sailboat.svg",
                "message": "Make the sail blue.",
                "references": [{"upload": "b" * 32}],
                "marks": [circle],
            },
        )
        history = await asyncio.wait_for(until(client, "finished"), TIMEOUT_SECONDS)
        begun = history.events[0].data
        steering = next(event.data for event in history.events if event.kind == "steered")
        given = [Path(begun["run_folder"], "inputs", "reference-1.png"), Path(steering["references"][0])]
        thumbs = [
            (await client.read_resource(f"image-design://references/{quote(str(path), safe='')}")).contents
            for path in given
        ]
        outside = Path(begun["run_folder"], "..", "..", "..", "..", "..", "elsewhere.png")
        (tmp_path / "elsewhere.png").write_bytes(picture(8, 8, "#000000"))
        with pytest.raises(MCPError):
            await client.read_resource(f"image-design://references/{quote(str(outside), safe='')}")
        late = await client.call_tool("steer_svg_image", {"name": "sailboat.svg", "message": "Too late."})
        written = await client.call_tool("export_svg_image", {"name": "sailboat.svg", "format": ".png", "scale": 2})
        listing = ImageListing.model_validate((await client.call_tool("list_images", {})).structured_content)

    [drawing] = listing.images
    assert (started.structured_content or {})["name"] == "sailboat.svg"
    assert drawing.last_run is not None
    assert (drawing.status, drawing.last_run.origin, drawing.last_run.agent_provider) == ("done", "app", "claude")
    assert (begun["reasoning_effort"], begun["canvas"], begun["max_bytes"]) == ("high", [64, 48], None)
    assert begun["images"] == ["inputs/reference-1.png"]
    assert misdrawn.structured_content == {"reason": "invalid-request", "image": None}
    assert not steered.is_error
    assert (steering["message"], steering["origin"], steering["marks"][0]["color"]) == (
        "Make the sail blue.",
        "app",
        "blue",
    )
    assert all(isinstance(each[0], BlobResourceContents) for each in thumbs)
    assert late.structured_content == {"reason": "not-running", "image": "sailboat.svg"}
    assert (written.structured_content, asked) == ({"path": str(exported)}, ["sailboat.png"])
    assert Image.open(exported).size == (128, 96)
    # The run and the message each copied what they were given, so neither upload is kept.
    assert not (tmp_path / "uploads" / ("a" * 32)).exists()
    assert not (tmp_path / "uploads" / ("b" * 32)).exists()


@pytest.mark.detached
async def test_the_view_starts_a_run_in_a_process_of_its_own_reads_its_previews_and_stops_one(
    open_app: Callable[..., lib.AppServer], images_api: FakeImagesAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_server = open_app()

    async def image(client: Client, running: bool) -> ImageSummary:
        """The image, once its run is going, or once it has ended."""
        while True:
            listing = ImageListing.model_validate((await client.call_tool("list_images", {})).structured_content)
            if listing.images and (listing.images[0].status == "running") == running:
                return listing.images[0]
            await asyncio.sleep(0.05)

    async with Client(f"{app_server.open().url}/mcp") as client:
        monkeypatch.setattr(generate, "BACKGROUND_COMMAND", detached_openai.command("answer"))
        started = await client.call_tool(
            "generate_openai_image",
            {"prompt": "A cactus.", "name": "cactus.png", "size": [1536, 1024], "previews": 2},
        )
        created = await asyncio.wait_for(image(client, running=False), DETACHED_TIMEOUT_SECONDS)
        run_id = (started.structured_content or {})["run_id"]
        history = ImageActivity.model_validate(
            (await client.call_tool("read_image_activity", {"name": "cactus.png"})).structured_content
        )
        [preview] = (await client.read_resource(f"image-design://previews/{run_id}/1/cactus.png")).contents
        refused: list[str] = []
        for uri in (
            f"image-design://previews/{run_id}/2/cactus.png",
            "image-design://previews/another-run/1/cactus.png",
            f"image-design://previews/{run_id}/1/missing.png",
        ):
            with pytest.raises(MCPError) as failure:
                await client.read_resource(uri)
            refused.append(str(failure.value))
        monkeypatch.setattr(generate, "BACKGROUND_COMMAND", detached_openai.command("hang"))
        palette = picture(64, 64, "#ff0000")
        await upload(client, "d" * 32, "palette.png", palette)
        guided = await client.call_tool(
            "generate_openai_image",
            {"prompt": "Make it bloom.", "name": "cactus.png", "references": [{"upload": "d" * 32}]},
        )
        library = ReferenceLibrary.model_validate(
            (await client.call_tool("read_reference_library", {})).structured_content
        )
        [used] = (
            await client.read_resource(f"image-design://references/{quote(str(library.used[0].path), safe='')}")
        ).contents
        busy = await client.call_tool("generate_openai_image", {"prompt": "Make it wilt.", "name": "cactus.png"})
        working = await asyncio.wait_for(image(client, running=True), DETACHED_TIMEOUT_SECONDS)
        stopping = await client.call_tool("cancel_image", {"name": "cactus.png"})
        stopped = await asyncio.wait_for(image(client, running=False), DETACHED_TIMEOUT_SECONDS)

    previews = [event for event in history.events if event.kind == "preview"]
    assert started.structured_content == {
        "name": "cactus.png",
        "run_id": created.last_run and created.last_run.id,
        "references": [],
    }
    assert (created.status, created.width, created.height) == ("done", 1536, 1024)
    assert created.last_run is not None
    assert (created.last_run.origin, created.last_run.pid != os.getpid()) == ("app", True)
    assert [event.data["index"] for event in previews] == [0, 1]
    assert isinstance(preview, BlobResourceContents)
    assert (preview.mime_type, base64.b64decode(preview.blob)) == (
        "image/png",
        Path(previews[1].data["path"]).read_bytes(),
    )
    assert f"Run '{run_id}' on cactus.png has no preview '2'" in refused[0]
    assert "Run 'another-run' on cactus.png has no preview '1'" in refused[1]
    assert "no image named 'missing.png'" in refused[2]
    assert busy.is_error
    # The run copied the upload into its own folder, which is where it is offered from once the upload is cleared.
    assert [(entry.name, entry.path.read_bytes()) for entry in library.used] == [("palette.png", palette)]
    assert library.used[0].path.is_relative_to(Path.cwd() / ".image-design" / ".agents")
    assert (guided.structured_content or {})["references"] == [str(library.used[0].path)]
    assert not (uploads.UPLOADS / ("d" * 32)).exists()
    assert isinstance(used, BlobResourceContents)
    assert working.last_run is not None
    assert working.last_run.prompt == "Make it bloom."
    assert not stopping.is_error
    assert (stopped.status, stopped.current, len(stopped.versions)) == ("cancelled", "v1", 1)
    assert images_api.requests == []


def image_in(workspace: Path, name: str) -> Path:
    """An image file in the workspace's .image-design, which the tool keeps nothing for yet."""
    path = workspace / ".image-design" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(picture(64, 48, "#336699"))
    return path


async def ended(client: Client, name: str) -> ImageSummary:
    """The image named `name` once a run on it has ended, as the app lists it."""
    while True:
        image = next((each for each in (await listed(client)).images if each.name == name), None)
        if image is not None and image.status not in (None, "running"):
            return image
        await asyncio.sleep(0.05)


async def test_with_no_workspace_given_the_app_opens_on_the_last_one_opened_that_is_still_a_folder_or_on_none(
    open_app: Callable[..., lib.AppServer], tmp_path: Path
) -> None:
    first, second, unopened = tmp_path / "first", tmp_path / "second", tmp_path / "unopened"
    for workspace in (first, second, unopened):
        workspace.mkdir()
    before = lib.app_server().workspace
    open_app(first)
    open_app(second)
    # Served, but never opened, so not kept.
    lib.app_server(unopened)
    last = lib.app_server().workspace
    second.rmdir()
    earlier = lib.app_server().workspace
    first.rmdir()
    app_server = lib.app_server()
    try:
        async with Client(f"{app_server.open().url}/mcp") as client:
            workspaces = await client.call_tool("read_app_workspaces", {})
            refused = [
                await client.call_tool("list_images", {}),
                await client.call_tool("read_app_state", {}),
                await client.call_tool("show_in_file_manager", {}),
                await client.call_tool("open_app", {"name": "logo.png"}),
            ]
            settings = await client.call_tool("read_app_settings", {})
            config = await client.call_tool("read_config", {})
            opened = await client.call_tool("open_app", {})
    finally:
        app_server.close()

    assert (before, last, earlier, app_server.workspace) == (None, second, first, None)
    assert AppWorkspaces.model_validate(workspaces.structured_content) == AppWorkspaces(
        current=None,
        recent=[RecentWorkspace(path=second, missing=True), RecentWorkspace(path=first, missing=True)],
        new_in=tmp_path,
    )
    for result in refused:
        assert result.structured_content == {"reason": "no-workspace", "image": None}
    assert "The app shows no workspace yet." in text_of(refused[0])
    assert (settings.is_error, config.is_error) == (False, False)
    assert "It shows no workspace yet" in text_of(opened)


async def test_the_view_switches_workspaces_showing_each_one_s_images_image_shown_tabs_and_pins(
    open_app: Callable[..., lib.AppServer], tmp_path: Path
) -> None:
    garden, harbor, empty = tmp_path / "garden", tmp_path / "harbor", tmp_path / "empty"
    pin = image_in(garden, "cactus.png")
    image_in(harbor, "boat.png")
    image_in(harbor, "gull.png")
    empty.mkdir()
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    app_server = open_app(garden)

    async def state_and_library(client: Client) -> tuple[AppState, ReferenceLibrary]:
        state = AppState.model_validate((await client.call_tool("read_app_state", {})).structured_content)
        library = (await client.call_tool("read_reference_library", {})).structured_content
        return state, ReferenceLibrary.model_validate(library)

    async with Client(f"{app_server.open().url}/mcp") as client:
        await client.call_tool("show_image", {"name": "cactus.png"})
        await client.call_tool("save_app_state", {"state": {"tabs": [{"name": "cactus.png"}], "pins": [str(pin)]}})
        switched = await client.call_tool("open_app_workspace", {"path": str(harbor / ".image-design")})
        await client.call_tool("show_image", {"name": "gull.png"})
        there = await listed(client)
        there_state, there_library = await state_and_library(client)
        refused = await client.call_tool("open_app_workspace", {"path": str(tmp_path / "notes.txt")})
        kept = await listed(client)
        await client.call_tool("open_app_workspace", {"path": str(empty)})
        await client.call_tool("open_app_workspace", {"path": str(garden)})
        back = await listed(client)
        back_state, back_library = await state_and_library(client)

    assert AppWorkspaces.model_validate(switched.structured_content).current == harbor
    assert ([image.name for image in there.images], there.shown) == (["boat.png", "gull.png"], "gull.png")
    assert (there_state.tabs, there_library.pinned) == ([], [])
    assert refused.structured_content == {"reason": "no-such-workspace", "image": None}
    assert kept.workspace == harbor
    assert ([image.name for image in back.images], back.shown) == (["cactus.png"], "cactus.png")
    assert [tab.name for tab in back_state.tabs] == ["cactus.png"]
    assert [entry.path for entry in back_library.pinned] == [pin]
    assert list(empty.iterdir()) == []


async def test_the_workspaces_opened_are_offered_newest_first_each_once_at_most_20_and_forgetting_one_leaves_it(
    open_app: Callable[..., lib.AppServer], tmp_path: Path
) -> None:
    projects = [tmp_path / f"project-{index}" for index in range(22)]
    for project in projects:
        project.mkdir()
    app_server = open_app(projects[0])

    async with Client(f"{app_server.open().url}/mcp") as client:
        for project in projects[1:]:
            await client.call_tool("open_app_workspace", {"path": str(project)})
        # The same folders, spelled another way.
        await client.call_tool("open_app_workspace", {"path": f"{projects[5]}{os.sep}"})
        again = await client.call_tool("open_app_workspace", {"path": str(projects[9] / ".." / projects[9].name)})
        forgotten = await client.call_tool("forget_app_workspace", {"path": str(projects[20])})

    newest = [projects[9], projects[5], *(projects[index] for index in range(21, 1, -1) if index not in (5, 9))]
    offered = AppWorkspaces.model_validate(again.structured_content)
    assert offered.current == projects[9]
    assert [workspace.path for workspace in offered.recent] == newest
    assert not any(workspace.missing for workspace in offered.recent)
    assert [workspace.path for workspace in AppWorkspaces.model_validate(forgotten.structured_content).recent] == [
        project for project in newest if project != projects[20]
    ]
    assert projects[20].is_dir()


async def test_a_workspace_chosen_in_the_folder_dialog_comes_back_by_path_and_a_dialog_that_cannot_show_names_the_command(
    open_app: Callable[..., lib.AppServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    garden, harbor = tmp_path / "garden", tmp_path / "harbor"
    garden.mkdir()
    harbor.mkdir()
    app_server = open_app(garden)
    shown: list[Path] = []
    answers: list[Path | None] = [harbor, None]

    def choose(directory: Path, title: str, instead: str) -> Path | None:
        shown.append(directory)
        return answers.pop(0)

    monkeypatch.setattr(app_server, "_choose_folder", choose)

    async with Client(f"{app_server.open().url}/mcp") as client:
        chosen = await client.call_tool("choose_app_workspace", {})
        cancelled = await client.call_tool("choose_app_workspace", {})
    monkeypatch.setattr(sys, "executable", str(tmp_path / "no-python"))
    async with Client(f"{open_app(garden).open().url}/mcp") as client:
        unshown = await client.call_tool("choose_app_workspace", {})

    assert chosen.structured_content == {"path": str(harbor)}
    assert cancelled.structured_content == {"path": None}
    assert (shown, app_server.workspace) == ([tmp_path, tmp_path], garden)
    assert "Could not show a window to ask in" in text_of(unshown)
    assert "`image-design app --workspace <folder>`" in text_of(unshown)


async def test_a_new_workspace_is_a_folder_made_where_asked_and_opened_and_one_that_cannot_be_is_refused(
    open_app: Callable[..., lib.AppServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects = tmp_path / "projects"
    garden = projects / "garden"
    garden.mkdir(parents=True)
    (projects / "notes.txt").write_text("", encoding="utf-8")
    app_server = open_app(garden)
    shown: list[Path] = []

    def choose(directory: Path, title: str, instead: str) -> Path:
        shown.append(directory)
        return tmp_path / "elsewhere"

    monkeypatch.setattr(app_server, "_choose_folder", choose)

    async with Client(f"{app_server.open().url}/mcp") as client:
        before = AppWorkspaces.model_validate((await client.call_tool("read_app_workspaces", {})).structured_content)
        chosen = await client.call_tool("choose_app_workspace", {"parent": True})
        made = await client.call_tool("create_app_workspace", {"name": " harbor ", "parent": str(before.new_in)})
        refused = [
            await client.call_tool("create_app_workspace", {"name": name, "parent": str(before.new_in)})
            for name in ("garden", "notes.txt", "a/b", "..", "")
        ]
        nowhere = await client.call_tool("create_app_workspace", {"name": "dock", "parent": str(tmp_path / "gone")})

    harbor = projects / "harbor"
    workspaces = AppWorkspaces.model_validate(made.structured_content)
    assert before.new_in == projects
    assert (chosen.structured_content, shown) == ({"path": str(tmp_path / "elsewhere")}, [projects])
    assert (workspaces.current, app_server.workspace) == (harbor, harbor)
    assert [workspace.path for workspace in workspaces.recent] == [harbor, garden]
    assert list(harbor.iterdir()) == []
    assert [result.structured_content for result in refused[:2]] == [{"reason": "name-in-use", "image": None}] * 2
    assert "already exists. Open it with Open Workspace, or choose another name." in text_of(refused[0])
    assert all("is not a folder's name" in text_of(result) for result in refused[2:])
    assert "is not a folder, so no workspace can be made in it" in text_of(nowhere)
    assert sorted(path.name for path in projects.iterdir()) == ["garden", "harbor", "notes.txt"]
    assert not (tmp_path / "gone").exists()


async def test_every_app_offers_the_workspaces_the_others_opened_too(
    open_app: Callable[..., lib.AppServer], tmp_path: Path
) -> None:
    garden, harbor, empty = tmp_path / "garden", tmp_path / "harbor", tmp_path / "empty"
    for workspace in (garden, harbor, empty):
        workspace.mkdir()
    url = open_app(garden).open().url
    open_app(harbor)

    async with Client(f"{url}/mcp") as client:
        switched = await client.call_tool("open_app_workspace", {"path": str(empty)})

    offered = [workspace.path for workspace in AppWorkspaces.model_validate(switched.structured_content).recent]
    assert offered == [empty, harbor, garden]
    assert lib.app_server().workspace == empty


async def test_a_call_for_a_workspace_the_app_no_longer_shows_is_refused_and_changes_nothing(
    open_app: Callable[..., lib.AppServer], tmp_path: Path
) -> None:
    garden, harbor = tmp_path / "garden", tmp_path / "harbor"
    cacti = [image_in(garden, "cactus.png"), image_in(harbor, "cactus.png")]
    app_server = open_app(garden)
    sent = str(app_server.workspace)

    async with Client(f"{app_server.open().url}/mcp") as client:
        before = await client.call_tool("list_images", {"workspace": sent})
        await client.call_tool("open_app_workspace", {"path": str(harbor)})
        refused = [
            await client.call_tool("list_images", {"workspace": sent}),
            await client.call_tool("delete_image", {"name": "cactus.png", "workspace": sent}),
            await client.call_tool("save_app_state", {"state": {"method": "svg"}, "workspace": sent}),
        ]
        settings = await client.call_tool("read_app_settings", {"workspace": sent})
        here = await client.call_tool("list_images", {"workspace": str(harbor)})

    assert not before.is_error, text_of(before)
    for result in refused:
        assert result.structured_content == {"reason": "workspace-changed", "image": None}
        assert f"The app now shows {harbor}, so this call, sent for {sent}, was not made." in text_of(result)
    assert all(cactus.is_file() for cactus in cacti)
    assert not (harbor / ".image-design" / ".agents").exists()
    assert not settings.is_error, text_of(settings)
    assert [image.name for image in AppImages.model_validate(here.structured_content).images] == ["cactus.png"]


async def test_a_workspace_removed_while_the_app_shows_it_is_refused_and_not_made_again(
    open_app: Callable[..., lib.AppServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    garden = tmp_path / "garden"
    garden.mkdir()
    app_server = open_app(garden)
    shown: list[Path] = []
    monkeypatch.setattr(app_server, "_show_in_file_manager", shown.append)
    garden.rmdir()

    async with Client(f"{app_server.open().url}/mcp") as client:
        refused = [
            await client.call_tool("list_images", {}),
            await client.call_tool("save_app_state", {"state": {"method": "svg"}}),
            await client.call_tool("show_in_file_manager", {}),
        ]
        workspaces = AppWorkspaces.model_validate(
            (await client.call_tool("read_app_workspaces", {})).structured_content
        )
        forgotten = await client.call_tool("forget_app_workspace", {"path": str(garden)})

    for result in refused:
        assert result.structured_content == {"reason": "no-such-workspace", "image": None}
    assert f"The workspace {garden} is no longer a folder." in text_of(refused[1])
    assert (garden.exists(), shown) == (False, [])
    assert (workspaces.current, [workspace.missing for workspace in workspaces.recent]) == (None, [True])
    assert AppWorkspaces.model_validate(forgotten.structured_content) == AppWorkspaces(
        current=None, recent=[], new_in=tmp_path
    )


async def test_images_and_a_folder_of_them_chosen_in_the_dialogs_come_in_under_free_names(
    open_app: Callable[..., lib.AppServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    garden = tmp_path / "garden"
    image_in(garden, "palette.png")
    trip = tmp_path / "trip"
    (trip / "day 1").mkdir(parents=True)
    (trip / "palette.png").write_bytes(picture(40, 30, "#ff0000"))
    (trip / "day 1" / "beach.jpg").write_bytes(picture(40, 30, "#00ff00", "jpeg"))
    (trip / "notes.txt").write_text("Not an image.", encoding="utf-8")
    (trip / ".cache").mkdir()
    (trip / ".cache" / "hidden.png").write_bytes(picture(16, 16, "#000000"))
    loose = tmp_path / "palette.png"
    loose.write_bytes(picture(40, 30, "#0000ff"))
    text = tmp_path / "notes.png"
    text.write_text("Not an image.", encoding="utf-8")
    app_server = open_app(garden)
    opened_at: list[Path] = []
    files: list[list[Path]] = [[loose, text], []]

    def choose_folder(directory: Path, title: str, instead: str) -> Path:
        opened_at.append(directory)
        return trip

    def choose_files(directory: Path, title: str, instead: str) -> list[Path]:
        opened_at.append(directory)
        return files.pop(0)

    monkeypatch.setattr(app_server, "_choose_folder", choose_folder)
    monkeypatch.setattr(app_server, "_choose_files", choose_files)

    async with Client(f"{app_server.open().url}/mcp") as client:
        folder = await client.call_tool("choose_image_folder", {})
        chosen = await client.call_tool("choose_image_files", {"folder": "trip/day 1"})
        cancelled = await client.call_tool("choose_image_files", {})
        listing = await listed(client)

    brought = ImageImports.model_validate(folder.structured_content)
    picked = ImageImports.model_validate(chosen.structured_content)
    assert [image.name for image in brought.images] == ["trip/palette.png", "trip/day 1/beach.jpg"]
    assert (brought.folders, brought.refused) == (["trip", "trip/day 1"], [])
    assert [image.name for image in picked.images] == ["trip/day 1/palette.png"]
    assert [(refusal.name, refusal.reason) for refusal in picked.refused] == [("notes.png", "not-an-image")]
    assert cancelled.structured_content == {"images": [], "folders": [], "refused": []}
    # Where a folder was chosen from is where the next dialog opens.
    assert opened_at == [garden / ".image-design", tmp_path, tmp_path]
    assert sorted(image.name for image in listing.images) == [
        "palette.png",
        "trip/day 1/beach.jpg",
        "trip/day 1/palette.png",
        "trip/palette.png",
    ]


def test_the_app_opened_on_an_image_with_no_workspace_to_open_it_in_exits_1_and_names_the_flag() -> None:
    result = CliRunner().invoke(cli_app, ["app", "--name", "logo.png"])

    assert result.exit_code == 1
    assert "Pass --workspace with the project's top-level directory." in str(result.exception)


@pytest.mark.detached
async def test_a_request_sent_just_before_a_switch_makes_its_image_in_the_workspace_it_was_sent_for(
    open_app: Callable[..., lib.AppServer],
    images_api: FakeImagesAPI,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(uploads, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(generate, "BACKGROUND_COMMAND", detached_openai.command("answer"))
    garden, harbor = tmp_path / "garden", tmp_path / "harbor"
    garden.mkdir()
    harbor.mkdir()
    app_server = open_app(garden)
    arrived, switched = threading.Event(), threading.Event()
    start = app_server._generate["generate_openai_image"]

    async def after_the_switch(**arguments: Any) -> Any:
        arrived.set()
        await asyncio.to_thread(switched.wait, DETACHED_TIMEOUT_SECONDS)
        return await start(**arguments)

    monkeypatch.setattr(app_server, "_generate", {**app_server._generate, "generate_openai_image": after_the_switch})
    sent = str(app_server.workspace)
    url = f"{app_server.open().url}/mcp"

    async with Client(url) as client, Client(url) as other:
        await upload(client, "a" * 32, "palette.png", picture(40, 30, "#457b9d"))
        request = asyncio.create_task(
            client.call_tool(
                "generate_openai_image",
                {"prompt": "A cactus.", "name": "cactus.png", "references": [{"upload": "a" * 32}], "workspace": sent},
            )
        )
        await asyncio.to_thread(arrived.wait, DETACHED_TIMEOUT_SECONDS)
        await other.call_tool("open_app_workspace", {"path": str(harbor)})
        switched.set()
        started = await request
        await other.call_tool("open_app_workspace", {"path": sent})
        made = await asyncio.wait_for(ended(client, "cactus.png"), DETACHED_TIMEOUT_SECONDS)

    assert not started.is_error, text_of(started)
    assert (made.path, made.status) == (garden / ".image-design" / "cactus.png", "done")
    # The reference it was given is remembered as used where it was sent for.
    assert (garden / ".image-design" / ".agents" / "app" / "used.json").is_file()
    assert not (harbor / ".image-design").exists()


@pytest.mark.detached
async def test_a_run_goes_on_while_the_app_shows_another_workspace_and_is_there_whole_on_switching_back(
    open_app: Callable[..., lib.AppServer],
    images_api: FakeImagesAPI,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generate, "BACKGROUND_COMMAND", detached_openai.command("answer"))
    garden, harbor = tmp_path / "garden", tmp_path / "harbor"
    garden.mkdir()
    image_in(harbor, "boat.png")
    app_server = open_app(garden)

    async with Client(f"{app_server.open().url}/mcp") as client:
        started = await client.call_tool("generate_openai_image", {"prompt": "A cactus.", "name": "cactus.png"})
        await client.call_tool("open_app_workspace", {"path": str(harbor)})
        away = await listed(client)
        await client.call_tool("open_app_workspace", {"path": str(garden)})
        made = await asyncio.wait_for(ended(client, "cactus.png"), DETACHED_TIMEOUT_SECONDS)
        history = ImageActivity.model_validate(
            (await client.call_tool("read_image_activity", {"name": "cactus.png"})).structured_content
        )

    assert not started.is_error, text_of(started)
    assert [image.name for image in away.images] == ["boat.png"]
    assert (made.status, made.current) == ("done", "v1")
    kinds = [event.kind for event in history.events]
    assert (kinds[0], kinds[-1], "version" in kinds) == ("started", "finished", True)
