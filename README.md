# MCP Server Installer

GUI installer for fabric-core, powerbi-modeling, translation-audit, and azure-sql MCP servers.

## Run from source

```bash
pip install requests packaging
python installer.py
```

## Build exe

```bash
pip install pyinstaller
pyinstaller build.spec
# Output: dist/MCPInstaller.exe
```

## What it does

1. Clones/updates `mcp-servers` repo to install dir
2. Runs `uv sync` for each selected server
3. Writes `claude_desktop_config.json` and/or `~/.claude/settings.json`
4. Copies agent markdown files to `~/.claude/agents/`

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [git](https://git-scm.com/)
- [Azure CLI](https://aka.ms/installazurecliwindows) (for fabric-core / azure-sql)
- ODBC Driver 18 for SQL Server (for azure-sql only)
