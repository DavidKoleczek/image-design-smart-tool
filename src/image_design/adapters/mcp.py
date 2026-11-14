"""MCP adapter: the app's MCP server over stdio, a thin surface over the library."""

import asyncio

from mcp.server.stdio import stdio_server

from image_design import lib


def run_stdio() -> None:
    """Serve the MCP server over stdin and stdout until the client disconnects, then stop the app if it was opened."""
    asyncio.run(_serve())


async def _serve() -> None:
    app_server = lib.app_server()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app_server.server.run(read_stream, write_stream, app_server.server.create_initialization_options())
    finally:
        app_server.close()
