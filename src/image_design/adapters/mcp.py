"""MCP adapter: the app's MCP server over stdio, a thin surface over the library."""

import asyncio
from pathlib import Path

from mcp.server.stdio import stdio_server

from image_design import lib


def run_stdio(directory: Path | None = None, data_directory: Path | None = None) -> None:
    """Serve the MCP server over stdin and stdout until the client disconnects, then stop the app if it was opened.

    Args:
        directory: Where the images the app shows are kept; `.image-design` in the working directory when omitted.
        data_directory: Where the tool keeps their versions and runs; `.agents` in the directory when omitted.
    """
    asyncio.run(_serve(directory, data_directory))


async def _serve(directory: Path | None, data_directory: Path | None) -> None:
    app_server = lib.app_server(directory, data_directory)
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app_server.server.run(read_stream, write_stream, app_server.server.create_initialization_options())
    finally:
        app_server.close()
