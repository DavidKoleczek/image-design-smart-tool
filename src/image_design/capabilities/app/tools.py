"""What the app's MCP server offers: the tool that opens the app, the tools its view calls, and the view."""

from mcp.server.apps import APP_MIME_TYPE
from mcp.types import Resource, ResourceTemplate, Tool

VIEW_URI = "ui://image-design/app"
IMAGE_FILE_PREFIX = "image-design://images/"
IMAGE_VERSION_PREFIX = "image-design://versions/"
IMAGE_THUMBNAIL_PREFIX = "image-design://thumbnails/"
# In a thumbnail's URI, names the image's file where a version's id would be.
FILE = "file"
APP_ONLY = {"ui": {"resourceUri": VIEW_URI, "visibility": ["app"]}}
IMAGE_NAME = {"type": "string", "description": "The image's path in the directory, such as concepts/cactus.png"}
OPEN_APP = Tool(
    name="open_app",
    description="Show the Image Design app, where the user sees the images in a directory, and return its browser "
    "URL. Hosts that render MCP Apps show it inline. Opening it again returns the same URL.",
    input_schema={
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Where the images to show are kept, absolute or relative to where this server started. "
                "Omit it to keep the current one, .image-design in the working directory at first.",
            },
            "data_directory": {
                "type": "string",
                "description": "Where the tool keeps the versions and runs of those images. Omit it for .agents in "
                "the directory.",
            },
        },
    },
    _meta={"ui": {"resourceUri": VIEW_URI}},
)
LIST_IMAGES = Tool(
    name="list_images",
    description="The images in the app's directory, in name order, with their versions and how their last runs went, "
    "and the one viewed last. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
READ_SETTINGS = Tool(
    name="read_app_settings",
    description="How the person set up the app, such as its theme and pane sizes, the same in every directory. Called "
    "by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
SAVE_SETTINGS = Tool(
    name="save_app_settings",
    description="Keep how the person set up the app, replacing what was kept, and return it as kept. Called by the "
    "view.",
    input_schema={
        "type": "object",
        "properties": {"settings": {"type": "object", "description": "What `read_app_settings` returns, changed"}},
        "required": ["settings"],
    },
    _meta=APP_ONLY,
)
READ_STATE = Tool(
    name="read_app_state",
    description="What the person last picked in the app for the images in its directory. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
SAVE_STATE = Tool(
    name="save_app_state",
    description="Keep what the person last picked in the app for the images in its directory, replacing what was "
    "kept, and return it as kept. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {"state": {"type": "object", "description": "What `read_app_state` returns, changed"}},
        "required": ["state"],
    },
    _meta=APP_ONLY,
)
VIEW_IMAGE = Tool(
    name="view_image",
    description="Record an image as the one the person is looking at, and return it with its versions. Called by "
    "the view.",
    input_schema={"type": "object", "properties": {"name": IMAGE_NAME}, "required": ["name"]},
    _meta=APP_ONLY,
)
MOVE_IMAGE = Tool(
    name="move_image",
    description="Rename an image, or move it to another folder of the directory, and return it there. It keeps its "
    "versions. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": IMAGE_NAME,
            "new_name": {"type": "string", "description": "Its new path in the directory, with the same extension"},
        },
        "required": ["name", "new_name"],
    },
    _meta=APP_ONLY,
)
DELETE_IMAGE = Tool(
    name="delete_image",
    description="Delete an image's file and everything kept for it, stopping a run working on it first. Called by the "
    "view.",
    input_schema={"type": "object", "properties": {"name": IMAGE_NAME}, "required": ["name"]},
    _meta=APP_ONLY,
)
RESTORE_VERSION = Tool(
    name="restore_image_version",
    description="Put an earlier version of an image back in its file, and return the image. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": IMAGE_NAME,
            "version": {"type": "string", "description": "The version's id, such as v2"},
        },
        "required": ["name", "version"],
    },
    _meta=APP_ONLY,
)
READ_ACTIVITY = Tool(
    name="read_image_activity",
    description="The history of an image: each run's request, what happened, and how it ended, as the run's events. "
    "Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": IMAGE_NAME,
            "after": {"type": "string", "description": "The cursor of an earlier call, for only what happened since"},
        },
        "required": ["name"],
    },
    _meta=APP_ONLY,
)
VIEW_TOOLS = [
    LIST_IMAGES,
    VIEW_IMAGE,
    MOVE_IMAGE,
    DELETE_IMAGE,
    RESTORE_VERSION,
    READ_ACTIVITY,
    READ_SETTINGS,
    SAVE_SETTINGS,
    READ_STATE,
    SAVE_STATE,
]
VIEW = Resource(uri=VIEW_URI, name="Image Design app", mime_type=APP_MIME_TYPE)
IMAGE_FILE = ResourceTemplate(
    name="Image file",
    uri_template=f"{IMAGE_FILE_PREFIX}{{+name}}",
    description="An image's file, as base64, for the app's view.",
)
IMAGE_VERSION = ResourceTemplate(
    name="Image version",
    uri_template=f"{IMAGE_VERSION_PREFIX}{{version}}/{{+name}}",
    description="A version kept for an image, by its id such as v2, as base64, for the app's view.",
)
IMAGE_THUMBNAIL = ResourceTemplate(
    name="Image thumbnail",
    uri_template=f"{IMAGE_THUMBNAIL_PREFIX}{{version}}/{{+name}}",
    description=f"A small WebP of a version of an image, or of its file when the version is `{FILE}`, as base64, for "
    "the app's view.",
)
IMAGE_RESOURCES = [IMAGE_FILE, IMAGE_VERSION, IMAGE_THUMBNAIL]
