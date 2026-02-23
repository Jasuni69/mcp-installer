from tools import *
from helpers.logging_config import get_logger
from helpers.utils.context import mcp, __ctx_cache
import logging



logger = get_logger(__name__)
logger.level = logging.ERROR


@mcp.tool()
async def clear_context() -> str:
    """Clear the current session context.

    Returns:
        A string confirming the context has been cleared.
    """
    __ctx_cache.clear()
    return "Context cleared."


if __name__ == "__main__":
    # Initialize and run the server in STDIO mode
    # Avoid stdout noise before the MCP handshake
    logger.error("Starting MCP server in STDIO mode...")
    mcp.run(transport="stdio")
