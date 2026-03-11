"""
PATH management: find executables, refresh process PATH, broadcast environment changes.

Failure modes handled:
- Registry keys missing or inaccessible → caught by try/except
- SendMessageTimeout failing → non-fatal, wrapped in try/except
- Non-Windows platforms → functions are no-ops or return early
"""
import os
import platform
import shutil
from pathlib import Path


def find_executable(name: str) -> str | None:
    """Find an executable, checking PATH and common Windows install dirs.

    Returns the full path to the executable, or None if not found.
    """
    found = shutil.which(name)
    if found:
        return found

    if platform.system() != "Windows":
        return None

    # Extra locations for Windows fresh installs where PATH hasn't been
    # refreshed yet in the current process
    appdata = os.environ.get("LOCALAPPDATA", "")
    extra: list[str] = [
        str(Path(appdata) / "Programs" / "uv" / f"{name}.exe"),
        str(Path.home() / ".local" / "bin" / f"{name}.exe"),
        str(Path.home() / ".cargo" / "bin" / f"{name}.exe"),
    ]
    if name in ("az", "az.cmd"):
        extra += [
            r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
            r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        ]
    if name == "dotnet":
        extra.append(r"C:\Program Files\dotnet\dotnet.exe")
    if name == "git":
        extra += [
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files (x86)\Git\cmd\git.exe",
        ]

    for path in extra:
        if Path(path).exists():
            return path
    return None


def refresh_process_path() -> list[str]:
    """Merge registry PATH entries into the current process PATH.

    Returns a list of newly added path entries (for logging/testing).
    On non-Windows, returns an empty list.
    """
    if platform.system() != "Windows":
        return []

    new_parts: list[str] = []
    try:
        import winreg

        current = set(os.environ.get("PATH", "").split(";"))
        for hive, subkey in [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ]:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "Path")
                    for p in val.split(";"):
                        p = p.strip()
                        if p and p not in current:
                            new_parts.append(p)
                            current.add(p)
            except FileNotFoundError:
                pass

        if new_parts:
            os.environ["PATH"] = os.environ.get("PATH", "") + ";" + ";".join(new_parts)
    except Exception:
        pass

    return new_parts


def broadcast_env_change() -> bool:
    """Broadcast WM_SETTINGCHANGE to notify other apps that PATH changed.

    This makes newly opened terminals and apps pick up the updated PATH
    without requiring a logoff/restart.

    Returns True if the broadcast was sent successfully, False otherwise.
    """
    if platform.system() != "Windows":
        return False

    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,  # 5 second timeout
            ctypes.byref(result),
        )
        return True
    except Exception:
        return False


def set_dpi_awareness() -> bool:
    """Enable DPI awareness so the app renders crisply on high-DPI displays.

    Should be called BEFORE creating any tkinter windows.
    Returns True if DPI awareness was set successfully.
    """
    if platform.system() != "Windows":
        return False

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # System DPI aware
        return True
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
            return True
        except Exception:
            return False
