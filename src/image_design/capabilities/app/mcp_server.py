"""The app's MCP server: the tool that opens the app, and the view as an MCP App resource."""

import asyncio
import threading
from typing import Any
import uuid

from mcp import MCPError
from mcp.server import Server, ServerRequestContext
from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID, client_supports_apps
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ElicitRequest,
    ElicitRequestURLParams,
    ElicitResult,
    InputRequiredResult,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    TextContent,
    TextResourceContents,
)

from image_design.capabilities.app.server import App, serve_app, view
from image_design.capabilities.app.tools import OPEN_APP, VIEW, VIEW_URI
from image_design.schemas import ImageDesignError

# The key `open_app` files its request to open the browser under, when the client answers by retrying the call.
OPEN_REQUEST = "open"
INSTRUCTIONS = "Image Design has an app the user can open. Call `open_app` when they ask for it."


class AppServer:
    """The app's MCP server, and the browser host page once it is open.

    Serve `server` over any MCP transport. Several at once share this state, so the browser host page reaches the
    same server the agent's session does.
    """

    def __init__(self, server_name: str, version: str) -> None:
        self._lock = threading.Lock()
        self._app: App | None = None
        # Whether the client was asked to open the app in the browser, so it is asked once a session.
        self._offered = False
        self.server = Server(
            server_name,
            version=version,
            instructions=INSTRUCTIONS,
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool_or_explain,
            on_list_resources=self._list_resources,
            on_read_resource=self._read_resource,
        )
        self.server.extensions[EXTENSION_ID] = {}

    def open(self, port: int | None = None) -> App:
        """Serve the browser host page, unless it already is, and return it."""
        with self._lock:
            if self._app is None:
                self._app = serve_app(self.server, port)
            return self._app

    def close(self) -> None:
        """Stop serving the browser host page, if it was opened."""
        with self._lock:
            if self._app is not None:
                self._app.stop()
                self._app = None

    async def _list_tools(
        self, ctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=[OPEN_APP])

    async def _list_resources(
        self, ctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListResourcesResult:
        return ListResourcesResult(resources=[VIEW] if client_supports_apps(ctx) else [])

    async def _read_resource(
        self, ctx: ServerRequestContext[Any], params: ReadResourceRequestParams
    ) -> ReadResourceResult:
        if params.uri != VIEW_URI:
            raise MCPError(INVALID_PARAMS, f"'{params.uri}' is not a resource of this server. It has {VIEW_URI}.")
        try:
            html = view()
        except ImageDesignError as error:
            raise MCPError(INVALID_PARAMS, str(error)) from None
        return ReadResourceResult(contents=[TextResourceContents(uri=VIEW_URI, mime_type=APP_MIME_TYPE, text=html)])

    async def _call_tool_or_explain(
        self, ctx: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult | InputRequiredResult:
        # A low-level handler's exception is a protocol error the model never reads, so a named failure is a result.
        try:
            return await self._call_tool(ctx, params)
        except ImageDesignError as error:
            # Which failure it was rides along, so the view can word it for the person rather than showing the
            # message, which names commands and arguments for an agent.
            return CallToolResult(
                content=[TextContent(type="text", text=str(error))],
                structured_content={"reason": error.reason, "image": error.image},
                is_error=True,
            )

    async def _call_tool(
        self, ctx: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult | InputRequiredResult:
        if params.name == OPEN_APP.name:
            return await self._open_app(ctx, params)
        raise ImageDesignError(
            f"'{params.name}' is not a tool of this server. The tools are: {OPEN_APP.name}.", "no-such-tool"
        )

    async def _open_app(
        self, ctx: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult | InputRequiredResult:
        app = await asyncio.to_thread(self.open)
        embedded = client_supports_apps(ctx)
        answer = (params.input_responses or {}).get(OPEN_REQUEST)
        opened = isinstance(answer, ElicitResult) and answer.action == "accept"
        if not embedded and not self._offered and _takes_url_elicitation(ctx):
            self._offered = True
            message = "Open the Image Design app."
            elicitation_id = str(uuid.uuid4())
            # Before 2026-07-28 the server asks mid-call; from it on, the server returns the question and the client
            # retries the call with the answer.
            if not ctx.session.can_send_request:
                request = ElicitRequestURLParams(message=message, url=app.url, elicitation_id=elicitation_id)
                return InputRequiredResult(input_requests={OPEN_REQUEST: ElicitRequest(params=request)})
            try:
                response = await ctx.session.elicit_url(message, app.url, elicitation_id)
            except MCPError:
                response = None
            opened = response is not None and response.action == "accept"
        if embedded:
            where = f"The app is shown to the user inline, and at {app.url} for a browser."
        elif opened:
            where = f"The user opened the app at {app.url}."
        else:
            where = f"Give the user this URL to open the app: {app.url}"
        return CallToolResult(content=[TextContent(type="text", text=where)])


def _takes_url_elicitation(ctx: ServerRequestContext[Any]) -> bool:
    capabilities = ctx.session.client_capabilities
    return (
        capabilities is not None and capabilities.elicitation is not None and capabilities.elicitation.url is not None
    )
