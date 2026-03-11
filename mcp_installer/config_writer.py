"""
Config file writer for Claude Desktop and Claude Code.

Writes MCP server configurations to the appropriate JSON config files.
Handles backup, merge with existing configs, and platform differences.

Failure modes handled:
- Existing config is malformed JSON → falls back to empty dict, backs up bad file
- Config directory doesn't exist → creates it
- Permission denied writing config → raises with clear message
- Concurrent writes → backup before write provides recovery
"""
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mcp_installer.constants import CREATION_FLAGS, SERVERS, FABRIC_ITEM_SUFFIXES
from mcp_installer.path_manager import find_executable


def build_server_configs(
    server_base_dir: Path,
    selected_servers: list[str],
    uv_path: str,
    tenant_id: str = "",
    subscription_id: str = "",
    az_server: str = "",
    az_database: str = "",
    az_auth: str = "az_cli",
    az_user: str = "",
    az_password: str = "",
) -> dict[str, dict]:
    """Build MCP server configuration dicts for all selected servers.

    Args:
        server_base_dir: Directory containing server subdirectories
        selected_servers: List of server keys (e.g., ["fabric", "powerbi"])
        uv_path: Path to the uv executable
        tenant_id: Azure tenant ID
        subscription_id: Azure subscription ID
        az_*: Azure SQL connection details

    Returns:
        Dict of server_name -> config dict for use in Claude configs
    """
    tenant_env: dict[str, str] = {}
    if tenant_id:
        tenant_env["AZURE_TENANT_ID"] = tenant_id
    if subscription_id:
        tenant_env["AZURE_SUBSCRIPTION_ID"] = subscription_id

    server_configs: dict[str, dict] = {}

    if "fabric" in selected_servers:
        cfg: dict[str, Any] = {
            "command": uv_path,
            "args": ["--directory", str(server_base_dir / "fabric-core"),
                     "run", "fabric_mcp_stdio.py"],
        }
        if tenant_env:
            cfg["env"] = tenant_env
        server_configs["fabric-core"] = cfg

    if "powerbi" in selected_servers:
        server_configs["powerbi-modeling"] = {
            "command": uv_path,
            "args": ["--directory", str(server_base_dir / "powerbi-modeling"),
                     "run", "python", "-m", "powerbi_modeling_mcp"],
        }

    if "translation" in selected_servers:
        server_configs["powerbi-translation-audit"] = {
            "command": uv_path,
            "args": ["--directory", str(server_base_dir / "translation-audit"),
                     "run", "python", "server.py"],
        }

    if "azure_sql" in selected_servers:
        az_env = {
            **tenant_env,
            "AZURE_SQL_SERVER": az_server,
            "AZURE_SQL_DATABASE": az_database,
            "AZURE_SQL_AUTH": az_auth,
        }
        if az_auth == "sql":
            az_env["AZURE_SQL_USER"] = az_user
            az_env["AZURE_SQL_PASSWORD"] = az_password

        server_configs["azure-sql"] = {
            "command": uv_path,
            "args": ["--directory", str(server_base_dir / "azure-sql"),
                     "run", "python", "-m", "azure_sql_mcp"],
            "env": az_env,
        }

    return server_configs


def get_desktop_config_path() -> Path:
    """Get the Claude Desktop config file path for the current platform."""
    import os
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "") or str(
            Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def _read_json_safe(path: Path) -> dict:
    """Read a JSON file, returning empty dict on any error."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _write_json_safe(path: Path, data: dict) -> None:
    """Write JSON to a file, creating parent dirs and backing up existing file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(".json.bak"))
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def write_desktop_config(server_configs: dict) -> Path:
    """Write/merge MCP server configs into Claude Desktop config.

    Returns the config file path.
    """
    config_path = get_desktop_config_path()
    existing = _read_json_safe(config_path)
    existing.setdefault("mcpServers", {})
    existing["mcpServers"].update(server_configs)
    _write_json_safe(config_path, existing)
    return config_path


def write_code_config(
    server_configs: dict,
    scope: str = "global",
    project_dir: str = "",
) -> Path:
    """Write/merge MCP server configs into Claude Code config.

    Args:
        server_configs: Server configuration dicts
        scope: "global" or "project"
        project_dir: Required if scope is "project"

    Returns the config file path.
    """
    if scope == "project":
        project = Path(project_dir)
        mcp_path = project / ".mcp.json"
        existing = _read_json_safe(mcp_path)
        existing.setdefault("mcpServers", {})
        existing["mcpServers"].update(server_configs)
        _write_json_safe(mcp_path, existing)
        return mcp_path
    else:
        settings_path = Path.home() / ".claude" / "settings.json"
        existing = _read_json_safe(settings_path)
        existing.setdefault("mcpServers", {})
        existing["mcpServers"].update(server_configs)
        _write_json_safe(settings_path, existing)
        return settings_path


def remove_desktop_config(server_keys_to_remove: list[str]) -> bool:
    """Remove MCP server configs from Claude Desktop config.

    Returns True if the config was modified.
    """
    config_path = get_desktop_config_path()
    existing = _read_json_safe(config_path)
    if not existing or "mcpServers" not in existing:
        return False

    modified = False
    for k in server_keys_to_remove:
        if k in existing["mcpServers"]:
            del existing["mcpServers"][k]
            modified = True

    if modified:
        _write_json_safe(config_path, existing)
    return modified


def remove_code_config(
    server_keys_to_remove: list[str],
    scope: str = "global",
    project_dir: str = "",
) -> bool:
    """Remove MCP server configs from Claude Code config.

    Returns True if the config was modified.
    """
    if scope == "project":
        mcp_path = Path(project_dir) / ".mcp.json"
        existing = _read_json_safe(mcp_path)
        path_to_write = mcp_path
    else:
        settings_path = Path.home() / ".claude" / "settings.json"
        existing = _read_json_safe(settings_path)
        path_to_write = settings_path

    if not existing or "mcpServers" not in existing:
        return False

    modified = False
    for k in server_keys_to_remove:
        if k in existing["mcpServers"]:
            del existing["mcpServers"][k]
            modified = True

    if modified:
        _write_json_safe(path_to_write, existing)
    return modified



def is_claude_desktop_running() -> bool:
    """Check if Claude Desktop is currently running (Windows only)."""
    if platform.system() != "Windows":
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Claude.exe", "/NH"],
            stderr=subprocess.STDOUT, text=True, timeout=5,
            creationflags=CREATION_FLAGS
        )
        return "Claude.exe" in out
    except Exception:
        return False


# ── Fabric project helpers ────────────────────────────────────────────────────


def scan_fabric_items(root: Path) -> list[dict]:
    """Scan for Fabric items by looking for .platform files or metadata.

    Returns list of dicts with 'name' and 'path' keys.
    """
    items: list[dict] = []
    try:
        for p in root.rglob(".platform"):
            item_dir = p.parent
            items.append({"name": item_dir.name, "path": str(item_dir)})
        for p in root.rglob("item.metadata.json"):
            item_dir = p.parent
            if not any(i["path"] == str(item_dir) for i in items):
                items.append({"name": item_dir.name, "path": str(item_dir)})
    except PermissionError:
        pass
    return items


def write_fabric_claude_md(project_dir: Path) -> str:
    """Write/update a CLAUDE.md for a Fabric project.

    Returns "created", "updated", or "appended" depending on what happened.
    """
    claude_md = project_dir / "CLAUDE.md"
    found = scan_fabric_items(project_dir)
    types_found: set[str] = set()
    for item in found:
        for sig in FABRIC_ITEM_SUFFIXES:
            if item["name"].endswith(sig):
                types_found.add(sig.lstrip("."))
                break

    content = "# Fabric Project\n\n"
    content += "This is a Microsoft Fabric project synced via Git integration.\n"
    content += "Do NOT treat files here as local code to run directly.\n\n"
    content += "## Rules\n\n"
    content += "- Use **fabric-core MCP tools** for all operations\n"
    content += "- Always call `set_workspace` before any operation\n"
    content += "- Discover items before querying — never guess names or schemas\n"
    content += "- Execute code via `run_notebook_job` or `sql_query` tools, not locally\n"
    content += "- .platform and item.metadata.json are Fabric system files — do not edit\n"
    content += "\n"
    content += "## Item types in this project\n\n"
    if types_found:
        for t in sorted(types_found):
            content += f"- {t}\n"
    else:
        content += "- (none detected)\n"
    content += "\n"
    content += "## Folder structure\n\n"
    content += "Each Fabric item is a folder named `ItemName.ItemType/` containing:\n"
    content += "- `.platform` — item metadata (GUID, type)\n"
    content += "- `item.metadata.json` — display name, description\n"
    content += "- `item.config.json` — item-specific config\n"
    content += "- Content files (notebooks: .py cells, semantic models: .tmdl, etc.)\n"

    marker_start = "# Fabric Project"
    marker_end = "- Content files (notebooks: .py cells, semantic models: .tmdl, etc.)"

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if marker_start in existing:
            pattern = re.escape(marker_start) + r".*?" + re.escape(marker_end)
            updated = re.sub(pattern, content.rstrip("\n"), existing, flags=re.DOTALL)
            claude_md.write_text(updated, encoding="utf-8")
            return "updated"
        else:
            with open(claude_md, "a", encoding="utf-8") as f:
                f.write("\n" + content)
            return "appended"
    else:
        claude_md.write_text(content, encoding="utf-8")
        return "created"


def copy_agents(
    source_dir: Path,
    selected_servers: list[str],
    dest_dir: Path,
) -> list[str]:
    """Copy agent markdown files to the destination directory.

    Returns list of copied file names.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    if any(k in selected_servers for k in ("fabric", "powerbi", "translation")):
        agents_src = source_dir / "agents" / "fabric"
        if agents_src.exists():
            for md in agents_src.glob("*.md"):
                shutil.copy2(md, dest_dir / md.name)
                copied.append(md.name)

    if "azure_sql" in selected_servers:
        agents_src = source_dir / "agents" / "azure-sql"
        if agents_src.exists():
            for md in agents_src.glob("*.md"):
                shutil.copy2(md, dest_dir / md.name)
                copied.append(md.name)

    return copied


def copy_skills(
    source_dir: Path,
    dest_dir: Path,
) -> list[str]:
    """Copy skill markdown files to the destination directory.

    Returns list of copied file names.
    """
    skills_src = source_dir / "skills" / "fabric-toolkit"
    if not skills_src.exists():
        return []

    skills_dest = dest_dir / "fabric-toolkit"
    skills_dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    for md in skills_src.glob("*.md"):
        shutil.copy2(md, skills_dest / md.name)
        copied.append(md.name)

    return copied


def install_notebook_template(
    src: Path,
    dest_dir: Path,
    claude_md_path: Path,
) -> str:
    """Copy notebook template and inject reference into CLAUDE.md.

    Returns "added", "updated", or "copied" describing what happened.
    """
    notebooks_dir = dest_dir / "notebooks"
    notebooks_dir.mkdir(parents=True, exist_ok=True)
    dest = notebooks_dir / src.name
    shutil.copy2(src, dest)

    marker = "## Notebook Style"
    entry = (
        f"\n{marker}\n"
        f"When creating notebooks, follow the structure and style of this example:\n"
        f"`{dest}`\n"
    )

    existing_text = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    if marker not in existing_text:
        with open(claude_md_path, "a", encoding="utf-8") as f:
            f.write(entry)
        return "added"
    else:
        updated = re.sub(
            r"(## Notebook Style\r?\nWhen creating notebooks.*?\r?\n)`[^\r\n]+`",
            lambda m: m.group(1) + f"`{dest}`",
            existing_text,
            flags=re.DOTALL,
        )
        claude_md_path.write_text(updated, encoding="utf-8")
        return "updated"


def install_glossary(
    files: list[Path],
    dest_dir: Path,
    claude_md_path: Path,
    glossary_ref: str = "",
) -> list[str]:
    """Copy glossary files and inject reference into CLAUDE.md.

    Returns list of copied file names.
    """
    glossary_dir = dest_dir / "glossary"
    glossary_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    for src in files:
        dest = glossary_dir / src.name
        shutil.copy2(src, dest)
        copied.append(src.name)

    if not glossary_ref:
        glossary_ref = f"`{glossary_dir}`"

    marker = "## Translation Glossary"
    entry = (
        f"\n{marker}\n"
        f"When translating Power BI reports, check {glossary_ref} for company-specific term dictionaries.\n"
        f"If glossary files exist, use them as the authoritative source for terminology.\n"
        f"If no glossary files exist, use your best judgment for translations.\n"
    )

    existing_text = claude_md_path.read_text(encoding="utf-8") if claude_md_path.exists() else ""
    if marker not in existing_text:
        with open(claude_md_path, "a", encoding="utf-8") as f:
            f.write(entry)

    return copied
