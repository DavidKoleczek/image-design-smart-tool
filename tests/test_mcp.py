"""The MCP adapter on the wire, spoken to over stdio the way Claude Code and MCP Apps hosts speak to it."""

from collections.abc import Callable, Iterator
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
from typing import Any

from mcp import Client
from mcp.client.context import ClientRequestContext
from mcp.client.stdio import StdioServerParameters
from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID
from mcp.types import ElicitRequestParams, ElicitRequestURLParams, ElicitResult, TextContent
import pytest

from image_design import lib
from image_design.capabilities.app.tools import VIEW_URI

pytestmark = pytest.mark.mcp_process

TIMEOUT_SECONDS = 10
# What Claude Code 2.1 asks for in `initialize`.
PROTOCOL_VERSION = "2025-11-25"
MCP_APPS_HOST = {"extensions": {EXTENSION_ID: {"mimeTypes": [APP_MIME_TYPE]}}}
VIEW_TOOLS = (
    "list_images",
    "show_image",
    "view_image",
    "move_image",
    "copy_image",
    "import_image",
    "choose_image_files",
    "delete_image",
    "create_folder",
    "move_folder",
    "delete_folder",
    "relink_image",
    "restore_image_version",
    "read_image_activity",
    "list_image_methods",
    "generate_openai_image",
    "generate_chatgpt_image",
    "preview_openai_image_request",
    "preview_chatgpt_image_request",
    "draw_svg_image",
    "steer_svg_image",
    "design_image",
    "steer_image",
    "export_svg_image",
    "cancel_image",
    "upload_file",
    "read_reference_library",
    "list_reference_folder",
    "choose_reference_files",
    "choose_reference_folder",
    "show_in_file_manager",
    "keep_reference",
    "read_openai_key",
    "enter_openai_key",
    "clear_openai_key",
    "read_app_settings",
    "save_app_settings",
    "read_app_state",
    "save_app_state",
)
IMAGE_RESOURCES = (
    "image-design://images/{+name}",
    "image-design://versions/{version}/{+name}",
    "image-design://thumbnails/{version}/{+name}",
    "image-design://frames/{version}/{index}/{+name}",
    "image-design://frame-thumbnails/{version}/{index}/{+name}",
    "image-design://previews/{run}/{index}/{+name}",
    "image-design://references/{+path}",
    "image-design://reference-files/{+path}",
)


class Wire:
    """One `image-design mcp` process, spoken to in newline-delimited JSON-RPC on the initialize handshake."""

    def __init__(self, arguments: list[str] | None = None) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "image_design.cli", "mcp", *(arguments or [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.messages.put(json.loads(line))

    def send(self, message: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def receive(self, matches: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        while True:
            message = self.messages.get(timeout=TIMEOUT_SECONDS)
            if matches(message):
                return message

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        request_id = self.next_id
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return self.receive(lambda message: message.get("id") == request_id and "method" not in message)["result"]

    def initialize(self, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": capabilities or {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> int:
        assert self.process.stdin is not None
        self.process.stdin.close()
        return self.process.wait(timeout=TIMEOUT_SECONDS)


@pytest.fixture
def wire() -> Iterator[Wire]:
    server = Wire()
    yield server
    if server.process.poll() is None:
        server.process.kill()


def text_of(result: dict[str, Any]) -> str:
    return "\n".join(block["text"] for block in result["content"])


def test_a_client_without_mcp_apps_gets_open_app_and_a_url_and_the_server_exits_when_left(wire: Wire) -> None:
    initialized = wire.initialize()
    tools = {tool["name"]: tool for tool in wire.request("tools/list", {})["tools"]}
    resources = wire.request("resources/list", {})["resources"]
    templates = wire.request("resources/templates/list", {})["resourceTemplates"]
    opened = text_of(wire.call_tool("open_app", {}))
    unknown = wire.call_tool("draw", {})

    assert set(tools) == {"open_app"}
    assert tools["open_app"]["_meta"] == {"ui": {"resourceUri": VIEW_URI}}
    assert "open_app" in initialized["instructions"]
    assert (resources, templates) == ([], [])
    assert "Give the user this URL to open the app: http://127.0.0.1:" in opened
    assert unknown["isError"]
    assert "'draw' is not a tool of this server" in text_of(unknown)
    assert wire.close() == 0


def test_an_mcp_apps_host_gets_the_view_and_the_tools_it_calls_and_is_told_it_shows_inline(wire: Wire) -> None:
    wire.initialize(MCP_APPS_HOST)
    tools = {tool["name"]: tool for tool in wire.request("tools/list", {})["tools"]}
    resources = wire.request("resources/list", {})["resources"]
    templates = wire.request("resources/templates/list", {})["resourceTemplates"]
    contents = wire.request("resources/read", {"uri": VIEW_URI})["contents"]
    opened = text_of(wire.call_tool("open_app", {}))

    assert set(tools) == {"open_app", *VIEW_TOOLS}
    assert all(tools[name]["_meta"]["ui"]["visibility"] == ["app"] for name in VIEW_TOOLS)
    assert [resource["uri"] for resource in resources] == [VIEW_URI]
    assert tuple(template["uriTemplate"] for template in templates) == IMAGE_RESOURCES
    assert contents == [{"uri": VIEW_URI, "mimeType": APP_MIME_TYPE, "text": lib.app_view()}]
    assert "shown to the user inline" in opened


def test_the_app_shows_the_directory_it_was_started_on_until_open_app_names_another(tmp_path: Path) -> None:
    wire = Wire(arguments=["--directory", str(tmp_path / "first"), "--data-directory", str(tmp_path / "data")])
    try:
        wire.initialize(MCP_APPS_HOST)
        started = wire.call_tool("list_images", {})["structuredContent"]
        opened = text_of(wire.call_tool("open_app", {"directory": str(tmp_path / "second")}))
        switched = wire.call_tool("list_images", {})["structuredContent"]
    finally:
        exit_code = wire.close()

    assert exit_code == 0
    assert (started["directory"], started["data_directory"]) == (str(tmp_path / "first"), str(tmp_path / "data"))
    assert f"It shows the images in {tmp_path / 'second'}." in opened
    assert (switched["directory"], switched["data_directory"]) == (
        str(tmp_path / "second"),
        str(tmp_path / "second" / ".agents"),
    )


# "auto" lands on 2026-07-28, where the question rides back on the result and the client retries; "legacy" is the
# initialize handshake, where the server asks mid-call. Claude Code speaks the first.
@pytest.mark.parametrize(("mode", "era"), [("auto", "2026-07-28"), ("legacy", PROTOCOL_VERSION)])
async def test_open_app_asks_the_client_to_open_it_in_the_browser_once(mode: str, era: str) -> None:
    asked: list[ElicitRequestURLParams] = []

    async def open_it(context: ClientRequestContext, params: ElicitRequestParams) -> ElicitResult:
        assert isinstance(params, ElicitRequestURLParams)
        asked.append(params)
        return ElicitResult(action="accept")

    server = StdioServerParameters(command=sys.executable, args=["-m", "image_design.cli", "mcp"])
    async with Client(server, mode=mode, elicitation_callback=open_it) as client:
        opened = (await client.call_tool("open_app", {})).content[0]
        again = (await client.call_tool("open_app", {})).content[0]
        negotiated = client.protocol_version

    assert negotiated == era
    assert isinstance(opened, TextContent)
    assert isinstance(again, TextContent)
    assert len(asked) == 1
    assert f"The user opened the app at {asked[0].url}." in opened.text
    assert f"Give the user this URL to open the app: {asked[0].url}" in again.text
