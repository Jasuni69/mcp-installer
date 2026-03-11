"""
Prerequisite detection and installation.

Checks for: uv, git, Azure CLI, Azure auth, ODBC Driver 18, .NET 9.x
Installs missing prereqs via winget (with fallback to browser).

Failure modes handled:
- subprocess.check_output timeouts → caught, returns (False, "Check failed")
- Executable not found → returns (False, "Not found")
- winget not available → falls back to opening browser URL
- winget install fails → falls back to browser URL
- Registry not accessible (ODBC check) → returns (False, "Not found")
"""
import platform
import subprocess
from typing import Callable

from mcp_installer.constants import CREATION_FLAGS, PREREQ_FIXES
from mcp_installer.path_manager import find_executable, refresh_process_path, broadcast_env_change


def check_prereqs() -> dict:
    """Check all prerequisites.

    Returns dict of name -> (ok: bool, detail: str).
    Special key '_tenant_id' holds the Azure tenant ID if found.
    """
    results: dict = {}

    # ── uv ────────────────────────────────────────────────────────────────
    uv = find_executable("uv")
    if uv:
        try:
            out = subprocess.check_output(
                [uv, "--version"], stderr=subprocess.STDOUT, text=True,
                creationflags=CREATION_FLAGS
            ).strip()
            results["uv"] = (True, out)
        except Exception:
            results["uv"] = (True, uv)
    else:
        results["uv"] = (False, "Not found")

    # ── git ───────────────────────────────────────────────────────────────
    git = find_executable("git")
    if git:
        try:
            out = subprocess.check_output(
                [git, "--version"], stderr=subprocess.STDOUT, text=True,
                creationflags=CREATION_FLAGS
            ).strip()
            results["git"] = (True, out)
        except Exception:
            results["git"] = (True, git)
    else:
        results["git"] = (False, "Not found — optional (used for git integration)")

    # ── Azure CLI ─────────────────────────────────────────────────────────
    az = find_executable("az") or find_executable("az.cmd")
    if az:
        try:
            out = subprocess.check_output(
                [az, "--version"], stderr=subprocess.STDOUT, text=True,
                timeout=10, creationflags=CREATION_FLAGS
            )
            ver_line = out.split("\n")[0].strip()
            results["azure_cli"] = (True, ver_line)
        except Exception:
            results["azure_cli"] = (True, az)
    else:
        results["azure_cli"] = (False, "Not found — install from https://aka.ms/installazurecliwindows")

    # ── Azure auth + tenant ID ────────────────────────────────────────────
    if az:
        try:
            subprocess.check_output(
                [az, "account", "get-access-token"],
                stderr=subprocess.STDOUT, text=True, timeout=10,
                creationflags=CREATION_FLAGS
            )
            tenant_id = ""
            try:
                acct = subprocess.check_output(
                    [az, "account", "show", "--query", "tenantId", "-o", "tsv"],
                    stderr=subprocess.STDOUT, text=True, timeout=10,
                    creationflags=CREATION_FLAGS
                ).strip()
                tenant_id = acct
            except Exception:
                pass
            detail = f"Authenticated — tenant {tenant_id}" if tenant_id else "Authenticated"
            results["azure_auth"] = (True, detail)
            results["_tenant_id"] = tenant_id
        except subprocess.CalledProcessError:
            results["azure_auth"] = (False, "Not logged in — run: az login")
        except Exception:
            results["azure_auth"] = (False, "Check failed")
    else:
        results["azure_auth"] = (False, "Azure CLI not found")

    # ── ODBC Driver 18 ───────────────────────────────────────────────────
    results["odbc_driver"] = _check_odbc()

    # ── .NET 9.x runtime ─────────────────────────────────────────────────
    results["dotnet9"] = _check_dotnet9()

    return results


def _check_odbc() -> tuple[bool, str]:
    """Check for ODBC Driver 17 or 18 for SQL Server."""
    if platform.system() == "Windows":
        try:
            import winreg
            key_path = r"SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                i = 0
                while True:
                    try:
                        name, _, _ = winreg.EnumValue(key, i)
                        if "ODBC Driver 18" in name or "ODBC Driver 17" in name:
                            return (True, name)
                        i += 1
                    except OSError:
                        break
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(
                ["odbcinst", "-q", "-d"], stderr=subprocess.STDOUT, text=True,
                creationflags=CREATION_FLAGS
            )
            if "ODBC Driver 18" in out or "ODBC Driver 17" in out:
                return (True, "Found")
        except Exception:
            pass

    return (False, "Not found — needed for Azure SQL (download from Microsoft)")


def _check_dotnet9() -> tuple[bool, str]:
    """Check for .NET 9.x runtime (required by powerbi-modeling)."""
    from pathlib import Path

    dotnet_candidates: list[str] = []
    d = find_executable("dotnet")
    if d:
        dotnet_candidates.append(d)
    system_dotnet = r"C:\Program Files\dotnet\dotnet.exe"
    if Path(system_dotnet).exists() and system_dotnet not in dotnet_candidates:
        dotnet_candidates.append(system_dotnet)

    for dotnet in dotnet_candidates:
        try:
            out = subprocess.check_output(
                [dotnet, "--list-runtimes"], stderr=subprocess.STDOUT,
                text=True, timeout=10, creationflags=CREATION_FLAGS
            )
            for line in out.splitlines():
                if ("9." in line and
                        ("Microsoft.NETCore.App" in line or
                         "Microsoft.WindowsDesktop.App" in line)):
                    return (True, line.strip())
        except Exception:
            pass

    if dotnet_candidates:
        return (False, "No 9.x runtime found — run: winget install Microsoft.DotNet.Runtime.9")
    return (False, "Not found — needed for Power BI Modeling (https://aka.ms/dotnet/download)")


# ── Prerequisite Installation ─────────────────────────────────────────────────

def install_prereq_winget(
    winget_id: str,
    log_callback: Callable[[str], None] | None = None,
) -> bool:
    """Install a single prerequisite via winget.

    Returns True if installation succeeded, False otherwise.
    """
    winget = find_executable("winget")
    if not winget:
        return False

    if log_callback:
        log_callback(f"Installing {winget_id} via winget...")

    try:
        proc = subprocess.Popen(
            [winget, "install", "--id", winget_id, "--silent",
             "--accept-source-agreements", "--accept-package-agreements"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=CREATION_FLAGS
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line and log_callback:
                log_callback(f"  {line}")
        proc.wait(timeout=600)  # 10 min max per prereq

        if proc.returncode == 0:
            # Refresh PATH so the newly installed tool is found
            refresh_process_path()
            broadcast_env_change()
            if log_callback:
                log_callback(f"✓ Installed {winget_id}")
            return True
        else:
            if log_callback:
                log_callback(f"✗ winget returned exit code {proc.returncode}")
            return False

    except subprocess.TimeoutExpired:
        if log_callback:
            log_callback(f"✗ {winget_id} install timed out")
        return False
    except Exception as ex:
        if log_callback:
            log_callback(f"✗ {winget_id} install failed: {ex}")
        return False


def install_all_missing(
    prereqs: dict,
    log_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, bool]:
    """Install all missing prerequisites that have winget IDs.

    Args:
        prereqs: Result from check_prereqs()
        log_callback: Called with log messages
        progress_callback: Called with (current, total, label)

    Returns:
        dict of prereq_key -> success (only for prereqs that were attempted)
    """
    # Figure out what needs installing
    to_install: list[tuple[str, str]] = []  # (key, winget_id)
    for key, (ok, _detail) in prereqs.items():
        if key.startswith("_"):
            continue
        if ok:
            continue
        winget_id, _url = PREREQ_FIXES.get(key, (None, None))
        if winget_id:
            to_install.append((key, winget_id))

    if not to_install:
        if log_callback:
            log_callback("All prerequisites are already installed!")
        return {}

    results: dict[str, bool] = {}
    total = len(to_install)

    for i, (key, winget_id) in enumerate(to_install):
        if progress_callback:
            progress_callback(i, total, f"Installing {winget_id}...")
        success = install_prereq_winget(winget_id, log_callback)
        results[key] = success

    if progress_callback:
        progress_callback(total, total, "Prerequisites done")

    # Final PATH refresh + broadcast
    refresh_process_path()
    broadcast_env_change()

    return results


def run_az_login(
    log_callback: Callable[[str], None] | None = None,
) -> bool:
    """Launch 'az login' (opens browser for auth).

    Returns True if login succeeded.
    """
    az = find_executable("az") or find_executable("az.cmd")
    if not az:
        if log_callback:
            log_callback("Azure CLI not found — cannot sign in")
        return False

    if log_callback:
        log_callback("Opening Azure login in browser...")

    try:
        proc = subprocess.Popen(
            [az, "login"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=CREATION_FLAGS
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line and log_callback:
                log_callback(f"  {line}")
        proc.wait(timeout=120)
        return proc.returncode == 0
    except Exception:
        return False


def load_az_accounts() -> list[dict]:
    """Fetch cached Azure account list.

    Returns list of account dicts with keys: name, id, tenantId, user, isDefault.
    Returns empty list on failure.
    """
    import json
    az = find_executable("az") or find_executable("az.cmd")
    if not az:
        return []

    try:
        out = subprocess.check_output(
            [az, "account", "list", "--query",
             "[].{name:name, id:id, tenantId:tenantId, user:user.name, isDefault:isDefault}",
             "-o", "json"],
            stderr=subprocess.STDOUT, text=True, timeout=10,
            creationflags=CREATION_FLAGS
        )
        return json.loads(out)
    except Exception:
        return []
