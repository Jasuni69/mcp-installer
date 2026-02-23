from mcp.server.fastmcp import FastMCP
from cachetools import TTLCache


# Create MCP instance with context manager
mcp = FastMCP("Fabric MCP Server ", json_response=True, stateless_http=True)
# Keep logs to stderr and at error-level to avoid polluting STDIO protocol
mcp.settings.log_level = "error"

# Shared cache and context
__ctx_cache = TTLCache(maxsize=100, ttl=300)  # Cache for 5 minutes
ctx = mcp.get_context()
