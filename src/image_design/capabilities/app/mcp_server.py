"""The app's MCP server: the tool that opens the app, the tools its view calls, and the view as an MCP App resource."""

import asyncio
from collections.abc import Awaitable, Callable
import hashlib
import json
from pathlib import Path, PurePosixPath
import threading
import time
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
    Tool,
)
from pydantic import ValidationError

from image_design.capabilities.app import library, uploads
from image_design.capabilities.app.resources import (
    IMAGE_TYPES,
    is_frame_resource,
    is_image_resource,
    is_preview_resource,
    is_reference_resource,
    read_frame_resource,
    read_image_resource,
    read_preview_resource,
    read_reference_resource,
    reference_path,
)
from image_design.capabilities.app.server import App, serve_app, view
from image_design.capabilities.app.settings import (
    follow_move,
    read_app_settings,
    read_app_state,
    save_app_settings,
    save_app_state,
    show_image,
)
from image_design.capabilities.app.tools import (
    CANCEL_IMAGE,
    CHOOSE_FILES,
    CHOOSE_FOLDER,
    CHOOSE_IMAGES,
    CLEAR_OPENAI_KEY,
    COPY_IMAGE,
    CREATE_FOLDER,
    DELETE_FOLDER,
    DELETE_IMAGE,
    DRAW_SVG,
    ENTER_OPENAI_KEY,
    EXPORT_SVG,
    FRAME_THUMBNAIL,
    GENERATE_CHATGPT,
    GENERATE_OPENAI,
    IMAGE_FILE,
    IMAGE_FRAME,
    IMAGE_RESOURCES,
    IMAGE_THUMBNAIL,
    IMAGE_VERSION,
    IMPORT_IMAGE,
    KEEP_REFERENCE,
    LIST_FOLDER,
    LIST_IMAGES,
    LIST_METHODS,
    MOVE_FOLDER,
    MOVE_IMAGE,
    OPEN_APP,
    PREVIEW_CHATGPT,
    PREVIEW_OPENAI,
    READ_ACTIVITY,
    READ_LIBRARY,
    READ_OPENAI_KEY,
    READ_SETTINGS,
    READ_STATE,
    REFERENCE,
    REFERENCE_FILE,
    RELINK_IMAGE,
    RESTORE_VERSION,
    RUN_PREVIEW,
    SAVE_SETTINGS,
    SAVE_STATE,
    SHOW_IMAGE,
    STEER_SVG,
    UPLOAD_FILE,
    VIEW,
    VIEW_IMAGE,
    VIEW_TOOLS,
    VIEW_URI,
)
from image_design.schemas import (
    AppImages,
    ImageActivity,
    ImageDesignError,
    ImageListing,
    ImageMethods,
    ImageMove,
    ImageRelinking,
    ImageRequestPreview,
    ImageSummary,
    ImageView,
    Mark,
    OpenAIKeyStatus,
    ReferenceEntry,
    ReferenceFolderPage,
    UsedReference,
)
from image_design.shared.images import pictures
from image_design.shared.images.runs import ImageRun
from image_design.shared.images.store import IMAGES, directories

# The key `open_app` files its request to open the browser under, when the client answers by retrying the call.
OPEN_REQUEST = "open"
# What a run the view starts is recorded as asked by.
ORIGIN = "app"
CHOOSE_FILES_TITLE = "Choose reference images"
CHOOSE_FOLDER_TITLE = "Choose a folder to pin"
CHOOSE_IMAGES_TITLE = "Choose images to add"
EXPORT_TITLE = "Export the drawing"
ENTER_KEY_TITLE = "Image Design: OpenAI API key"
ENTER_KEY_LABEL = "Paste your OpenAI API key. It is saved in this computer's credential store."
# The tools whose arguments are a request to a library function, by their names.
REQUEST_TOOLS = {tool.name: tool for tool in (GENERATE_OPENAI, GENERATE_CHATGPT, DRAW_SVG, PREVIEW_OPENAI, PREVIEW_CHATGPT)}
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
        view_image: Callable[[str, str | None, Path | None, Path, Path], ImageView],
        move_image: Callable[[str, str, Path, Path, bool], ImageSummary],
        copy_image: Callable[[str, str, Path, Path, bool], ImageSummary],
        import_image: Callable[[Path, str | None, Path, Path, bool], ImageSummary],
        delete_image: Callable[[str, Path, Path], None],
        create_folder: Callable[[str, Path, Path, bool], str],
        move_folder: Callable[[str, str, Path, Path, bool], str],
        delete_folder: Callable[[str, Path, Path], list[str]],
        relink_images: Callable[[list[str] | None, Path, Path], ImageRelinking],
        restore_image_version: Callable[[str, str, Path, Path], ImageSummary],
        read_image_activity: Callable[[str, Path, Path, str | None], ImageActivity],
        list_image_methods: Callable[[], ImageMethods],
        generate_openai_image: Callable[..., Awaitable[ImageRun]],
        generate_chatgpt_image: Callable[..., Awaitable[ImageRun]],
        preview_openai_image_request: Callable[..., ImageRequestPreview],
        preview_chatgpt_image_request: Callable[..., ImageRequestPreview],
        draw_svg_image: Callable[..., Awaitable[ImageRun]],
        steer_svg_image: Callable[..., None],
        export_svg_image: Callable[[str, Path, float, str | None, Path, Path], Path],
        cancel_image: Callable[[str, Path, Path], None],
        choose_files: Callable[[Path, str], list[Path]],
        choose_folder: Callable[[Path, str], Path | None],
        choose_save_path: Callable[[Path, str, str], Path | None],
        openai_api_key_status: Callable[[], OpenAIKeyStatus],
        save_openai_api_key: Callable[[str], None],
        clear_openai_api_key: Callable[[], None],
        ask_secret: Callable[[str, str], str | None],
        settings_path: Path,
    ) -> None:
        self.directory, self.data_directory = directories(directory, data_directory)
        self.settings_path = settings_path
        self._list_images = list_images
        self._view_image = view_image
        self._move_image = move_image
        self._copy_image = copy_image
        self._import_image = import_image
        self._delete_image = delete_image
        self._create_folder = create_folder
        self._move_folder = move_folder
        self._delete_folder = delete_folder
        self._relink_images = relink_images
        self._restore_image_version = restore_image_version
        self._read_image_activity = read_image_activity
        self._list_image_methods = list_image_methods
        self._generate = {
            GENERATE_OPENAI.name: generate_openai_image,
            GENERATE_CHATGPT.name: generate_chatgpt_image,
            DRAW_SVG.name: draw_svg_image,
        }
        self._preview = {
            PREVIEW_OPENAI.name: preview_openai_image_request,
            PREVIEW_CHATGPT.name: preview_chatgpt_image_request,
        }
        self._steer_svg_image = steer_svg_image
        self._export_svg_image = export_svg_image
        self._cancel_image = cancel_image
        self._choose_files = choose_files
        self._choose_folder = choose_folder
        self._choose_save_path = choose_save_path
        self._openai_api_key_status = openai_api_key_status
        self._save_openai_api_key = save_openai_api_key
        self._clear_openai_api_key = clear_openai_api_key
        self._ask_secret = ask_secret
        # Whether a file or folder dialog is showing, so a second click does not show another.
        self._asking = False
        # Where the file dialogs open: where files were last chosen from, and until then the app's directory.
        self._last_folder: Path | None = None
        # The files chosen in a dialog since the app started, which it then offers as references.
        self._chosen: set[Path] = set()
        # The uploads no request took yet.
        self._uploads: set[str] = set()
        uploads.clear_old(time.time())
        # The last listing the view was given, which the files it then reads are checked against.
        self._listing: ImageListing | None = None
        # What the images with no file were last relinked from, and the likely files it left, so a listing that has
        # nothing new to relink from does not look again.
        self._relinked: tuple[object, list[ImageMove]] | None = None
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

    def show(self, name: str) -> str:
        """Bring the image up in the app: an open app switches to it, and one opened later opens on it.

        Returns its name as the directory has it, raising when there is no such image.
        """
        found = self._view_image(name, None, None, self.directory, self.data_directory).name
        show_image(found, self.data_directory)
        return found

    def close(self) -> None:
        """Stop serving the browser host page, if it was opened, and clear the uploads no request took."""
        with self._lock:
            if self._app is not None:
                self._app.stop()
                self._app = None
            for upload in self._uploads:
                uploads.clear(upload)
            self._uploads.clear()

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
            if is_image_resource(params.uri) or is_preview_resource(params.uri) or is_frame_resource(params.uri):
                return ReadResourceResult(contents=[await asyncio.to_thread(self._image_resource, params.uri)])
            if is_reference_resource(params.uri):
                return ReadResourceResult(contents=[await asyncio.to_thread(self._reference_resource, params.uri)])
        except ImageDesignError as error:
            raise MCPError(INVALID_PARAMS, str(error)) from None
        raise MCPError(
            INVALID_PARAMS,
            f"'{params.uri}' is not a resource of this server. It has {VIEW_URI}, each image's file at "
            f"{IMAGE_FILE.uri_template}, its versions at {IMAGE_VERSION.uri_template}, small copies of them at "
            f"{IMAGE_THUMBNAIL.uri_template}, their frames at {IMAGE_FRAME.uri_template} and small copies of those at "
            f"{FRAME_THUMBNAIL.uri_template}, the in-progress images of its runs at {RUN_PREVIEW.uri_template}, and "
            f"the references it offers at {REFERENCE_FILE.uri_template} and small copies of them at "
            f"{REFERENCE.uri_template}.",
        )

    def _image_resource(self, uri: str) -> BlobResourceContents:
        if self._listing is not None:
            try:
                return self._read_by(uri, self._listing)
            except ImageDesignError:
                # The image, version, or preview may be newer than that listing.
                pass
        return self._read_by(uri, self._list())

    def _read_by(self, uri: str, listing: ImageListing) -> BlobResourceContents:
        if is_frame_resource(uri):
            return read_frame_resource(uri, listing)
        if not is_preview_resource(uri):
            return read_image_resource(uri, listing)

        def activity(name: str) -> ImageActivity:
            return self._read_image_activity(name, listing.directory, listing.data_directory, None)

        return read_preview_resource(uri, listing, activity)

    def _reference_resource(self, uri: str) -> BlobResourceContents:
        return read_reference_resource(uri, self._as_reference(reference_path(uri)))

    def _as_reference(self, path: Path) -> Path:
        """`path`, once it is known to be an image the app offers as a reference, so no other file on this machine
        can be read or sent through the app."""
        state = read_app_state(self.data_directory)
        if (
            path in state.pins
            or path in self._chosen
            # A path that climbs out with `..` would still start with the folder's.
            or (
                ".." not in path.parts
                and any(folder.shows == "files" and path.is_relative_to(folder.path) for folder in state.folders)
            )
            or library.is_kept(self.data_directory, path)
            or library.is_used(self.data_directory, path)
            or self._kept_for_images(path)
            or (self._listing is not None and any(image.path == path for image in self._listing.images))
            # The image may be newer than that listing.
            or any(image.path == path for image in self._list().images)
        ):
            return path
        raise ImageDesignError(
            f"{path} is not an image the app offers as a reference. Pin it, pin the folder it is in, or choose it in "
            "the file dialog.",
            "not-a-reference",
        )

    def _kept_for_images(self, path: Path) -> bool:
        """Whether `path` is an image the tool keeps for the app's images: a version, or a copy of what a run was
        given."""
        try:
            kept = path.resolve().relative_to((self.data_directory / IMAGES).resolve())
        except ValueError:
            return False
        return kept.parts[1:2] in {("versions",), ("runs",)} and path.suffix.lower() in IMAGE_TYPES

    def _request(self, arguments: dict[str, Any], tool: Tool) -> dict[str, Any]:
        """What a request tool was called with, as the arguments of the library function it wraps, on the app's
        directory."""
        request = {name: arguments[name] for name in tool.input_schema["properties"] if name in arguments}
        for pair in ("size", "canvas"):
            if isinstance(request.get(pair), list):
                request[pair] = tuple(request[pair])
        if "marks" in request:
            request["marks"] = [_mark(number, mark) for number, mark in enumerate(request["marks"], 1)]
        if "references" in request:
            request["references"] = [self._reference(reference) for reference in request["references"]]
        if "mask" in request:
            request["mask"] = uploads.staged(request["mask"])
        return {**request, "directory": self.directory, "data_directory": self.data_directory}

    def _reference(self, reference: dict[str, Any]) -> Path:
        if "upload" in reference:
            return uploads.staged(reference["upload"])
        path = self._as_reference(Path(reference["path"]))
        if "frame" not in reference:
            return path
        # One frame of an animation goes as a still of its own, which waits as an upload does.
        upload, frame = _frame_upload(reference), reference["frame"]
        reel = pictures.reel(path)
        if not isinstance(frame, int) or not 0 <= frame < reel.count:
            raise ImageDesignError(
                f"{path.name} has {reel.count} frame(s), so frame {frame!r} does not exist. Send a frame from 0 to "
                f"{reel.count - 1}.",
                "invalid-request",
            )
        self._uploads.add(upload)
        # Named by the frame's place counting from 1, as the app shows it.
        stem = Path(self._reference_name(path)).stem
        return uploads.stage(upload, f"{stem}-frame-{frame + 1}.png", reel.png(frame))

    def _reference_name(self, path: Path) -> str:
        """What the app calls the reference at `path`: its file's name, or for a version kept for an image, the image's
        name and the version, so it says which image it is of."""
        if not self._kept_for_images(path):
            return path.name
        # The listing kept may be older than the version.
        return _version_name(self._listing, path) or _version_name(self._list(), path) or path.name

    def _took(self, arguments: dict[str, Any], run: ImageRun) -> list[Path]:
        """Remember the references a started run was given as used here, and clear the uploads it took, which the
        run has copied into its own folder. Returns where each reference is offered from now, in order."""
        given: list[UsedReference] = []
        for number, reference in enumerate(arguments.get("references") or [], 1):
            upload = _upload_of(reference)
            if upload is None:
                path = Path(reference["path"])
                given.append(UsedReference(name=self._reference_name(path), path=path))
                continue
            name = uploads.staged(upload).name
            copies = sorted((run.folder / "runs" / run.run_id / "inputs").glob(f"reference-{number}.*"))
            if copies:
                given.append(UsedReference(name=name, path=copies[0]))
        library.remember_used(self.data_directory, given)
        self._clear_taken(arguments)
        return [each.path for each in given]

    def _clear_taken(self, arguments: dict[str, Any]) -> None:
        """Clear the uploads a request took, once what it started has copied them."""
        taken = [_upload_of(reference) for reference in arguments.get("references") or []]
        for upload in [*filter(None, taken), *([arguments["mask"]] if "mask" in arguments else [])]:
            uploads.clear(upload)
            self._uploads.discard(upload)

    def _entries(self, paths: list[Path]) -> list[dict[str, Any]]:
        entries = (library.entry(path) for path in paths)
        return [found.model_dump(mode="json") for found in entries if found is not None]

    def _pinned_folder(self, path: Path, after: str | None) -> ReferenceFolderPage:
        pinned = [folder.path for folder in read_app_state(self.data_directory).folders if folder.shows == "files"]
        if path not in pinned:
            raise ImageDesignError(
                f"{path} is not a folder pinned to show its files. Those pinned so are: "
                f"{', '.join(str(folder) for folder in pinned) or 'none'}.",
                "missing-folder",
            )
        return library.list_folder(path, after)

    def _keep(self, upload: str) -> ReferenceEntry:
        kept = library.entry(library.keep(uploads.staged(upload), self.data_directory))
        if kept is None:
            raise ImageDesignError(f"The upload {upload} could not be kept to pin it. Add the file again.", "bad-upload")
        return kept

    async def _in_dialog[Asked, Chosen](self, ask: Callable[[Asked, str], Chosen], first: Asked, second: str) -> Chosen:
        if self._asking:
            raise ImageDesignError(
                "A window asking for something is already open. Answer it first; it may be behind another window.",
                "dialog-open",
            )
        self._asking = True
        try:
            return await asyncio.to_thread(ask, first, second)
        finally:
            self._asking = False

    async def _export(self, arguments: dict[str, Any]) -> str | None:
        """Render a drawing where the person says in the save dialog; None when they cancel."""
        name = arguments["name"]
        suggested = f"{PurePosixPath(name).stem}{arguments['format']}"
        chosen = await self._in_dialog(
            lambda folder, title: self._choose_save_path(folder, title, suggested), self._dialog_folder(), EXPORT_TITLE
        )
        if chosen is None:
            return None
        self._last_folder = chosen.parent
        written = await asyncio.to_thread(
            self._export_svg_image,
            name,
            chosen,
            arguments.get("scale", 1),
            arguments.get("version"),
            self.directory,
            self.data_directory,
        )
        return str(written)

    def _dialog_folder(self) -> Path:
        folder = self._last_folder
        return folder if folder is not None and folder.is_dir() else self.directory

    def _list(self) -> AppImages:
        directory, data = self.directory, self.data_directory
        listing = self._list_images(directory, data)
        likely: list[ImageMove] = []
        unlinked = _unlinked(listing)
        if unlinked is not None:
            if self._relinked is None or self._relinked[0] != (data, unlinked):
                found = self._relink_images(None, directory, data)
                for move in found.relinked:
                    self._follow(move.name, move.new_name, directory, data)
                if found.relinked:
                    listing = self._list_images(directory, data)
                self._relinked = ((data, _unlinked(listing)), found.likely)
            likely = self._relinked[1]
        # A listing that took long enough for `open_app` to switch directory is not the one to read files by.
        self._listing = listing if directory == self.directory else None
        shown = read_app_state(data).shown
        known = any(image.name == shown for image in listing.images)
        return AppImages(**dict(listing), shown=shown if known else None, likely=likely)

    def _follow(self, old: str, new: str, directory: Path, data: Path) -> None:
        """Point what the app keeps at an image, or at everything in a folder, that went from `old` to `new`."""
        follow_move(old, new, directory, data)
        library.follow_move(data, directory / old, directory / new)

    def _import(self, arguments: dict[str, Any]) -> ImageSummary:
        upload = arguments["upload"]
        image = self._import_image(
            uploads.staged(upload),
            _in_folder(arguments.get("folder")),
            self.directory,
            self.data_directory,
            bool(arguments.get("numbered")),
        )
        uploads.clear(upload)
        self._uploads.discard(upload)
        return image

    def _import_chosen(self, chosen: list[Path], folder: str | None) -> dict[str, Any]:
        """Bring each chosen file in, and say why each that was refused was, so one bad file does not stop the rest."""
        images: list[dict[str, Any]] = []
        refused: list[dict[str, Any]] = []
        for path in chosen:
            try:
                image = self._import_image(path, _in_folder(folder), self.directory, self.data_directory, True)
            except ImageDesignError as error:
                refused.append({"name": path.name, "reason": error.reason, "message": str(error)})
            else:
                images.append(image.model_dump(mode="json"))
        return {"images": images, "refused": refused}

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
        if params.name == SHOW_IMAGE.name:
            await asyncio.to_thread(show_image, arguments["name"], self.data_directory)
            return _text(f"The app shows {arguments['name']}.")
        if params.name == VIEW_IMAGE.name:
            image = await asyncio.to_thread(
                self._view_image, arguments["name"], arguments.get("version"), None, self.directory, self.data_directory
            )
            return _structured(image.model_dump(mode="json"))
        numbered = bool(arguments.get("numbered"))
        if params.name == MOVE_IMAGE.name:
            directory, data = self.directory, self.data_directory
            image = await asyncio.to_thread(
                self._move_image, arguments["name"], arguments["new_name"], directory, data, numbered
            )
            self._listing = None
            await asyncio.to_thread(self._follow, arguments["name"].replace("\\", "/"), image.name, directory, data)
            return _structured(image.model_dump(mode="json"))
        if params.name == COPY_IMAGE.name:
            image = await asyncio.to_thread(
                self._copy_image, arguments["name"], arguments["new_name"], self.directory, self.data_directory, numbered
            )
            return _structured(image.model_dump(mode="json"))
        if params.name == IMPORT_IMAGE.name:
            image = await asyncio.to_thread(self._import, arguments)
            return _structured(image.model_dump(mode="json"))
        if params.name == CHOOSE_IMAGES.name:
            chosen = await self._in_dialog(self._choose_files, self._dialog_folder(), CHOOSE_IMAGES_TITLE)
            if chosen:
                self._last_folder = chosen[0].parent
            return _structured(await asyncio.to_thread(self._import_chosen, chosen, arguments.get("folder")))
        if params.name == DELETE_IMAGE.name:
            await asyncio.to_thread(self._delete_image, arguments["name"], self.directory, self.data_directory)
            self._listing = None
            return _text(f"Deleted {arguments['name']}.")
        if params.name == CREATE_FOLDER.name:
            made = await asyncio.to_thread(
                self._create_folder, arguments["name"], self.directory, self.data_directory, numbered
            )
            return _structured({"name": made})
        if params.name == MOVE_FOLDER.name:
            directory, data = self.directory, self.data_directory
            moved = await asyncio.to_thread(
                self._move_folder, arguments["name"], arguments["new_name"], directory, data, numbered
            )
            self._listing = None
            await asyncio.to_thread(self._follow, arguments["name"].replace("\\", "/"), moved, directory, data)
            return _structured({"name": moved})
        if params.name == DELETE_FOLDER.name:
            left = await asyncio.to_thread(
                self._delete_folder, arguments["name"], self.directory, self.data_directory
            )
            self._listing = None
            return _structured({"left": left})
        if params.name == RELINK_IMAGE.name:
            directory, data = self.directory, self.data_directory
            found = await asyncio.to_thread(self._relink_images, [arguments["name"]], directory, data)
            for move in found.relinked:
                await asyncio.to_thread(self._follow, move.name, move.new_name, directory, data)
            self._listing = self._relinked = None
            return _structured(found.model_dump(mode="json"))
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
        if params.name == LIST_METHODS.name:
            methods = await asyncio.to_thread(self._list_image_methods)
            return _structured(methods.model_dump(mode="json"))
        if params.name in self._generate:
            # In a process of its own, so the image goes on being made when the app or its host closes.
            request = await asyncio.to_thread(self._request, arguments, REQUEST_TOOLS[params.name])
            run = await self._generate[params.name](**request, origin=ORIGIN, detach=True)
            references = await asyncio.to_thread(self._took, arguments, run)
            started = {"name": run.name, "run_id": run.run_id, "references": [str(path) for path in references]}
            return _structured(started)
        if params.name in self._preview:
            tool = REQUEST_TOOLS[params.name]
            preview = await asyncio.to_thread(lambda: self._preview[params.name](**self._request(arguments, tool)))
            return _structured(preview.model_dump(mode="json"))
        if params.name == STEER_SVG.name:
            request = await asyncio.to_thread(self._request, arguments, STEER_SVG)
            await asyncio.to_thread(lambda: self._steer_svg_image(**request, origin=ORIGIN))
            # The message left for the run holds copies of what it was given.
            await asyncio.to_thread(self._clear_taken, arguments)
            return _text(f"Left the message for the agent drawing {arguments['name']}.")
        if params.name == EXPORT_SVG.name:
            return _structured({"path": await self._export(arguments)})
        if params.name == CANCEL_IMAGE.name:
            await asyncio.to_thread(self._cancel_image, arguments["name"], self.directory, self.data_directory)
            return _text(f"Asked the run on {arguments['name']} to stop.")
        if params.name == UPLOAD_FILE.name:
            received = await asyncio.to_thread(
                uploads.receive, arguments["upload"], arguments["name"], arguments["offset"], arguments["data"]
            )
            self._uploads.add(arguments["upload"])
            return _structured({"received": received})
        if params.name == READ_LIBRARY.name:
            state = await asyncio.to_thread(read_app_state, self.data_directory)
            found = await asyncio.to_thread(library.read_library, self.data_directory, state)
            return _structured(found.model_dump(mode="json"))
        if params.name == LIST_FOLDER.name:
            page = await asyncio.to_thread(self._pinned_folder, Path(arguments["path"]), arguments.get("after"))
            return _structured(page.model_dump(mode="json"))
        if params.name == CHOOSE_FILES.name:
            folder = arguments.get("folder")
            opened = Path(folder) if folder else self._dialog_folder()
            chosen = await self._in_dialog(self._choose_files, opened, CHOOSE_FILES_TITLE)
            if chosen:
                self._last_folder = chosen[0].parent
                self._chosen.update(chosen)
            return _structured({"entries": await asyncio.to_thread(self._entries, chosen)})
        if params.name == CHOOSE_FOLDER.name:
            picked = await self._in_dialog(self._choose_folder, self._dialog_folder(), CHOOSE_FOLDER_TITLE)
            return _structured({"path": str(picked) if picked else None})
        if params.name == KEEP_REFERENCE.name:
            kept = await asyncio.to_thread(self._keep, arguments["upload"])
            return _structured(kept.model_dump(mode="json"))
        if params.name == READ_OPENAI_KEY.name:
            status = await asyncio.to_thread(self._openai_api_key_status)
            return _structured(status.model_dump(mode="json"))
        if params.name == ENTER_OPENAI_KEY.name:
            # Typed on this machine and kept here: the key is in no message between the view, its host, and this.
            entered = await self._in_dialog(self._ask_secret, ENTER_KEY_TITLE, ENTER_KEY_LABEL)
            if entered is not None:
                await asyncio.to_thread(self._save_openai_api_key, entered)
            status = await asyncio.to_thread(self._openai_api_key_status)
            return _structured({**status.model_dump(mode="json"), "entered": entered is not None})
        if params.name == CLEAR_OPENAI_KEY.name:
            await asyncio.to_thread(self._clear_openai_api_key)
            status = await asyncio.to_thread(self._openai_api_key_status)
            return _structured(status.model_dump(mode="json"))
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
            await asyncio.to_thread(library.clear_unpinned, self.data_directory, state.pins)
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
        name = arguments.get("name")
        shown = await asyncio.to_thread(self.show, name) if name is not None else None
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
        showing = f", with {shown} in view" if shown is not None else ""
        return _text(f"{where} It shows the images in {self.directory}{showing}.")


def _text(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _structured(structured: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(structured))], structured_content=structured
    )


def _unlinked(listing: ImageListing) -> tuple[tuple[str, ...], tuple[tuple[str, str | None], ...]] | None:
    """What `relink_images` works from in a listing: the images with no file, and the files nothing is kept for. None
    when there is none of either, so there is nothing to relink."""
    gone = tuple(
        image.name
        for image in listing.images
        if image.id is not None and image.modified is None and image.versions and image.status != "running"
    )
    free = tuple((image.name, image.sha256) for image in listing.images if image.id is None)
    return (gone, free) if gone and free else None


def _in_folder(folder: str | None) -> str | None:
    """A folder as `import_image` takes it for a name: ending in a slash, so the image keeps its file's name."""
    return f"{folder.rstrip('/')}/" if folder else None


def _version_name(listing: ImageListing | None, path: Path) -> str | None:
    """The name a version kept for an image goes by as a reference, after the image and the version; None when
    `listing` has no version kept at `path`."""
    for image in listing.images if listing is not None else []:
        for version in image.versions:
            if version.file == path:
                return f"{PurePosixPath(image.name).stem}-{version.id}{path.suffix}"
    return None


def _upload_of(reference: dict[str, Any]) -> str | None:
    """The upload a request's reference waits in: the one the view sent, or the one made for a frame; None for a file
    sent from where it is."""
    if "upload" in reference:
        return reference["upload"]
    return _frame_upload(reference) if "frame" in reference else None


def _frame_upload(reference: dict[str, Any]) -> str:
    """The upload one frame of a file waits in: the same one each time, so a request previewed and then sent keeps one
    copy, which each of them writes afresh."""
    return hashlib.sha256(f"{reference['path']}:{reference['frame']}".encode()).hexdigest()[:32]


def _mark(number: int, mark: Any) -> Mark:
    try:
        return Mark.model_validate(mark)
    except ValidationError as error:
        problem = error.errors()[0]
        where = ".".join(str(part) for part in problem["loc"])
        raise ImageDesignError(f"Mark {number}: {where}: {problem['msg']}.", "invalid-request") from None


def _takes_url_elicitation(ctx: ServerRequestContext[Any]) -> bool:
    capabilities = ctx.session.client_capabilities
    return (
        capabilities is not None and capabilities.elicitation is not None and capabilities.elicitation.url is not None
    )
