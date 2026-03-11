"""
Constants for the MCP Server Installer.
Server definitions, URLs, paths, and theme tokens.
"""
import platform
import subprocess
from pathlib import Path

from mcp_installer import __version__

# ── Subprocess ────────────────────────────────────────────────────────────────
# Prevent console windows from flashing on Windows when spawning subprocesses
CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

# ── GitHub URLs ───────────────────────────────────────────────────────────────
GITHUB_OWNER = "Jasuni69"
GITHUB_REPO = "mcp-installer"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

# ── Local paths ───────────────────────────────────────────────────────────────
DEFAULT_INSTALL_DIR = str(Path.home() / ".mcp-servers")
VERSIONS_FILE = "versions.json"  # stored inside install_dir

# ── Server definitions ────────────────────────────────────────────────────────
SERVERS = {
    "fabric": {
        "label": "Fabric Core (138+ tools)",
        "desc": "Workspaces, lakehouses, SQL, DAX, notebooks, pipelines, OneLake, Git, CI/CD",
        "dir": "fabric-core",
        "run": ["run", "fabric_mcp_stdio.py"],
        "needs_az": True,
    },
    "powerbi": {
        "label": "Power BI Modeling",
        "desc": "Live semantic model editing in Power BI Desktop — measures, translations, metadata",
        "dir": "powerbi-modeling",
        "run": ["run", "python", "-m", "powerbi_modeling_mcp"],
        "needs_az": False,
    },
    "translation": {
        "label": "Translation Audit",
        "desc": "Scan Power BI reports for untranslated content, PASS/FAIL verdict",
        "dir": "translation-audit",
        "run": ["run", "python", "server.py"],
        "needs_az": False,
    },
    "azure_sql": {
        "label": "Azure SQL",
        "desc": "Query, analyze, and manage Azure SQL databases",
        "dir": "azure-sql",
        "run": ["run", "python", "-m", "azure_sql_mcp"],
        "needs_az": True,
    },
}

# ── Fabric item types ─────────────────────────────────────────────────────────
FABRIC_ITEM_SUFFIXES = (
    ".Notebook", ".Lakehouse", ".SemanticModel", ".Report",
    ".DataPipeline", ".Warehouse", ".SQLEndpoint", ".Eventhouse",
    ".Environment", ".KQLDatabase", ".MLModel", ".MLExperiment",
)

# ── Prerequisite winget IDs / download URLs ───────────────────────────────────
PREREQ_FIXES = {
    "uv":          ("astral-sh.uv",               "https://docs.astral.sh/uv/getting-started/installation/"),
    "git":         ("Git.Git",                     "https://git-scm.com/download/win"),
    "azure_cli":   ("Microsoft.AzureCLI",          "https://aka.ms/installazurecliwindows"),
    "azure_auth":  (None,                           None),
    "dotnet9":     ("Microsoft.DotNet.Runtime.9",  "https://aka.ms/dotnet/download"),
    "odbc_driver": (None,                           "https://aka.ms/odbc18"),
}

# ── Theme tokens (Catppuccin Mocha) ───────────────────────────────────────────
class Theme:
    BG          = "#1e1e2e"
    CARD        = "#252536"
    CARD_BORDER = "#313244"
    FG          = "#cdd6f4"
    ACCENT      = "#89b4fa"
    WARN        = "#f38ba8"
    OK          = "#a6e3a1"
    MUTED       = "#9399b2"
    OVERLAY     = "#45475a"
    SURFACE     = "#313244"
    DARK        = "#181825"
    BASE_DARK   = "#11111b"
    TEAL        = "#89dceb"

    FONT        = ("Segoe UI", 11)
    FONT_BOLD   = ("Segoe UI", 11, "bold")
    FONT_HEADER = ("Segoe UI", 13, "bold")
    FONT_MONO   = ("Consolas", 10)
    FONT_SMALL  = ("Segoe UI", 9)
    FONT_LINK   = ("Consolas", 10, "underline")
