from tools import *
from helpers.logging_config import get_logger
from helpers.utils.context import mcp, __ctx_cache, clear_context  # noqa: F401
import logging



logger = get_logger(__name__)
logger.level = logging.ERROR


if __name__ == "__main__":
    # Initialize and run the server in STDIO mode
    # Avoid stdout noise before the MCP handshake
    logger.error("Starting MCP server in STDIO mode...")
    mcp.run(transport="stdio")
