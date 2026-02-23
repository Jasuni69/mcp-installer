"""Find and load TOM .NET DLLs for pythonnet."""

import os
import sys
from pathlib import Path

# DLLs we need
_REQUIRED_DLLS = [
    "Microsoft.AnalysisServices.Core",
    "Microsoft.AnalysisServices.Tabular",
    "Microsoft.AnalysisServices.Tabular.Json",
]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LIB_DIR = _PROJECT_ROOT / "lib"


def _search_paths() -> list[Path]:
    """Return candidate directories that might contain TOM DLLs."""
    paths = [_LIB_DIR]

    # NuGet global cache
    nuget_cache = Path.home() / ".nuget" / "packages"
    if nuget_cache.exists():
        for pkg_dir in nuget_cache.glob("microsoft.analysisservices*"):
            for dll_dir in pkg_dir.rglob("net45"):
                paths.append(dll_dir)

    # SSMS / common install locations
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    ssms_path = Path(program_files) / "Microsoft SQL Server Management Studio 20" / "Common7" / "IDE"
    if ssms_path.exists():
        paths.append(ssms_path)

    return paths


def resolve_tom_dlls() -> dict[str, Path]:
    """Find all required TOM DLLs. Return {name: path} mapping."""
    found: dict[str, Path] = {}
    for search_dir in _search_paths():
        if not search_dir.exists():
            continue
        for dll_name in _REQUIRED_DLLS:
            if dll_name in found:
                continue
            dll_path = search_dir / f"{dll_name}.dll"
            if dll_path.exists():
                found[dll_name] = dll_path
        if len(found) == len(_REQUIRED_DLLS):
            break

    missing = set(_REQUIRED_DLLS) - set(found.keys())
    if missing:
        searched = [str(p) for p in _search_paths() if p.exists()]
        raise RuntimeError(
            f"Missing TOM DLLs: {', '.join(missing)}\n"
            f"Searched: {', '.join(searched)}\n"
            f"Download via NuGet: Microsoft.AnalysisServices.retail.amd64"
        )
    return found


def load_tom() -> None:
    """Load TOM DLLs into the CLR. Must call before importing TOM types."""
    import clr  # noqa: E402

    dll_map = resolve_tom_dlls()
    for name, path in dll_map.items():
        # Add parent dir to path so dependencies resolve
        parent = str(path.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        clr.AddReference(str(path.with_suffix("")))
