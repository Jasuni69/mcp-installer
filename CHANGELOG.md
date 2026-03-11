# Changelog

All notable changes to the MCP Server Installer will be documented in this file.

## [2.0.0] — 2026-03-11

### 🚀 Major Changes

- **No more git dependency** — Server bundles are now downloaded as ZIP assets from GitHub Releases instead of requiring `git clone`
- **"Install All Missing" button** — One-click installation of all missing prerequisites (uv, git, Azure CLI, .NET 9)
- **PATH auto-broadcast** — After installing prerequisites, the installer broadcasts `WM_SETTINGCHANGE` so new terminals immediately see the tools without a restart
- **DPI-aware rendering** — Text and UI elements render crisply on high-DPI displays
- **Version tracking** — Each installed server's version is saved in `versions.json` for update comparison
- **SHA256 verification** — All downloaded server bundles are verified against checksums in the release manifest

### 🏗️ Architecture

- Refactored from 1,552-line monolith into modular package (`mcp_installer/`)
  - `constants.py` — Server definitions, URLs, theme tokens
  - `path_manager.py` — Executable lookup, PATH refresh, WM_SETTINGCHANGE broadcast
  - `prereqs.py` — Prerequisite detection and batch installation
  - `downloader.py` — GitHub Release downloads with checksum verification
  - `config_writer.py` — Claude Desktop/Code config generation
  - `updater.py` — Version tracking and update checking
  - `app.py` — GUI application
- Added 58 automated tests across all modules
- Added GitHub Actions CI for tests (on push/PR) and releases (on tag)

### 🐛 Fixes

- Fixed global mousewheel binding that interfered with log panel scrolling
- Moved `import re` and `import webbrowser` to proper locations
- Git is now optional (only needed if GitHub Release download is unavailable)

### 📦 Distribution

- Agents, skills, and templates are now bundled inside the exe
- Server code is downloaded from GitHub Release assets (smaller, faster, versioned)
- Fallback to git clone if release download fails (e.g., no releases published yet)

## [1.2.0] — Previous Release

- Initial GUI installer with prerequisite detection
- Git-based server distribution
- Claude Desktop and Claude Code config writing
- Agent and skill copying
- Fabric project CLAUDE.md generation
