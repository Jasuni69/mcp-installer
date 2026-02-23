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
- ODBC Driver 17 or 18 for SQL Server — for Azure SQL only
- [.NET 9.x runtime](https://aka.ms/dotnet/download) — for Power BI Modeling only

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

1. Clones/updates `mcp-installer` repo to install dir
2. Runs `uv sync` for each selected server
3. Writes `claude_desktop_config.json` and/or `~/.claude/settings.json`
4. Copies agent markdown files to `~/.claude/agents/`

## After install — important steps

### %PATH and VSCode

Windows programs (uv, git, Azure CLI) add themselves to the system `%PATH` when installed. **VSCode snapshots `%PATH` once when it launches** and does not refresh it while running.

If you installed any prerequisite (uv, git, Azure CLI) during this session:

1. **Close ALL VSCode windows** — every one, not just the active one
2. Reopen VSCode

> **"Reload Window" is NOT enough.** VSCode inherits `%PATH` from the process that spawned it. Only a full restart picks up system-level PATH changes. The same applies to any terminal (PowerShell, Windows Terminal, CMD).

### Claude Desktop — verify MCP servers

After installing, Claude Desktop must be fully restarted to load the new MCP config:

1. **Quit Claude Desktop** — check the **system tray** (bottom-right) and right-click → Quit. Just closing the window may leave it running in the background.
2. Reopen Claude Desktop
3. Go to **Settings ▸ Connectors**
4. Your installed MCP servers should appear in the list (e.g. `fabric-core`, `powerbi-modeling`)

If a server shows an error in Connectors, check:
- Is `uv` on your PATH? (restart Claude Desktop after installing uv)
- Is Azure CLI authenticated? (`az login` in a terminal)
- For Power BI Modeling: is .NET 9.x runtime installed?
- For Azure SQL: is ODBC Driver 18 installed?

### Claude Code — verify MCP servers

Run `claude` in any terminal. If `uv` is not recognized, restart your terminal first.

Use `/mcp` inside Claude Code to check which MCP servers are connected.

## Where credentials are stored

The installer writes MCP server config (including Azure SQL connection details) to **plain-text JSON files**:

| Client | Config file |
|--------|-------------|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Code (global) | `~/.claude/settings.json` |
| Claude Code (project) | `<project>/.claude/settings.local.json` |

**What's stored:**
- Azure SQL server name, database name, and auth method
- If using SQL auth: **username and password in plain text**
- Azure CLI auth (`az_cli`) does NOT store credentials — it uses your `az login` session token at runtime

**Also stored (if Azure account selected):**
- Azure tenant ID and subscription ID as environment variables in the server config

**What's NOT stored:**
- Fabric/Power BI tokens — fetched at runtime via Azure CLI login

> **Security note:** If you use SQL auth, your password sits in plain text in the config file. Prefer `az_cli` auth when possible. If you must use SQL auth, make sure the config file isn't shared or committed to version control.

To change credentials later, just rerun the installer with the new values — it skips the heavy steps if already installed.

## Troubleshooting

### "uv: command not found" / "'uv' is not recognized"

uv was installed but your terminal doesn't see it yet. **Close and reopen your terminal** (or all VSCode windows). The new `%PATH` is only picked up by newly launched processes.

### Claude Desktop doesn't show my servers in Connectors

1. Make sure you fully quit Claude Desktop (system tray → Quit)
2. Reopen it and check **Settings ▸ Connectors**
3. If servers still missing, open `%APPDATA%\Claude\claude_desktop_config.json` and verify the `mcpServers` section exists

### Azure SQL server won't connect

- Verify ODBC Driver 18 is installed (run the installer again to check prerequisites)
- For `az_cli` auth: run `az login` and make sure your account has access to the database
- For `sql` auth: double-check username, password, and that your IP is allowed through the Azure SQL firewall

### Power BI Modeling server crashes on start

- .NET 9.x runtime must be installed: `winget install Microsoft.DotNet.Runtime.9`
- TOM DLLs must be present in `powerbi-modeling/lib/` or discoverable via NuGet cache / SSMS install
- Power BI Desktop must be running if using local connection mode

### "git clone" or "uv sync" hangs

The installer has a 5-minute timeout per command. If your network is slow or behind a proxy:
- Check your internet connection
- If behind a corporate proxy, configure `git` and `uv` proxy settings
- Try again — transient network issues are common

### Azure token expired / MCP tools stopped working

Azure CLI tokens expire after a few hours. If MCP tools suddenly stop connecting:

1. Open a terminal and run `az login`
2. Restart Claude Desktop or your terminal

### Corporate proxy blocking git/uv

If `git clone` or `uv sync` fail with connection errors behind a corporate proxy:

```bash
git config --global http.proxy http://proxy.company.com:8080
git config --global https.proxy http://proxy.company.com:8080
```

For uv, set the environment variable:
```
set HTTPS_PROXY=http://proxy.company.com:8080
```

### Azure SQL: "Cannot open server" / connection refused

Your IP may not be in the Azure SQL firewall allow-list:

1. Go to Azure Portal → your SQL Server → Networking
2. Add your current IP address (or enable "Allow Azure services")
3. Save and retry

### winget install fails with "access denied"

Some packages require administrator privileges. Right-click the installer (or terminal) and select **Run as administrator**, then retry.

### Force reinstall (broken .venv)

If `uv sync` failed partway and left a broken environment, check **"Force reinstall"** in the installer before clicking Install. This deletes existing `.venv` folders and re-creates them from scratch.

### Paths with spaces or special characters

The installer handles paths with spaces (e.g. `C:\Users\John Smith\.mcp-servers`). If you encounter issues, try an install location without spaces (e.g. `C:\mcp-servers`).
