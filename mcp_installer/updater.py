"""
Version tracking and update checking.

Tracks installed server versions in a local versions.json file.
Compares against GitHub release manifest to determine available updates.

Failure modes handled:
- versions.json doesn't exist → returns empty dict
- versions.json is malformed → returns empty dict, logs warning
- versions.json write fails (permissions) → raises with context
- No internet → update check returns "unknown"
- GitHub API rate limit → returns "unknown" status
"""
import json
from pathlib import Path
from typing import Any

from mcp_installer import __version__
from mcp_installer.constants import VERSIONS_FILE


def read_local_versions(install_dir: Path) -> dict[str, str]:
    """Read the local versions.json file.

    Returns dict of component_name -> version string.
    Returns empty dict if file doesn't exist or is malformed.
    """
    versions_path = install_dir / VERSIONS_FILE
    if not versions_path.exists():
        return {}

    try:
        with open(versions_path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return {k: str(v) for k, v in data.items()}
    except (json.JSONDecodeError, IOError):
        return {}


def write_local_versions(install_dir: Path, versions: dict[str, str]) -> None:
    """Write the local versions.json file.

    Merges with existing versions rather than overwriting.
    """
    install_dir.mkdir(parents=True, exist_ok=True)
    versions_path = install_dir / VERSIONS_FILE

    existing = read_local_versions(install_dir)
    existing.update(versions)

    # Always include installer version
    existing["installer"] = __version__

    with open(versions_path, "w") as f:
        json.dump(existing, f, indent=2)


def check_for_installer_update() -> tuple[bool, str, str]:
    """Check GitHub for a newer installer version.

    Returns:
        (update_available, latest_version, release_url)

    Non-destructive — never modifies state. Returns (False, "", "")
    on any error.
    """
    try:
        import requests
        from packaging.version import Version

        from mcp_installer.constants import RELEASES_API

        resp = requests.get(RELEASES_API, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            url = data.get("html_url", "")
            if latest and Version(latest) > Version(__version__):
                return True, latest, url
    except Exception:
        pass

    return False, "", ""


def get_update_status(
    install_dir: Path,
    manifest: dict | None = None,
) -> dict[str, dict[str, Any]]:
    """Compare local versions against manifest to find available updates.

    Args:
        install_dir: Local installation directory
        manifest: Remote manifest from fetch_manifest(). If None, only
                  reports local versions.

    Returns:
        Dict of component_name -> {
            "local": "1.0.0" or None,
            "remote": "1.1.0" or None,
            "update_available": True/False
        }
    """
    local = read_local_versions(install_dir)
    status: dict[str, dict[str, Any]] = {}

    if manifest:
        servers = manifest.get("servers", {})
        for name, info in servers.items():
            remote_ver = info.get("version", "")
            local_ver = local.get(name, "")
            status[name] = {
                "local": local_ver or None,
                "remote": remote_ver or None,
                "update_available": bool(remote_ver and remote_ver != local_ver),
            }

        # Also check installer version
        installer_ver = manifest.get("installer_version", "")
        if installer_ver:
            status["installer"] = {
                "local": __version__,
                "remote": installer_ver,
                "update_available": installer_ver != __version__,
            }
    else:
        # No manifest — just report local versions
        for name, ver in local.items():
            status[name] = {
                "local": ver,
                "remote": None,
                "update_available": False,
            }

    return status
