"""FastMCP entry point — wires all tools and runs the server."""

from __future__ import annotations

from fastmcp import FastMCP

from .dll_resolver import load_tom
from .discovery import discover_local_instances
from .connection import (
    connect_local,
    connect_fabric,
    connect_pbip,
    disconnect,
    get_state,
)
from . import metadata
from . import translations
from . import tmdl


def create_server() -> FastMCP:
    """Build and configure the MCP server with all tools."""
    mcp = FastMCP(
        "powerbi-modeling-mcp",
        instructions="Power BI TOM API — model metadata and sv-SE translations",
    )

    # Discovery tool
    @mcp.tool()
    def discover_instances() -> list[dict]:
        """Scan filesystem for running Power BI Desktop local AS instances.

        Returns list of {workspace_id, port, port_file_path} for each instance found.
        """
        return discover_local_instances()

    # Connection tools
    @mcp.tool()
    def connect_to_local(port: int) -> dict:
        """Connect to a local Power BI Desktop instance by port number.

        Use discover_instances() first to find available ports.
        """
        return connect_local(port)

    @mcp.tool()
    def connect_to_fabric(workspace: str, dataset: str, access_token: str = "") -> dict:
        """Connect to a Power BI dataset in a Fabric workspace via XMLA endpoint."""
        return connect_fabric(workspace, dataset, access_token)

    @mcp.tool()
    def connect_to_pbip(folder_path: str) -> dict:
        """Connect to a PBIP/TMDL folder for offline model access."""
        return connect_pbip(folder_path)

    @mcp.tool()
    def disconnect_server() -> dict:
        """Disconnect from current Power BI model."""
        return disconnect()

    @mcp.tool()
    def get_connection_status() -> dict:
        """Get current connection status and mode."""
        return get_state().summary

    # Register tools from submodules
    metadata.register_tools(mcp)
    translations.register_tools(mcp)
    tmdl.register_tools(mcp)

    return mcp


def main() -> None:
    """Load DLLs, create server, run on stdio."""
    load_tom()
    mcp = create_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
