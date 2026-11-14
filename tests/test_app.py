from collections.abc import Callable, Iterator
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mcp import Client
from mcp.types import TextResourceContents
import pytest

from image_design import lib
from image_design.capabilities.app import server as server_module
from image_design.capabilities.app.tools import VIEW_URI
from image_design.schemas import ImageDesignError

TIMEOUT_SECONDS = 5


@pytest.fixture
def open_app() -> Iterator[Callable[[], lib.AppServer]]:
    opened: list[lib.AppServer] = []

    def open_one() -> lib.AppServer:
        app_server = lib.app_server()
        app_server.open()
        opened.append(app_server)
        return app_server

    yield open_one
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


def test_the_host_page_points_at_a_sandbox_on_another_origin_and_only_its_own_pages_reach_mcp(
    open_app: Callable[[], lib.AppServer],
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
    open_app: Callable[[], lib.AppServer],
) -> None:
    app_server = open_app()

    async with Client(f"{app_server.open().url}/mcp") as client:
        view = (await client.read_resource(VIEW_URI)).contents[0]
        tools = (await client.list_tools()).tools

    assert isinstance(view, TextResourceContents)
    assert view.text == lib.app_view()
    assert [tool.name for tool in tools] == ["open_app"]


def test_opening_the_app_again_returns_the_same_page(open_app: Callable[[], lib.AppServer]) -> None:
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
