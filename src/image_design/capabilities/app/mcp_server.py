"""The app's MCP server: the tool that opens the app, the tools its view calls, and the view as an MCP App resource."""

import asyncio
from collections.abc import Callable
import json
from pathlib import Path
import threading
from typing import Any
import uuid

from mcp import MCPError
from mcp.server import Server, ServerRequestContext
from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID, client_supports_apps
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    BlobResourceContents,
    CallToolResult,
    ElicitRequest,
    ElicitRequestURLParams,
    ElicitResult,
    InputRequiredResult,
    ListResourcesResult,
    ListResourceTemplatesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    TextContent,
    TextResourceContents,
)

from image_design.capabilities.app.resources import is_image_resource, read_image_resource
from image_design.capabilities.app.server import App, serve_app, view
from image_design.capabilities.app.settings import (
    read_app_settings,
    read_app_state,
    save_app_settings,
    save_app_state,
)
from image_design.capabilities.app.tools import (
    DELETE_IMAGE,
    IMAGE_FILE,
    IMAGE_RESOURCES,
    IMAGE_THUMBNAIL,
    IMAGE_VERSION,
    LIST_IMAGES,
    MOVE_IMAGE,
    OPEN_APP,
    READ_ACTIVITY,
    READ_SETTINGS,
    READ_STATE,
    RESTORE_VERSION,
    SAVE_SETTINGS,
    SAVE_STATE,
    VIEW,
    VIEW_IMAGE,
    VIEW_TOOLS,
    VIEW_URI,
)
from image_design.schemas import ImageActivity, ImageDesignError, ImageListing, ImageSummary
from image_design.shared.images.store import directories

# The key `open_app` files its request to open the browser under, when the client answers by retrying the call.
OPEN_REQUEST = "open"
INSTRUCTIONS = (
    "Image Design has an app where the user sees the images in one directory. Call `open_app` when they ask for it."
)


class AppServer:
    """The app's MCP server, and the browser host page once it is open.

    Serve `server` over any MCP transport. Several at once share this state, so the browser host page reaches the
    same server the agent's session does. The capabilities the view calls are passed in, so this stays a surface.
    """

    def __init__(
        self,
        server_name: str,
        version: str,
        directory: Path | None,
        data_directory: Path | None,
        list_images: Callable[[Path, Path], ImageListing],
        view_image: Callable[[str, Path, Path], ImageSummary],
        move_image: Callable[[str, str, Path, Path], ImageSummary],
        delete_image: Callable[[str, Path, Path], None],
        restore_image_version: Callable[[str, str, Path, Path], ImageSummary],
        read_image_activity: Callable[[str, Path, Path, str | None], ImageActivity],
        settings_path: Path,
    ) -> None:
        self.directory, self.data_directory = directories(directory, data_directory)
        self.settings_path = settings_path
        self._list_images = list_images
        self._view_image = view_image
        self._move_image = move_image
        self._delete_image = delete_image
        self._restore_image_version = restore_image_version
        self._read_image_activity = read_image_activity
        # The last listing the view was given, which the files it then reads are checked against.
        self._listing: ImageListing | None = None
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
            on_list_resource_templates=self._list_resource_templates,
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
        # Tools only the view calls stay hidden from clients that would show them to the model.
        return ListToolsResult(tools=[OPEN_APP, *VIEW_TOOLS] if client_supports_apps(ctx) else [OPEN_APP])

    async def _list_resources(
        self, ctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListResourcesResult:
        return ListResourcesResult(resources=[VIEW] if client_supports_apps(ctx) else [])

    async def _list_resource_templates(
        self, ctx: ServerRequestContext[Any], params: PaginatedRequestParams | None
    ) -> ListResourceTemplatesResult:
        templates = IMAGE_RESOURCES if client_supports_apps(ctx) else []
        return ListResourceTemplatesResult(resource_templates=templates)

    async def _read_resource(
        self, ctx: ServerRequestContext[Any], params: ReadResourceRequestParams
    ) -> ReadResourceResult:
        try:
            if params.uri == VIEW_URI:
                contents = TextResourceContents(uri=VIEW_URI, mime_type=APP_MIME_TYPE, text=view())
                return ReadResourceResult(contents=[contents])
            if is_image_resource(params.uri):
                return ReadResourceResult(contents=[await asyncio.to_thread(self._image_resource, params.uri)])
        except ImageDesignError as error:
            raise MCPError(INVALID_PARAMS, str(error)) from None
        raise MCPError(
            INVALID_PARAMS,
            f"'{params.uri}' is not a resource of this server. It has {VIEW_URI}, each image's file at "
            f"{IMAGE_FILE.uri_template}, its versions at {IMAGE_VERSION.uri_template}, and small copies of them at "
            f"{IMAGE_THUMBNAIL.uri_template}.",
        )

    def _image_resource(self, uri: str) -> BlobResourceContents:
        if self._listing is not None:
            try:
                return read_image_resource(uri, self._listing)
            except ImageDesignError:
                # The image or version may be newer than that listing.
                pass
        return read_image_resource(uri, self._list())

    def _list(self) -> ImageListing:
        directory = self.directory
        listing = self._list_images(directory, self.data_directory)
        # A listing that took long enough for `open_app` to switch directory is not the one to read files by.
        self._listing = listing if directory == self.directory else None
        return listing

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
        arguments = params.arguments or {}
        if params.name == OPEN_APP.name:
            return await self._open_app(ctx, params)
        if params.name == LIST_IMAGES.name:
            listing = await asyncio.to_thread(self._list)
            return _structured(listing.model_dump(mode="json"))
        if params.name == VIEW_IMAGE.name:
            image = await asyncio.to_thread(self._view_image, arguments["name"], self.directory, self.data_directory)
            return _structured(image.model_dump(mode="json"))
        if params.name == MOVE_IMAGE.name:
            image = await asyncio.to_thread(
                self._move_image, arguments["name"], arguments["new_name"], self.directory, self.data_directory
            )
            self._listing = None
            return _structured(image.model_dump(mode="json"))
        if params.name == DELETE_IMAGE.name:
            await asyncio.to_thread(self._delete_image, arguments["name"], self.directory, self.data_directory)
            self._listing = None
            return _text(f"Deleted {arguments['name']}.")
        if params.name == RESTORE_VERSION.name:
            image = await asyncio.to_thread(
                self._restore_image_version,
                arguments["name"],
                arguments["version"],
                self.directory,
                self.data_directory,
            )
            return _structured(image.model_dump(mode="json"))
        if params.name == READ_ACTIVITY.name:
            activity = await asyncio.to_thread(
                self._read_image_activity,
                arguments["name"],
                self.directory,
                self.data_directory,
                arguments.get("after"),
            )
            return _structured(activity.model_dump(mode="json"))
        if params.name == READ_SETTINGS.name:
            settings = await asyncio.to_thread(read_app_settings, self.settings_path)
            return _structured(settings.model_dump(mode="json"))
        if params.name == SAVE_SETTINGS.name:
            settings = await asyncio.to_thread(save_app_settings, arguments["settings"], self.settings_path)
            return _structured(settings.model_dump(mode="json"))
        if params.name == READ_STATE.name:
            state = await asyncio.to_thread(read_app_state, self.data_directory)
            return _structured(state.model_dump(mode="json"))
        if params.name == SAVE_STATE.name:
            state = await asyncio.to_thread(save_app_state, arguments["state"], self.data_directory)
            return _structured(state.model_dump(mode="json"))
        known = ", ".join(tool.name for tool in [OPEN_APP, *VIEW_TOOLS])
        raise ImageDesignError(f"'{params.name}' is not a tool of this server. The tools are: {known}.", "no-such-tool")

    async def _open_app(
        self, ctx: ServerRequestContext[Any], params: CallToolRequestParams
    ) -> CallToolResult | InputRequiredResult:
        arguments = params.arguments or {}
        directory = arguments.get("directory")
        data_directory = arguments.get("data_directory")
        if directory is not None or data_directory is not None:
            root, data = directories(
                Path(directory) if directory is not None else self.directory,
                Path(data_directory) if data_directory is not None else None,
            )
            # Listed first, so a path the app cannot show is refused before the app switches to it.
            await asyncio.to_thread(self._list_images, root, data)
            self.directory, self.data_directory = root, data
            self._listing = None
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
        return _text(f"{where} It shows the images in {self.directory}.")


def _text(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _structured(structured: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(structured))], structured_content=structured
    )


def _takes_url_elicitation(ctx: ServerRequestContext[Any]) -> bool:
    capabilities = ctx.session.client_capabilities
    return (
        capabilities is not None and capabilities.elicitation is not None and capabilities.elicitation.url is not None
    )
