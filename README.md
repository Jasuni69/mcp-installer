# MCP Server Installer

GUI installer for fabric-core, powerbi-modeling, translation-audit, and azure-sql MCP servers.

**No Python required on end-user machines** — download `MCPInstaller.exe` from the [Releases](https://github.com/Jasuni69/mcp-installer/releases) page.

## For end users

1. Download `MCPInstaller.exe` from Releases
2. Run it — no install needed
3. Pick servers, click Install

Prerequisites (installer checks and tells you what's missing):
- [uv](https://docs.astral.sh/uv/) — Python package manager (tiny, standalone)
- [git](https://git-scm.com/)
- [Azure CLI](https://aka.ms/installazurecliwindows) — for Fabric / Azure SQL
- ODBC Driver 18 for SQL Server — for Azure SQL only

## For developers

Build the exe:

```bash
pip install pyinstaller requests packaging
pyinstaller build.spec
# Output: dist/MCPInstaller.exe
```

Run from source (requires Python):

```bash
pip install requests packaging
python installer.py
```

## What it does

1. Clones/updates `mcp-servers` repo to install dir
2. Runs `uv sync` for each selected server
3. Writes `claude_desktop_config.json` and/or `~/.claude/settings.json`
4. Copies agent markdown files to `~/.claude/agents/`
