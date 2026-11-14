"""What the app's MCP server offers: the tool that opens the app, the tools its view calls, and the view."""

from mcp.server.apps import APP_MIME_TYPE
from mcp.types import Resource, ResourceTemplate, Tool

VIEW_URI = "ui://image-design/app"
IMAGE_FILE_PREFIX = "image-design://images/"
IMAGE_VERSION_PREFIX = "image-design://versions/"
IMAGE_THUMBNAIL_PREFIX = "image-design://thumbnails/"
RUN_PREVIEW_PREFIX = "image-design://previews/"
REFERENCE_PREFIX = "image-design://references/"
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
LIST_METHODS = Tool(
    name="list_image_methods",
    description="The ways of making an image, whether each is set up on this machine, and the models and options "
    "each takes. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
# What both image models are asked the same way.
REQUEST = {
    "prompt": {"type": "string", "description": "What to make, or what to change, sent as written"},
    "name": {
        "type": "string",
        "description": "The image's path in the directory. A new name creates the image, and the name of one that "
        "exists edits it",
    },
    "version": {"type": "string", "description": "The version to edit, such as v2. Omit it for the image's file"},
}
REFERENCE_PATH = {"type": "string", "description": "An image file's path on this machine, as the app offered it"}
UPLOAD = {"type": "string", "description": "An upload's id: 16 to 64 lowercase hex digits the view makes up"}
REFERENCES = {
    "type": "array",
    "items": {"type": "object", "properties": {"path": REFERENCE_PATH, "upload": UPLOAD}},
    "description": "Other images to send with the prompt, in order. Each is a `path` the app offers as a reference, "
    "or the `upload` holding a file sent with `upload_file`",
}
MARKS = {
    "type": "array",
    "items": {"type": "object"},
    "description": "Shapes drawn over the image being edited, each with a `shape`, its `points` as fractions of the "
    "image, a `color`, and for a sketch of several strokes its further `strokes`",
}
OPENAI_REQUEST = {
    "type": "object",
    "properties": {
        **REQUEST,
        "references": REFERENCES,
        "marks": MARKS,
        "mask": {
            "type": "string",
            "description": "The upload holding a PNG the image's size, transparent where the model may make changes",
        },
        "model": {"type": "string", "description": "An OpenAI image model's ID. Omit it for the default"},
        "size": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
            "description": "Width and height. Omit it for the API's choice, or on an edit the image's own size",
        },
        "quality": {"type": "string"},
        "complexity": {"type": "string"},
        "background": {"type": "string"},
        "compression": {"type": "integer", "description": "0 to 100, for a .jpg or .webp"},
        "count": {"type": "integer", "description": "How many images to make. Each is kept as a version"},
        "previews": {"type": "integer", "description": "In-progress images to ask for, with a count of 1"},
    },
    "required": ["prompt", "name"],
}
CHATGPT_REQUEST = {
    "type": "object",
    "properties": {
        **REQUEST,
        "references": REFERENCES,
        "marks": MARKS,
        "transparent": {"type": "boolean", "description": "Ask for a transparent background"},
        "model": {"type": "string", "description": "The Codex model that carries the request. Omit it for the default"},
        "reasoning_effort": {"type": "string", "description": "That model's reasoning effort"},
    },
    "required": ["prompt", "name"],
}
GENERATE_OPENAI = Tool(
    name="generate_openai_image",
    description="Start creating or editing an image in the app's directory with an OpenAI image model, in a process "
    "of its own, and return the image's name and the run's id. Billed to the OpenAI API key. Called by the view.",
    input_schema=OPENAI_REQUEST,
    _meta=APP_ONLY,
)
GENERATE_CHATGPT = Tool(
    name="generate_chatgpt_image",
    description="Start creating or editing an image in the app's directory with the image generation built into "
    "Codex, in a process of its own, and return the image's name and the run's id. Counts against the ChatGPT plan "
    "Codex is signed in with. Called by the view.",
    input_schema=CHATGPT_REQUEST,
    _meta=APP_ONLY,
)
PREVIEW_OPENAI = Tool(
    name="preview_openai_image_request",
    description="What `generate_openai_image` would send for the same arguments: the prompt, the images in order, "
    "and the parameters. Nothing is sent or kept. Called by the view.",
    input_schema=OPENAI_REQUEST,
    _meta=APP_ONLY,
)
PREVIEW_CHATGPT = Tool(
    name="preview_chatgpt_image_request",
    description="What `generate_chatgpt_image` would send for the same arguments: the prompt, the images in order, "
    "and the parameters. Nothing is sent or kept. Called by the view.",
    input_schema=CHATGPT_REQUEST,
    _meta=APP_ONLY,
)
CANCEL_IMAGE = Tool(
    name="cancel_image",
    description="Stop the run working on an image, whichever process started it. A request already sent may still be "
    "billed or counted. Called by the view.",
    input_schema={"type": "object", "properties": {"name": IMAGE_NAME}, "required": ["name"]},
    _meta=APP_ONLY,
)
UPLOAD_FILE = Tool(
    name="upload_file",
    description="Send a piece of a file for a request to take: a reference dropped or pasted into the app, or the mask "
    "painted in it. Returns how much of the file has arrived. An upload no request takes is cleared when the app "
    "closes. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "upload": UPLOAD,
            "name": {"type": "string", "description": "The file's name"},
            "offset": {"type": "integer", "description": "Where in the file this piece starts"},
            "data": {"type": "string", "description": "The piece, as base64"},
        },
        "required": ["upload", "name", "offset", "data"],
    },
    _meta=APP_ONLY,
)
READ_LIBRARY = Tool(
    name="read_reference_library",
    description="The references the app offers besides the images in its directory: what the person pinned, and what "
    "requests sent from the app were given before. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
LIST_FOLDER = Tool(
    name="list_reference_folder",
    description="The images in a folder the person pinned to show its files. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "The pinned folder's path"}},
        "required": ["path"],
    },
    _meta=APP_ONLY,
)
CHOOSE_FILES = Tool(
    name="choose_reference_files",
    description="Ask the person for image files in their platform's file dialog, and return those they chose, which "
    "the app then offers as references. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "folder": {
                "type": "string",
                "description": "Where the dialog opens. Omit it for where files were last chosen from",
            }
        },
    },
    _meta=APP_ONLY,
)
CHOOSE_FOLDER = Tool(
    name="choose_reference_folder",
    description="Ask the person for a folder to pin in their platform's folder dialog, and return its path, or none "
    "when they cancel. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
KEEP_REFERENCE = Tool(
    name="keep_reference",
    description="Keep an uploaded image with the app's state for its directory, so it can be pinned, and return it "
    "as the app offers it. It is cleared once the app's state is saved without it among the pins. Called by the view.",
    input_schema={"type": "object", "properties": {"upload": UPLOAD}, "required": ["upload"]},
    _meta=APP_ONLY,
)
READ_OPENAI_KEY = Tool(
    name="read_openai_key",
    description="Where the OpenAI API key comes from: the environment, the platform's credential store, or nowhere. "
    "Never the key itself. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
ENTER_OPENAI_KEY = Tool(
    name="enter_openai_key",
    description="Ask the person to type their OpenAI API key into a window on this machine, and save it in the "
    "platform's credential store. The key is not an argument and is not returned, so it passes through no host. "
    "Returns where the key comes from now, and whether one was entered. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
CLEAR_OPENAI_KEY = Tool(
    name="clear_openai_key",
    description="Forget the OpenAI API key saved in the platform's credential store, and return where the key comes "
    "from now. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
VIEW_TOOLS = [
    LIST_IMAGES,
    VIEW_IMAGE,
    MOVE_IMAGE,
    DELETE_IMAGE,
    RESTORE_VERSION,
    READ_ACTIVITY,
    LIST_METHODS,
    GENERATE_OPENAI,
    GENERATE_CHATGPT,
    PREVIEW_OPENAI,
    PREVIEW_CHATGPT,
    CANCEL_IMAGE,
    UPLOAD_FILE,
    READ_LIBRARY,
    LIST_FOLDER,
    CHOOSE_FILES,
    CHOOSE_FOLDER,
    KEEP_REFERENCE,
    READ_OPENAI_KEY,
    ENTER_OPENAI_KEY,
    CLEAR_OPENAI_KEY,
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
RUN_PREVIEW = ResourceTemplate(
    name="Run preview",
    uri_template=f"{RUN_PREVIEW_PREFIX}{{run}}/{{index}}/{{+name}}",
    description="An in-progress image of a run on an image, by the run's id and the index its `preview` event has, as "
    "base64, for the app's view.",
)
REFERENCE = ResourceTemplate(
    name="Reference",
    uri_template=f"{REFERENCE_PREFIX}{{+path}}",
    description="A small WebP of an image the app offers as a reference, by its path on this machine: an image in "
    "the app's directory, one that is pinned, in a folder pinned to show its files, used before, or chosen in the "
    "file dialog. As base64, for the app's view.",
)
IMAGE_RESOURCES = [IMAGE_FILE, IMAGE_VERSION, IMAGE_THUMBNAIL, RUN_PREVIEW, REFERENCE]
