import asyncio
import base64
from collections.abc import Callable, Iterator
from io import BytesIO
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import detached_openai
from fake_openai import FakeImagesAPI, picture
from mcp import Client, MCPError
from mcp.types import BlobResourceContents, TextContent, TextResourceContents
from PIL import Image
import pytest

from image_design import lib
from image_design.capabilities.app import server as server_module
from image_design.capabilities.app.tools import VIEW_URI
from image_design.capabilities.openai_image import generate
from image_design.schemas import (
    AppImageRequest,
    AppLayout,
    AppSettings,
    AppState,
    ImageActivity,
    ImageDesignError,
    ImageListing,
    ImageMethods,
    ImageRequestPreview,
    ImageSummary,
    PaneLayout,
)

TIMEOUT_SECONDS = 5
# A detached run starts a Python process of its own, which takes a while to import the library.
DETACHED_TIMEOUT_SECONDS = 30


@pytest.fixture
def open_app() -> Iterator[Callable[..., lib.AppServer]]:
    opened: list[lib.AppServer] = []

    def open_with(directory: Path | None = None, data_directory: Path | None = None) -> lib.AppServer:
        app_server = lib.app_server(directory, data_directory)
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


async def test_the_view_lists_the_images_of_the_app_s_directory_until_open_app_names_another(
    open_app: Callable[..., lib.AppServer], tmp_path: Path
) -> None:
    (tmp_path / "first").mkdir()
    (tmp_path / "first" / "photo.png").write_bytes(picture(800, 600, "#336699"))
    (tmp_path / "file").write_text("", encoding="utf-8")
    app_server = open_app(directory=tmp_path / "first")

    async with Client(f"{app_server.open().url}/mcp") as client:
        started = await client.call_tool("list_images", {})
        opened = await client.call_tool("open_app", {"directory": str(tmp_path / "second")})
        switched = await client.call_tool("list_images", {})
        refused = await client.call_tool("open_app", {"directory": str(tmp_path / "file")})
        kept = await client.call_tool("list_images", {})
        await client.call_tool("open_app", {"data_directory": str(tmp_path / "data")})
        elsewhere = await client.call_tool("list_images", {})
        unknown = await client.call_tool("draw", {})

    first = ImageListing.model_validate(started.structured_content)
    second = ImageListing.model_validate(switched.structured_content)
    assert (first.directory, first.data_directory) == (tmp_path / "first", tmp_path / "first" / ".agents")
    assert [(image.name, image.width, image.height) for image in first.images] == [("photo.png", 800, 600)]
    assert f"It shows the images in {tmp_path / 'second'}." in text_of(opened)
    assert (second.directory, second.data_directory, second.images) == (
        tmp_path / "second",
        tmp_path / "second" / ".agents",
        [],
    )
    assert refused.is_error
    assert "is a file, not a directory of images" in text_of(refused)
    assert ImageListing.model_validate(kept.structured_content) == second
    assert ImageListing.model_validate(elsewhere.structured_content).data_directory == tmp_path / "data"
    assert app_server.directory == tmp_path / "second"
    assert unknown.structured_content == {"reason": "no-such-tool", "image": None}
    assert "The tools are: open_app, list_images, " in text_of(unknown)


async def test_the_view_keeps_the_person_s_settings_in_their_config_directory_for_every_directory(
    open_app: Callable[..., lib.AppServer], tmp_path: Path, config_directory: Path
) -> None:
    logos = open_app(directory=tmp_path / "logos")
    photos = open_app(directory=tmp_path / "photos")
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
    assert not list(tmp_path.rglob("app-settings.json"))


async def test_what_was_picked_in_the_app_is_kept_with_each_directory_s_data(
    open_app: Callable[..., lib.AppServer], tmp_path: Path, config_directory: Path
) -> None:
    app_server = open_app(directory=tmp_path / "logos")
    kept = tmp_path / "logos" / ".agents" / "app" / "app.json"

    async with Client(f"{app_server.open().url}/mcp") as client:
        before = await client.call_tool("read_app_state", {})
        read_only = not (tmp_path / "logos").exists()
        saved = await client.call_tool("save_app_state", {"state": {"method": "svg"}})
        picked = AppImageRequest(model="chatgpt", size=(1536, 1024), format=".webp", count=2, reasoning_effort="high")
        request = await client.call_tool("save_app_state", {"state": {"request": picked.model_dump(mode="json")}})
        await client.call_tool("save_app_state", {"state": {"method": "svg"}})
        bad = await client.call_tool("save_app_state", {"state": {"method": "paint"}})
        await client.call_tool("open_app", {"directory": str(tmp_path / "photos")})
        elsewhere = await client.call_tool("read_app_state", {})
        await client.call_tool("open_app", {"directory": str(tmp_path / "logos")})
        back = await client.call_tool("read_app_state", {})

    assert (AppState.model_validate(before.structured_content), read_only) == (AppState(), True)
    assert AppState.model_validate(saved.structured_content) == AppState(method="svg")
    assert AppState.model_validate(request.structured_content) == AppState(request=picked)
    assert AppState.model_validate_json(kept.read_text(encoding="utf-8")) == AppState(method="svg")
    # The data directory's .gitignore comes with it, so what the app keeps there stays out of a project's commits.
    assert (tmp_path / "logos" / ".agents" / ".gitignore").is_file()
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
    app_server = open_app()

    async with Client(f"{app_server.open().url}/mcp") as client:
        viewed = await client.call_tool("view_image", {"name": "cactus.png"})
        listed = await client.call_tool("list_images", {})
        restored = await client.call_tool("restore_image_version", {"name": "cactus.png", "version": "v1"})
        history = await client.call_tool("read_image_activity", {"name": "cactus.png"})
        cursor = (history.structured_content or {})["cursor"]
        since = await client.call_tool("read_image_activity", {"name": "cactus.png", "after": cursor})
        converted = await client.call_tool("move_image", {"name": "cactus.png", "new_name": "cactus.jpg"})
        moved = await client.call_tool("move_image", {"name": "cactus.png", "new_name": "plants/cactus.png"})
        deleted = await client.call_tool("delete_image", {"name": "plants/cactus.png"})
        gone = await client.call_tool("view_image", {"name": "plants/cactus.png"})
        emptied = await client.call_tool("list_images", {})

    activity = ImageActivity.model_validate(history.structured_content)
    assert ImageSummary.model_validate(viewed.structured_content).current == "v2"
    assert ImageListing.model_validate(listed.structured_content).last_viewed == "cactus.png"
    assert ImageSummary.model_validate(restored.structured_content).current == "v1"
    assert [event.data["prompt"] for event in activity.events if event.kind == "started"] == [
        "A paper-cut cactus.",
        "Make it bloom.",
    ]
    assert ImageActivity.model_validate(since.structured_content).events == []
    assert converted.structured_content == {"reason": "invalid-name", "image": "cactus.png"}
    summary = ImageSummary.model_validate(moved.structured_content)
    assert (summary.name, [version.id for version in summary.versions]) == ("plants/cactus.png", ["v1", "v2"])
    assert not deleted.is_error
    assert gone.structured_content == {"reason": "no-such-image", "image": "plants/cactus.png"}
    assert ImageListing.model_validate(emptied.structured_content).images == []


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
        await client.call_tool("generate_openai_image", {"prompt": "Make it bloom.", "name": "cactus.png"})
        busy = await client.call_tool("generate_openai_image", {"prompt": "Make it wilt.", "name": "cactus.png"})
        working = await asyncio.wait_for(image(client, running=True), DETACHED_TIMEOUT_SECONDS)
        stopping = await client.call_tool("cancel_image", {"name": "cactus.png"})
        stopped = await asyncio.wait_for(image(client, running=False), DETACHED_TIMEOUT_SECONDS)

    previews = [event for event in history.events if event.kind == "preview"]
    assert started.structured_content == {"name": "cactus.png", "run_id": created.last_run and created.last_run.id}
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
    assert working.last_run is not None
    assert working.last_run.prompt == "Make it bloom."
    assert not stopping.is_error
    assert (stopped.status, stopped.current, len(stopped.versions)) == ("cancelled", "v1", 1)
    assert images_api.requests == []
