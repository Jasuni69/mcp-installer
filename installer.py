"""
MCP Server Installer — Entry point.

This is a thin wrapper for backward compatibility.
The real code lives in the mcp_installer package.
"""
from mcp_installer.__main__ import main

if __name__ == "__main__":
    main()
