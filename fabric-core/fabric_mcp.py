from tools import *
from helpers.logging_config import get_logger
from helpers.utils.context import mcp, __ctx_cache
import uvicorn
import argparse
import logging



logger = get_logger(__name__)
logger.level = logging.INFO


@mcp.tool()
async def clear_context() -> str:
    """Clear the current session context.

    Returns:
        A string confirming the context has been cleared.
    """
    __ctx_cache.clear()
    return "Context cleared."


if __name__ == "__main__":
    # Initialize and run the server
    logger.info("Starting MCP server...")
    parser = argparse.ArgumentParser(description="Run MCP Streamable HTTP based server")
    parser.add_argument("--port", type=int, default=8081, help="Localhost port to listen on")
    args = parser.parse_args()

    # Start the server with Streamable HTTP transport
    uvicorn.run(mcp.streamable_http_app, host="0.0.0.0", port=args.port)
    # mcp.run(transport="stdio")
