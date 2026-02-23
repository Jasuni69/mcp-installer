"""Connection state management for Power BI TOM API."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ConnectionMode(str, Enum):
    LOCAL = "local"
    FABRIC = "fabric"
    PBIP = "pbip"
    DISCONNECTED = "disconnected"


@dataclass
class ConnectionState:
    mode: ConnectionMode = ConnectionMode.DISCONNECTED
    server: Any = None  # TOM Server object
    database: Any = None  # TOM Database object
    model: Any = None  # TOM Model object
    port: int | None = None
    connection_string: str = ""
    pbip_folder: str = ""
    database_name: str = ""

    @property
    def is_connected(self) -> bool:
        return self.mode != ConnectionMode.DISCONNECTED

    @property
    def summary(self) -> dict:
        info = {"mode": self.mode.value, "connected": self.is_connected}
        if self.port:
            info["port"] = self.port
        if self.database_name:
            info["database"] = self.database_name
        if self.pbip_folder:
            info["pbip_folder"] = self.pbip_folder
        return info


# Module-level singleton — one connection at a time
_state = ConnectionState()


def get_state() -> ConnectionState:
    return _state


def require_connected() -> ConnectionState:
    """Return current state or raise if not connected."""
    if not _state.is_connected:
        raise RuntimeError("Not connected. Use connect_local, connect_fabric, or connect_pbip first.")
    return _state


def require_tom_connected() -> ConnectionState:
    """Return current state or raise if not connected via TOM (local/fabric)."""
    state = require_connected()
    if state.mode == ConnectionMode.PBIP:
        raise RuntimeError("This operation requires a live TOM connection (local or fabric), not PBIP mode.")
    return state


def connect_local(port: int) -> dict:
    """Connect to a local Power BI Desktop AS instance via TOM."""
    global _state
    disconnect()

    from Microsoft.AnalysisServices.Tabular import Server  # type: ignore

    conn_str = f"Data Source=localhost:{port}"
    server = Server()
    server.Connect(conn_str)

    if server.Databases.Count == 0:
        server.Disconnect()
        raise RuntimeError(f"Connected to port {port} but no databases found.")

    db = server.Databases[0]
    model = db.Model

    _state = ConnectionState(
        mode=ConnectionMode.LOCAL,
        server=server,
        database=db,
        model=model,
        port=port,
        connection_string=conn_str,
        database_name=db.Name,
    )

    return {
        "status": "connected",
        "mode": "local",
        "port": port,
        "database": db.Name,
        "model_name": model.Name if model else "unknown",
        "compatibility_level": db.CompatibilityLevel,
    }


def connect_fabric(workspace: str, dataset: str, access_token: str = "") -> dict:
    """Connect to a Fabric/Power BI Service dataset via XMLA endpoint."""
    global _state
    disconnect()

    from Microsoft.AnalysisServices.Tabular import Server  # type: ignore

    endpoint = f"powerbi://api.powerbi.com/v1.0/myorg/{workspace}"
    conn_str = f"Data Source={endpoint};Initial Catalog={dataset}"
    if access_token:
        conn_str += f";Password={access_token}"

    server = Server()
    server.Connect(conn_str)

    db = server.Databases.FindByName(dataset)
    if db is None:
        server.Disconnect()
        raise RuntimeError(f"Dataset '{dataset}' not found in workspace '{workspace}'.")

    _state = ConnectionState(
        mode=ConnectionMode.FABRIC,
        server=server,
        database=db,
        model=db.Model,
        connection_string=conn_str,
        database_name=db.Name,
    )

    return {
        "status": "connected",
        "mode": "fabric",
        "workspace": workspace,
        "dataset": dataset,
        "compatibility_level": db.CompatibilityLevel,
    }


def connect_pbip(folder_path: str) -> dict:
    """Set connection to a PBIP/TMDL folder (no live TOM server)."""
    global _state
    disconnect()

    p = Path(folder_path)
    if not p.exists():
        raise RuntimeError(f"PBIP folder not found: {folder_path}")

    # Look for definition subfolder (standard PBIP structure)
    definition_dir = p / "definition"
    if not definition_dir.exists():
        definition_dir = p  # Maybe they pointed directly at definition/

    tmdl_files = list(definition_dir.glob("**/*.tmdl"))
    if not tmdl_files:
        raise RuntimeError(f"No .tmdl files found in {folder_path}")

    _state = ConnectionState(
        mode=ConnectionMode.PBIP,
        pbip_folder=str(p),
    )

    return {
        "status": "connected",
        "mode": "pbip",
        "folder": str(p),
        "tmdl_file_count": len(tmdl_files),
    }


def disconnect() -> dict:
    """Disconnect current connection and clean up."""
    global _state

    if _state.server is not None:
        try:
            _state.server.Disconnect()
        except Exception:
            pass

    was_connected = _state.is_connected
    _state = ConnectionState()

    return {
        "status": "disconnected",
        "was_connected": was_connected,
    }
