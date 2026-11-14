"""What the app's MCP server offers: the tool that opens the app, and the view as a resource."""

from mcp.server.apps import APP_MIME_TYPE
from mcp.types import Resource, Tool

VIEW_URI = "ui://image-design/app"
OPEN_APP = Tool(
    name="open_app",
    description="Show the Image Design app and return its browser URL. Hosts that render MCP Apps show it inline. "
    "Opening it again returns the same URL.",
    input_schema={"type": "object", "properties": {}},
    _meta={"ui": {"resourceUri": VIEW_URI}},
)
VIEW = Resource(uri=VIEW_URI, name="Image Design app", mime_type=APP_MIME_TYPE)
