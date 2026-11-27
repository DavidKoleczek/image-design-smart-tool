"""What the app's MCP server offers: the tool that opens the app, the tools its view calls, and the view."""

from mcp.server.apps import APP_MIME_TYPE
from mcp.types import Resource, ResourceTemplate, Tool

VIEW_URI = "ui://image-design/app"
IMAGE_FILE_PREFIX = "image-design://images/"
IMAGE_VERSION_PREFIX = "image-design://versions/"
IMAGE_THUMBNAIL_PREFIX = "image-design://thumbnails/"
RUN_PREVIEW_PREFIX = "image-design://previews/"
IMAGE_FRAME_PREFIX = "image-design://frames/"
FRAME_THUMBNAIL_PREFIX = "image-design://frame-thumbnails/"
REFERENCE_PREFIX = "image-design://references/"
REFERENCE_FILE_PREFIX = "image-design://reference-files/"
# In the URI of a thumbnail or a frame, names the image's file where a version's id would be.
FILE = "file"
APP_ONLY = {"ui": {"resourceUri": VIEW_URI, "visibility": ["app"]}}
IMAGE_NAME = {"type": "string", "description": "The image's path in the directory, such as concepts/cactus.png"}
NUMBERED = {
    "type": "boolean",
    "description": "When the name is taken, take the next free name like it, such as `cactus (2).png`, and return it",
}
FOLDER_NAME = {"type": "string", "description": "The folder's path in the directory, such as concepts/drafts"}
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
            "name": {
                "type": "string",
                "description": "An image to bring up, by its path in the directory. An open app switches to it.",
            },
        },
    },
    _meta={"ui": {"resourceUri": VIEW_URI}},
)
LIST_IMAGES = Tool(
    name="list_images",
    description="The images in the app's directory, in name order, with their versions and how their last runs went, "
    "its folders, and the image the app showed last. An image whose file was moved outside the app is first kept "
    "under the name its file has, when that file is certainly its own. Called by the view.",
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
READ_CONFIG = Tool(
    name="read_config",
    description="The person's defaults for the tool, the same in every directory, such as the order the image's "
    "agent picks an image model in when it is given none. Called by the view.",
    input_schema={"type": "object", "properties": {}},
    _meta=APP_ONLY,
)
UPDATE_CONFIG = Tool(
    name="update_config",
    description="Change the person's defaults for the tool, leaving those not given as they are, and return them all "
    "as kept. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "design_image_models": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The image models the image's agent picks from, in order, when it is given none: each "
                "an OpenAI image model's ID, or `chatgpt`. Those left out follow in the tool's own order",
            }
        },
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
SHOW_IMAGE = Tool(
    name="show_image",
    description="Record the image the person is looking at, which the app opens on next time. Called by the view.",
    input_schema={"type": "object", "properties": {"name": IMAGE_NAME}, "required": ["name"]},
    _meta=APP_ONLY,
)
VIEW_IMAGE = Tool(
    name="view_image",
    description="An image with its versions, and its file or one of its versions frame by frame, with how long each "
    "frame shows. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": IMAGE_NAME,
            "version": {"type": "string", "description": "The version to view, such as v2. Omit it for the file"},
        },
        "required": ["name"],
    },
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
            "numbered": NUMBERED,
        },
        "required": ["name", "new_name"],
    },
    _meta=APP_ONLY,
)
COPY_IMAGE = Tool(
    name="copy_image",
    description="Make another image with a copy of an image's file and of everything kept for it, and return the "
    "copy. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": IMAGE_NAME,
            "new_name": {"type": "string", "description": "The copy's path in the directory, with the same extension"},
            "numbered": NUMBERED,
        },
        "required": ["name", "new_name"],
    },
    _meta=APP_ONLY,
)
IMPORT_IMAGE = Tool(
    name="import_image",
    description="Bring a file sent with `upload_file` into the app's directory as a new image, under the file's own "
    "name, and return the image. The upload is cleared. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "upload": {"type": "string", "description": "The upload holding the image file"},
            "folder": {
                "type": "string",
                "description": "The folder to put it in. Omit it for the top of the directory",
            },
            "numbered": NUMBERED,
        },
        "required": ["upload"],
    },
    _meta=APP_ONLY,
)
CHOOSE_IMAGES = Tool(
    name="choose_image_files",
    description="Ask the person for image files in their platform's file dialog, and bring each into the app's "
    "directory as a new image, under a numbered name when its own is taken. Returns the images, and why each file "
    "that was refused was. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "folder": {
                "type": "string",
                "description": "The folder to put them in. Omit it for the top of the directory",
            }
        },
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
CREATE_FOLDER = Tool(
    name="create_folder",
    description="Make a folder in the app's directory, and return its name. Called by the view.",
    input_schema={"type": "object", "properties": {"name": FOLDER_NAME, "numbered": NUMBERED}, "required": ["name"]},
    _meta=APP_ONLY,
)
MOVE_FOLDER = Tool(
    name="move_folder",
    description="Rename a folder, or move it into another, with everything in it, and return its name. Its images "
    "keep their versions. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": FOLDER_NAME,
            "new_name": {"type": "string", "description": "Its new path in the directory"},
            "numbered": NUMBERED,
        },
        "required": ["name", "new_name"],
    },
    _meta=APP_ONLY,
)
DELETE_FOLDER = Tool(
    name="delete_folder",
    description="Delete every image in a folder, with everything kept for each, then the folder. Returns the files in "
    "it that are not images, which are left with the folder. Called by the view.",
    input_schema={"type": "object", "properties": {"name": FOLDER_NAME}, "required": ["name"]},
    _meta=APP_ONLY,
)
RELINK_IMAGE = Tool(
    name="relink_image",
    description="Keep an image that has no file under the name of the file that is likely its own, one of those "
    "`list_images` returns as `likely`. Called by the view.",
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
    "items": {
        "type": "object",
        "properties": {
            "path": REFERENCE_PATH,
            "frame": {"type": "integer", "minimum": 0, "description": "With `path`, the frame of an animation to send"},
            "upload": UPLOAD,
        },
    },
    "description": "Other images to send with the prompt, in order. Each is a `path` the app offers as a reference, "
    "with a `frame` to send one frame of an animation, or the `upload` holding a file sent with `upload_file`",
}
MARKS = {
    "type": "array",
    "items": {"type": "object"},
    "description": "Shapes drawn over the image being edited, each with a `shape`, its `points` as fractions of the "
    "image, a `color`, for a sketch of several strokes its further `strokes`, and `numbered` true to draw its number "
    "beside it",
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
        "frame": {
            "type": "integer",
            "minimum": 0,
            "description": "When the image being edited is an animation, the frame to send. Omit it for the first",
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
        "frames": {"type": "integer", "description": "For a .gif, how many frames. Omit it on an edit to keep its own"},
        "frame_ms": {
            "type": "integer",
            "description": "For a .gif, how long each frame shows. Omit it on an edit to keep its own",
        },
        "previews": {"type": "integer", "description": "In-progress images to ask for"},
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
# A budget left out of an edit keeps the drawing's, and null takes a limit off.
SVG_LIMIT = {"type": ["integer", "null"], "minimum": 1}
SVG_REQUEST = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "What to draw, or what to change, sent as written"},
        "name": {
            "type": "string",
            "description": "The drawing's path in the directory, ending in .svg. A new name draws it, and the name of "
            "one that exists changes it",
        },
        "references": REFERENCES,
        "marks": MARKS,
        "canvas": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
            "description": "A new drawing's width and height. Omit it for the default, and on an edit to keep the "
            "drawing's",
        },
        "max_bytes": {**SVG_LIMIT, "description": "The most bytes the SVG file can have; null for any"},
        "resume_session": {
            "type": "boolean",
            "description": "Continue the drawing's last agent session, so the agent remembers the earlier requests",
        },
        "agent_provider": {"type": "string", "description": "`codex` or `claude`. Omit it for the default"},
        "model": {"type": "string", "description": "The agent's model. Omit it for the agent provider's default"},
        "reasoning_effort": {"type": "string", "description": "That model's reasoning effort"},
        "timeout_seconds": {**SVG_LIMIT, "description": "How long the run may take; null for no limit"},
    },
    "required": ["prompt", "name"],
}
GENERATE_OPENAI = Tool(
    name="generate_openai_image",
    description="Start creating or editing an image in the app's directory with an OpenAI image model, in a process "
    "of its own, and return the image's name and the run's id. Called by the view.",
    input_schema=OPENAI_REQUEST,
    _meta=APP_ONLY,
)
GENERATE_CHATGPT = Tool(
    name="generate_chatgpt_image",
    description="Start creating or editing an image in the app's directory with the image generation built into "
    "Codex, in a process of its own, and return the image's name and the run's id. Called by the view.",
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
DRAW_SVG = Tool(
    name="draw_svg_image",
    description="Start drawing or changing an SVG in the app's directory with an agent that draws it in code, in a "
    "process of its own, and return the drawing's name and the run's id. Called by the view.",
    input_schema=SVG_REQUEST,
    _meta=APP_ONLY,
)
STEER_SVG = Tool(
    name="steer_svg_image",
    description="Send a message to the agent drawing an SVG in the app's directory while it works, with references "
    "and marks on its latest render. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": IMAGE_NAME,
            "message": {"type": "string", "description": "What the agent should change, sent as written"},
            "references": REFERENCES,
            "marks": MARKS,
        },
        "required": ["name", "message"],
    },
    _meta=APP_ONLY,
)
DESIGN_REQUEST = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "description": "What the person asks of the agent, not what an image model gets"},
        "name": REQUEST["name"],
        "references": REFERENCES,
        "marks": MARKS,
        "mask": {
            "type": "string",
            "description": "The upload holding a PNG the image's size, transparent where changes may go",
        },
        "version": {"type": "string", "description": "The version the request is about. Omit it for the file"},
        "frame": {"type": "integer", "minimum": 0, "description": "For an animation, the frame it is about"},
        "resume_session": {
            "type": "boolean",
            "description": "Continue the image's agent's last session, so it remembers the conversation",
        },
        "image_model": {
            "type": "string",
            "description": "What the agent makes its images with: an OpenAI image model's ID, or `chatgpt`. Omit it "
            "for the default",
        },
        "size": {
            **OPENAI_REQUEST["properties"]["size"],
            "description": "Width and height the agent passes to its calls. Omit it for the agent's choice",
        },
        "quality": {"type": "string", "description": "The quality the agent passes to its calls"},
        "agent_provider": {"type": "string", "description": "`codex` or `claude`. Omit it for the default"},
        "model": {"type": "string", "description": "The agent's model. Omit it for the agent provider's default"},
        "reasoning_effort": {"type": "string", "description": "That model's reasoning effort"},
        "timeout_seconds": {**SVG_LIMIT, "description": "How long the agent may work; null for no limit"},
    },
    "required": ["prompt", "name"],
}
DESIGN_IMAGE = Tool(
    name="design_image",
    description="Start the image's agent on a request in the app's directory, in a process of its own: it writes the "
    "image calls and makes them. Returns the image's name and the run's id. Called by the view.",
    input_schema=DESIGN_REQUEST,
    _meta=APP_ONLY,
)
STEER_IMAGE = Tool(
    name="steer_image",
    description="Send a message to the agent working on an image in the app's directory while it works, with "
    "references and marks on the image. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": IMAGE_NAME,
            "message": {"type": "string", "description": "What the agent should do, sent as written"},
            "references": REFERENCES,
            "marks": MARKS,
        },
        "required": ["name", "message"],
    },
    _meta=APP_ONLY,
)
EXPORT_SVG = Tool(
    name="export_svg_image",
    description="Ask the person where to save a render of an SVG in their platform's save dialog, and render it there. "
    "Returns the file written, or none when they cancel. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": IMAGE_NAME,
            "version": {"type": "string", "description": "The version to render, such as v2. Omit it for the file"},
            "format": {"type": "string", "description": "The extension to render to: .png, .jpg, or .webp"},
            "scale": {"type": "number", "exclusiveMinimum": 0, "description": "Times the drawing's size"},
        },
        "required": ["name", "format"],
    },
    _meta=APP_ONLY,
)
CANCEL_IMAGE = Tool(
    name="cancel_image",
    description="Stop the run working on an image, whichever process started it. Called by the view.",
    input_schema={"type": "object", "properties": {"name": IMAGE_NAME}, "required": ["name"]},
    _meta=APP_ONLY,
)
UPLOAD_FILE = Tool(
    name="upload_file",
    description="Send a piece of a file for a request or `import_image` to take: a reference dropped or pasted into "
    "the app, an image file dropped on Your images, or the mask painted in it. Returns how much of the file has "
    "arrived. An upload nothing takes is cleared when the app closes. Called by the view.",
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
    description="A page of the images in a folder the person pinned to show its files and in the folders in it, "
    "leaving out what is hidden. Returns them, each with the folder it is in, and `after` for the next page, or none "
    "once every image is listed. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The pinned folder's path"},
            "after": {
                "type": "string",
                "description": "The `after` an earlier page returned, to list what follows it. Omit it for the first",
            },
        },
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
SHOW_IN_FILE_MANAGER = Tool(
    name="show_in_file_manager",
    description="Show an image or a folder of the app's directory in the platform's file manager: a folder opened, "
    "and an image selected in its folder. Called by the view.",
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The image's or folder's path in the directory. Omit it for the directory itself",
            }
        },
    },
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
    SHOW_IMAGE,
    VIEW_IMAGE,
    MOVE_IMAGE,
    COPY_IMAGE,
    IMPORT_IMAGE,
    CHOOSE_IMAGES,
    DELETE_IMAGE,
    CREATE_FOLDER,
    MOVE_FOLDER,
    DELETE_FOLDER,
    RELINK_IMAGE,
    RESTORE_VERSION,
    READ_ACTIVITY,
    LIST_METHODS,
    GENERATE_OPENAI,
    GENERATE_CHATGPT,
    PREVIEW_OPENAI,
    PREVIEW_CHATGPT,
    DRAW_SVG,
    STEER_SVG,
    DESIGN_IMAGE,
    STEER_IMAGE,
    EXPORT_SVG,
    CANCEL_IMAGE,
    UPLOAD_FILE,
    READ_LIBRARY,
    LIST_FOLDER,
    CHOOSE_FILES,
    CHOOSE_FOLDER,
    SHOW_IN_FILE_MANAGER,
    KEEP_REFERENCE,
    READ_OPENAI_KEY,
    ENTER_OPENAI_KEY,
    CLEAR_OPENAI_KEY,
    READ_SETTINGS,
    SAVE_SETTINGS,
    READ_CONFIG,
    UPDATE_CONFIG,
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
IMAGE_FRAME = ResourceTemplate(
    name="Image frame",
    uri_template=f"{IMAGE_FRAME_PREFIX}{{version}}/{{index}}/{{+name}}",
    description=f"One frame of a version of an image, or of its file when the version is `{FILE}`, by its index from "
    "0, as a PNG in base64, for the app's view.",
)
FRAME_THUMBNAIL = ResourceTemplate(
    name="Frame thumbnail",
    uri_template=f"{FRAME_THUMBNAIL_PREFIX}{{version}}/{{index}}/{{+name}}",
    description="A small WebP of one frame, named as a frame is, as base64, for the app's view.",
)
REFERENCE = ResourceTemplate(
    name="Reference",
    uri_template=f"{REFERENCE_PREFIX}{{+path}}",
    description="A small WebP of an image the app offers as a reference, by its path on this machine: an image in "
    "the app's directory, one that is pinned, in a folder pinned to show its files, used before, chosen in the file "
    "dialog, or kept for an image: a version, or a copy of what a run was given. As base64, for the app's view.",
)
REFERENCE_FILE = ResourceTemplate(
    name="Reference file",
    uri_template=f"{REFERENCE_FILE_PREFIX}{{+path}}",
    description="An image the app offers as a reference, by its path on this machine, as a request sends it: a PNG, "
    "JPEG, or WebP as it is, and any other image as a PNG. As base64, for the app's view to show it large.",
)
IMAGE_RESOURCES = [
    IMAGE_FILE,
    IMAGE_VERSION,
    IMAGE_THUMBNAIL,
    IMAGE_FRAME,
    FRAME_THUMBNAIL,
    RUN_PREVIEW,
    REFERENCE,
    REFERENCE_FILE,
]
