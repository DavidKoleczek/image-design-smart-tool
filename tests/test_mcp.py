"""The MCP adapter on the wire, spoken to over stdio the way Claude Code and MCP Apps hosts speak to it."""

from collections.abc import Callable, Iterator
import json
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


class Wire:
    """One `image-design mcp` process, spoken to in newline-delimited JSON-RPC on the initialize handshake."""

    def __init__(self) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "image_design.cli", "mcp"],
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
    opened = text_of(wire.call_tool("open_app", {}))
    unknown = wire.call_tool("draw", {})

    assert set(tools) == {"open_app"}
    assert tools["open_app"]["_meta"] == {"ui": {"resourceUri": VIEW_URI}}
    assert "open_app" in initialized["instructions"]
    assert resources == []
    assert "Give the user this URL to open the app: http://127.0.0.1:" in opened
    assert unknown["isError"]
    assert "'draw' is not a tool of this server" in text_of(unknown)
    assert wire.close() == 0


def test_an_mcp_apps_host_gets_the_view_and_is_told_it_shows_inline(wire: Wire) -> None:
    wire.initialize(MCP_APPS_HOST)
    resources = wire.request("resources/list", {})["resources"]
    contents = wire.request("resources/read", {"uri": VIEW_URI})["contents"]
    opened = text_of(wire.call_tool("open_app", {}))

    assert [resource["uri"] for resource in resources] == [VIEW_URI]
    assert contents == [{"uri": VIEW_URI, "mimeType": APP_MIME_TYPE, "text": lib.app_view()}]
    assert "shown to the user inline" in opened


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
    assert opened.text == f"The user opened the app at {asked[0].url}."
    assert again.text == f"Give the user this URL to open the app: {asked[0].url}"
