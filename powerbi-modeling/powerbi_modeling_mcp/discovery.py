"""Scan filesystem for running Power BI Desktop local AS instances."""

import os
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class LocalInstance:
    workspace_id: str
    port: int
    port_file_path: str
    pbix_hint: str = ""


def _workspace_roots() -> list[Path]:
    """Return candidate parent directories for AS workspace folders."""
    user = Path.home()
    roots = []

    # Store App (most common now)
    store_path = user / "Microsoft" / "Power BI Desktop Store App" / "AnalysisServicesWorkspaces"
    roots.append(store_path)

    # MSI install
    local_app = Path(os.environ.get("LOCALAPPDATA", user / "AppData" / "Local"))
    msi_path = local_app / "Microsoft" / "Power BI Desktop" / "AnalysisServicesWorkspaces"
    roots.append(msi_path)

    return roots


def discover_local_instances() -> list[dict]:
    """Find all running Power BI Desktop local AS instances.

    Scans workspace directories for msmdsrv.port.txt files.
    Returns list of dicts with workspace_id, port, port_file_path.
    """
    instances: list[LocalInstance] = []

    for root in _workspace_roots():
        if not root.exists():
            continue
        for workspace_dir in root.iterdir():
            if not workspace_dir.is_dir():
                continue
            port_file = workspace_dir / "Data" / "msmdsrv.port.txt"
            if not port_file.exists():
                continue
            try:
                raw = port_file.read_bytes()
                # Try UTF-16LE first (common on Windows), then utf-8-sig, then utf-8
                for enc in ("utf-16-le", "utf-8-sig", "utf-8"):
                    try:
                        port_text = raw.decode(enc).strip().strip("\x00")
                        break
                    except (UnicodeDecodeError, ValueError):
                        continue
                else:
                    continue
                port = int(port_text)
            except (ValueError, OSError):
                continue

            # Try to guess pbix name from workspace folder name
            ws_name = workspace_dir.name
            pbix_hint = ""
            if "_" in ws_name:
                # Workspace folders often named like AnalysisServicesWorkspace_<guid>
                pbix_hint = ws_name

            instances.append(LocalInstance(
                workspace_id=ws_name,
                port=port,
                port_file_path=str(port_file),
                pbix_hint=pbix_hint,
            ))

    return [asdict(inst) for inst in instances]
