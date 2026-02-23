"""
MCP Server Installer
Installs fabric-core, powerbi-modeling, translation-audit, and azure-sql MCP servers.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, scrolledtext, ttk

try:
    import requests
    from packaging.version import Version
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

__version__ = "1.0.0"

MCP_REPO = "https://github.com/Jasuni69/mcp-installer"
MCP_REPO_ZIP = "https://github.com/Jasuni69/mcp-installer/archive/refs/heads/main.zip"
INSTALLER_REPO_API = "https://api.github.com/repos/Jasuni69/mcp-installer/releases/latest"
DEFAULT_INSTALL_DIR = str(Path.home() / ".mcp-servers")

SERVERS = {
    "fabric": {
        "label": "Fabric Core (138+ tools)",
        "dir": "fabric-core",
        "run": ["run", "fabric_mcp_stdio.py"],
        "needs_az": True,
    },
    "powerbi": {
        "label": "Power BI Modeling",
        "dir": "powerbi-modeling",
        "run": ["run", "python", "-m", "powerbi_modeling_mcp"],
        "needs_az": False,
    },
    "translation": {
        "label": "Translation Audit",
        "dir": "translation-audit",
        "run": ["run", "python", "server.py"],
        "needs_az": False,
    },
    "azure_sql": {
        "label": "Azure SQL",
        "dir": "azure-sql",
        "run": ["run", "python", "-m", "azure_sql_mcp"],
        "needs_az": True,
    },
}


def find_executable(name: str) -> str | None:
    """Find an executable, checking PATH and common install dirs."""
    found = shutil.which(name)
    if found:
        return found
    # Extra locations for Windows fresh installs
    extra = []
    if platform.system() == "Windows":
        appdata = os.environ.get("LOCALAPPDATA", "")
        extra = [
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
            extra += [
                r"C:\Program Files\dotnet\dotnet.exe",
            ]
        if name == "git":
            extra += [
                r"C:\Program Files\Git\cmd\git.exe",
                r"C:\Program Files (x86)\Git\cmd\git.exe",
            ]
    for path in extra:
        if Path(path).exists():
            return path
    return None


def check_prereqs() -> dict:
    """Check all prerequisites. Returns dict of name -> (ok, detail)."""
    results = {}

    # uv
    uv = find_executable("uv")
    if uv:
        try:
            out = subprocess.check_output([uv, "--version"], stderr=subprocess.STDOUT, text=True).strip()
            results["uv"] = (True, out)
        except Exception:
            results["uv"] = (True, uv)
    else:
        results["uv"] = (False, "Not found")

    # git
    git = find_executable("git")
    if git:
        try:
            out = subprocess.check_output([git, "--version"], stderr=subprocess.STDOUT, text=True).strip()
            results["git"] = (True, out)
        except Exception:
            results["git"] = (True, git)
    else:
        results["git"] = (False, "Not found")

    # Azure CLI
    az = find_executable("az") or find_executable("az.cmd")
    if az:
        try:
            out = subprocess.check_output([az, "--version"], stderr=subprocess.STDOUT, text=True, timeout=10)
            ver_line = out.split("\n")[0].strip()
            results["azure_cli"] = (True, ver_line)
        except Exception:
            results["azure_cli"] = (True, az)
    else:
        results["azure_cli"] = (False, "Not found — install from https://aka.ms/installazurecliwindows")

    # Azure auth + tenant ID
    if az:
        try:
            subprocess.check_output(
                [az, "account", "get-access-token"],
                stderr=subprocess.STDOUT, text=True, timeout=10
            )
            # Fetch tenant ID from current account
            tenant_id = ""
            try:
                acct = subprocess.check_output(
                    [az, "account", "show", "--query", "tenantId", "-o", "tsv"],
                    stderr=subprocess.STDOUT, text=True, timeout=10
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

    # ODBC Driver 18
    odbc_ok = False
    odbc_detail = "Not found"
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
                            odbc_ok = True
                            odbc_detail = name
                            break
                        i += 1
                    except OSError:
                        break
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(["odbcinst", "-q", "-d"], stderr=subprocess.STDOUT, text=True)
            if "ODBC Driver 18" in out or "ODBC Driver 17" in out:
                odbc_ok = True
                odbc_detail = "Found"
        except Exception:
            pass

    if not odbc_ok:
        odbc_detail = "Not found — needed for Azure SQL (download from Microsoft)"
    results["odbc_driver"] = (odbc_ok, odbc_detail)

    # .NET 9.x runtime (required by powerbi-modeling)
    dotnet_ok = False
    dotnet_detail = "Not found — needed for Power BI Modeling (https://aka.ms/dotnet/download)"
    dotnet = find_executable("dotnet")
    if dotnet:
        try:
            out = subprocess.check_output(
                [dotnet, "--list-runtimes"], stderr=subprocess.STDOUT, text=True, timeout=10
            )
            for line in out.splitlines():
                # Match "Microsoft.NETCore.App 9.x.x" or "Microsoft.WindowsDesktop.App 9.x.x"
                if ("9." in line and
                        ("Microsoft.NETCore.App" in line or "Microsoft.WindowsDesktop.App" in line)):
                    dotnet_ok = True
                    dotnet_detail = line.strip()
                    break
            if not dotnet_ok:
                dotnet_detail = "No 9.x runtime found — run: winget install Microsoft.DotNet.Runtime.9"
        except Exception:
            pass
    results["dotnet9"] = (dotnet_ok, dotnet_detail)

    return results


def check_for_update() -> tuple[bool, str, str]:
    """Check GitHub for newer installer version. Returns (available, version, url)."""
    if not HAS_REQUESTS:
        return False, "", ""
    try:
        resp = requests.get(INSTALLER_REPO_API, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            url = data.get("html_url", "")
            if latest and Version(latest) > Version(__version__):
                return True, latest, url
    except Exception:
        pass
    return False, "", ""


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"MCP Server Installer  v{__version__}")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")

        self._install_dir = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self._server_vars = {k: tk.BooleanVar(value=(k != "azure_sql")) for k in SERVERS}
        self._client_desktop = tk.BooleanVar(value=True)
        self._client_code = tk.BooleanVar(value=True)
        self._az_server = tk.StringVar()
        self._az_database = tk.StringVar()
        self._az_auth = tk.StringVar(value="az_cli")
        self._az_user = tk.StringVar()
        self._az_password = tk.StringVar()
        self._notebook_template = tk.StringVar()
        self._code_scope = tk.StringVar(value="global")
        self._project_dir = tk.StringVar()
        self._az_tenant_id = tk.StringVar()

        self._prereqs: dict = {}
        self._installing = False

        self._build_ui()
        self._refresh_prereqs()
        self._toggle_azure_sql_fields()
        self._toggle_code_scope()
        self._update_install_btn()

        # Check for update in background
        threading.Thread(target=self._check_update_bg, daemon=True).start()

    # ── UI BUILD ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        PAD = {"padx": 12, "pady": 6}
        BG = "#1e1e2e"
        FG = "#cdd6f4"
        ACCENT = "#89b4fa"
        WARN = "#f38ba8"
        OK_COL = "#a6e3a1"

        FONT = ("Segoe UI", 11)
        FONT_MONO = ("Consolas", 10)

        self._style = ttk.Style(self)
        self._style.theme_use("clam")
        self._style.configure("TFrame", background=BG)
        self._style.configure("TLabel", background=BG, foreground=FG, font=FONT)
        self._style.configure("TCheckbutton", background=BG, foreground=FG, font=FONT)
        self._style.configure("TEntry", fieldbackground="#313244", foreground=FG, font=FONT)
        self._style.configure("TButton", background="#313244", foreground=FG, font=FONT)
        self._style.configure("Accent.TButton", background=ACCENT, foreground=BG, font=FONT)
        self._style.configure("TCombobox", fieldbackground="#313244", foreground=FG, font=FONT)
        self._style.configure("Horizontal.TProgressbar", troughcolor="#313244", background=ACCENT)

        self._font = FONT
        self._font_mono = FONT_MONO

        self._ok_col = OK_COL
        self._warn_col = WARN
        self._accent = ACCENT
        self._fg = FG
        self._bg = BG

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        main = ttk.Frame(self, padding=16)
        main.grid(sticky="nsew")
        main.columnconfigure(1, weight=1)

        row = 0

        # Update banner (hidden initially)
        self._update_frame = ttk.Frame(main)
        self._update_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self._update_frame.grid_remove()
        self._update_label = ttk.Label(self._update_frame, foreground=WARN)
        self._update_label.pack(side="left")
        self._update_link = tk.Label(self._update_frame, foreground=ACCENT, cursor="hand2", bg=BG)
        self._update_link.pack(side="left", padx=8)
        row += 1

        # Install dir
        ttk.Label(main, text="MCP tools folder:").grid(row=row, column=0, sticky="w", **PAD)
        ttk.Entry(main, textvariable=self._install_dir, width=40).grid(row=row, column=1, sticky="ew", **PAD)
        ttk.Button(main, text="Browse", command=self._browse_dir).grid(row=row, column=2, **PAD)
        row += 1
        ttk.Label(main, text="MCP tools are stored here permanently — do not delete this folder.",
                  foreground="#6c7086").grid(row=row, column=1, columnspan=2, sticky="w", padx=12)
        row += 1

        ttk.Separator(main, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        # Clients
        ttk.Label(main, text="Claude clients:").grid(row=row, column=0, sticky="w", **PAD)
        row += 1
        ttk.Checkbutton(main, text="Claude Desktop", variable=self._client_desktop,
                        command=self._update_install_btn).grid(row=row, column=0, columnspan=2, sticky="w", padx=24)
        row += 1
        ttk.Checkbutton(main, text="Claude Code", variable=self._client_code,
                        command=self._on_client_toggle).grid(row=row, column=0, columnspan=2, sticky="w", padx=24)
        row += 1

        # Claude Code scope (global vs project)
        self._scope_frame = ttk.Frame(main)
        self._scope_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=40)
        row += 1
        scope_inner = ttk.Frame(self._scope_frame)
        scope_inner.pack(fill="x")
        ttk.Radiobutton(scope_inner, text="Global (all projects)",
                        variable=self._code_scope, value="global",
                        command=self._toggle_code_scope).pack(side="left", padx=4)
        ttk.Radiobutton(scope_inner, text="Project only",
                        variable=self._code_scope, value="project",
                        command=self._toggle_code_scope).pack(side="left", padx=4)
        self._project_picker = ttk.Frame(self._scope_frame)
        self._project_picker.pack(fill="x", pady=2)
        ttk.Label(self._project_picker, text="Project folder:").pack(side="left", padx=4)
        ttk.Entry(self._project_picker, textvariable=self._project_dir, width=30).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(self._project_picker, text="Browse",
                   command=self._browse_project).pack(side="left", padx=4)

        ttk.Separator(main, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        # Servers
        ttk.Label(main, text="MCP Servers:").grid(row=row, column=0, sticky="w", **PAD)
        row += 1
        for key, srv in SERVERS.items():
            cb = ttk.Checkbutton(main, text=srv["label"], variable=self._server_vars[key],
                                 command=self._on_server_toggle)
            cb.grid(row=row, column=0, columnspan=3, sticky="w", padx=24)
            row += 1

        # Azure SQL fields (shown when azure_sql checked)
        self._az_frame = ttk.Frame(main)
        self._az_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=40)
        row += 1

        az_inner = ttk.Frame(self._az_frame)
        az_inner.pack(fill="x")

        ttk.Label(az_inner, text="Server:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(az_inner, textvariable=self._az_server, width=35).grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(az_inner, text="Database:").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(az_inner, textvariable=self._az_database, width=35).grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(az_inner, text="Auth:").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        auth_combo = ttk.Combobox(az_inner, textvariable=self._az_auth, values=["az_cli", "sql"],
                                  state="readonly", width=10)
        auth_combo.grid(row=2, column=1, sticky="w", pady=2)
        auth_combo.bind("<<ComboboxSelected>>", lambda e: self._toggle_sql_creds())

        self._sql_cred_frame = ttk.Frame(az_inner)
        self._sql_cred_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
        ttk.Label(self._sql_cred_frame, text="Username:").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Entry(self._sql_cred_frame, textvariable=self._az_user, width=35).grid(row=0, column=1, sticky="ew")
        ttk.Label(self._sql_cred_frame, text="Password:").grid(row=1, column=0, sticky="w", padx=4)
        ttk.Entry(self._sql_cred_frame, textvariable=self._az_password, show="*", width=35).grid(row=1, column=1, sticky="ew")

        ttk.Separator(main, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        # Notebook template (optional)
        ttk.Label(main, text="Notebook template:").grid(row=row, column=0, sticky="w", **PAD)
        ttk.Entry(main, textvariable=self._notebook_template, width=34,
                  state="readonly").grid(row=row, column=1, sticky="ew", **PAD)
        nb_btn_frame = ttk.Frame(main)
        nb_btn_frame.grid(row=row, column=2, **PAD)
        ttk.Button(nb_btn_frame, text="Browse", command=self._browse_notebook).pack(side="left", padx=2)
        ttk.Button(nb_btn_frame, text="Clear", command=lambda: self._notebook_template.set("")).pack(side="left", padx=2)
        ttk.Label(main, text="Optional — Claude uses default notebook style if not set.",
                  foreground="#6c7086").grid(row=row + 1, column=1, columnspan=2, sticky="w", padx=12)
        row += 2

        ttk.Separator(main, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        # Fabric project setup
        ttk.Label(main, text="Fabric project:").grid(row=row, column=0, sticky="w", **PAD)
        self._fabric_project_dir = tk.StringVar()
        fp_frame = ttk.Frame(main)
        fp_frame.grid(row=row, column=1, columnspan=2, sticky="ew", **PAD)
        ttk.Entry(fp_frame, textvariable=self._fabric_project_dir, width=34,
                  state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(fp_frame, text="Browse", command=self._browse_fabric_project).pack(side="left", padx=4)
        ttk.Button(fp_frame, text="Clear", command=lambda: self._fabric_project_dir.set("")).pack(side="left", padx=2)
        row += 1
        self._fabric_status = ttk.Label(main, text="Optional — auto-detects Fabric items and writes CLAUDE.md to project root.",
                  foreground="#6c7086")
        self._fabric_status.grid(row=row, column=1, columnspan=2, sticky="w", padx=12)
        row += 1

        ttk.Separator(main, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        # Prerequisites
        prereq_header = ttk.Frame(main)
        prereq_header.grid(row=row, column=0, sticky="nw", **PAD)
        ttk.Label(prereq_header, text="Prerequisites:").pack(side="left")
        ttk.Button(prereq_header, text="↻ Refresh", command=self._refresh_prereqs).pack(side="left", padx=8)
        self._prereq_frame = ttk.Frame(main)
        self._prereq_frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=4, pady=4)
        row += 1

        # Azure account picker
        ttk.Label(main, text="Azure account:").grid(row=row, column=0, sticky="w", **PAD)
        self._az_account_combo = ttk.Combobox(main, state="readonly", width=50)
        self._az_account_combo.grid(row=row, column=1, columnspan=2, sticky="ew", **PAD)
        self._az_account_combo.bind("<<ComboboxSelected>>", lambda e: self._on_account_selected())
        self._az_accounts = []  # list of {user, tenantId, isDefault}
        row += 1

        ttk.Separator(main, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        # Persistent info note
        note = tk.Label(main,
            text="ℹ  If you installed any prerequisite above, close ALL VSCode windows\n"
                 "    and reopen before using Claude Code. VSCode only reads PATH at launch.\n"
                 "    For Claude Desktop: fully quit (system tray) and reopen,\n"
                 "    then check Settings ▸ Connectors to verify MCP tools are loaded.\n"
                 "    Azure tokens expire — if MCP tools stop working, run 'az login' again.",
            fg="#89b4fa", bg=BG, font=("Consolas", 9), justify="left", anchor="w")
        note.grid(row=row, column=0, columnspan=3, sticky="ew", padx=12, pady=4)
        row += 1

        # Progress
        self._progress = ttk.Progressbar(main, mode="determinate", length=460,
                                         style="Horizontal.TProgressbar")
        self._progress.grid(row=row, column=0, columnspan=3, sticky="ew", padx=12, pady=4)
        row += 1

        self._log = scrolledtext.ScrolledText(main, width=60, height=8, state="disabled",
                                               bg="#181825", fg=FG, font=("Consolas", 10),
                                               insertbackground=FG)
        self._log.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=12, pady=4)
        main.rowconfigure(row, weight=1)
        row += 1

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=12, pady=8)
        self._force_reinstall = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_frame, text="Force reinstall",
                        variable=self._force_reinstall).pack(side="left", padx=4)
        self._cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self._on_cancel)
        self._cancel_btn.pack(side="right", padx=4)
        self._install_btn = ttk.Button(btn_frame, text="Install", style="Accent.TButton",
                                       command=self._on_install)
        self._install_btn.pack(side="right", padx=4)
        self._update_btn = ttk.Button(btn_frame, text="Update MCP Tools",
                                       command=self._on_update)
        self._update_btn.pack(side="left", padx=4)

    # ── PREREQ PANEL ──────────────────────────────────────────────────────────

    # Maps prereq key -> (winget_id_or_None, fallback_url)
    PREREQ_FIXES = {
        "uv":         ("astral-sh.uv",               "https://docs.astral.sh/uv/getting-started/installation/"),
        "git":        ("Git.Git",                    "https://git-scm.com/download/win"),
        "azure_cli":  ("Microsoft.AzureCLI",         "https://aka.ms/installazurecliwindows"),
        "azure_auth": (None,                          None),   # handled separately
        "dotnet9":    ("Microsoft.DotNet.Runtime.9", "https://aka.ms/dotnet/download"),
        "odbc_driver":(None,                          "https://aka.ms/odbc18"),
    }

    @staticmethod
    def _refresh_path():
        """Re-read PATH from Windows registry so newly installed tools are found."""
        if platform.system() != "Windows":
            return
        try:
            import winreg
            parts = []
            for hive, subkey in [
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                (winreg.HKEY_CURRENT_USER, r"Environment"),
            ]:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        val, _ = winreg.QueryValueEx(key, "Path")
                        parts.append(val)
                except FileNotFoundError:
                    pass
            if parts:
                os.environ["PATH"] = ";".join(parts)
        except Exception:
            pass

    def _load_az_accounts(self):
        """Fetch cached Azure accounts and populate the dropdown."""
        az = find_executable("az") or find_executable("az.cmd")
        if not az:
            self._az_account_combo.config(values=["(Azure CLI not installed)"])
            return
        try:
            out = subprocess.check_output(
                [az, "account", "list", "--query",
                 "[].{name:name, id:id, tenantId:tenantId, user:user.name, isDefault:isDefault}",
                 "-o", "json"],
                stderr=subprocess.STDOUT, text=True, timeout=10
            )
            accounts = json.loads(out)
            if not accounts:
                self._az_account_combo.config(values=["(no accounts — run Sign in)"])
                return
            self._az_accounts = accounts
            display = []
            default_idx = 0
            for i, acct in enumerate(accounts):
                user = acct.get("user", "unknown")
                tid = acct.get("tenantId", "")
                marker = " ★" if acct.get("isDefault") else ""
                display.append(f"{user} — {tid[:8]}...{marker}")
                if acct.get("isDefault"):
                    default_idx = i
            self._az_account_combo.config(values=display)
            self._az_account_combo.current(default_idx)
            self._on_account_selected()
        except Exception:
            self._az_account_combo.config(values=["(could not list accounts)"])

    def _on_account_selected(self):
        """Set tenant/subscription ID from selected account and update prereq display."""
        idx = self._az_account_combo.current()
        if idx < 0 or idx >= len(self._az_accounts):
            return
        acct = self._az_accounts[idx]
        tid = acct.get("tenantId", "")
        sid = acct.get("id", "")
        self._az_tenant_id.set(tid)
        self._az_subscription_id = sid
        if hasattr(self, "_auth_detail_label") and tid:
            self._auth_detail_label.config(text=f"Authenticated — tenant {tid}")

    def _refresh_prereqs(self):
        self._refresh_path()
        for widget in self._prereq_frame.winfo_children():
            widget.destroy()
        self._prereqs = check_prereqs()
        # Auto-populate tenant ID from az account
        tid = self._prereqs.get("_tenant_id", "")
        if tid:
            self._az_tenant_id.set(tid)
        # Refresh account dropdown
        self._load_az_accounts()
        labels = {
            "uv":         "uv",
            "git":        "git",
            "azure_cli":  "Azure CLI",
            "azure_auth": "Azure authenticated",
            "dotnet9":    ".NET 9.x (Power BI Modeling)",
            "odbc_driver":"ODBC Driver 18 (Azure SQL)",
        }
        for i, (key, label) in enumerate(labels.items()):
            ok, detail = self._prereqs.get(key, (False, ""))
            icon = "✓" if ok else "✗"
            color = self._ok_col if ok else self._warn_col

            # Status label
            tk.Label(self._prereq_frame, text=f"{icon} {label}",
                     fg=color, bg=self._bg, font=("Consolas", 10),
                     anchor="w").grid(row=i, column=0, sticky="w")

            # Detail text
            detail_lbl = tk.Label(self._prereq_frame, text=detail,
                     fg="#6c7086", bg=self._bg, font=("Consolas", 9),
                     anchor="w")
            detail_lbl.grid(row=i, column=1, sticky="w", padx=8)
            if key == "azure_auth":
                self._auth_detail_label = detail_lbl

            # Install button for missing prereqs
            if not ok:
                winget_id, url = self.PREREQ_FIXES.get(key, (None, None))
                if key == "azure_auth":
                    btn = tk.Label(self._prereq_frame, text="[ Sign in ]",
                                   fg=self._accent, bg=self._bg,
                                   font=("Consolas", 10), cursor="hand2")
                    btn.grid(row=i, column=2, sticky="w", padx=4)
                    btn.bind("<Button-1>", lambda e: self._az_login())
                elif winget_id:
                    btn = tk.Label(self._prereq_frame, text="[ Install ]",
                                   fg=self._accent, bg=self._bg,
                                   font=("Consolas", 10), cursor="hand2")
                    btn.grid(row=i, column=2, sticky="w", padx=4)
                    btn.bind("<Button-1>", lambda e, w=winget_id, u=url: self._install_prereq(w, u))
                elif url:
                    btn = tk.Label(self._prereq_frame, text="[ Download ]",
                                   fg=self._accent, bg=self._bg,
                                   font=("Consolas", 10), cursor="hand2")
                    btn.grid(row=i, column=2, sticky="w", padx=4)
                    btn.bind("<Button-1>", lambda e, u=url: self._open_url(u))

    def _install_prereq(self, winget_id: str, fallback_url: str):
        """Try winget install; fall back to browser if winget not available."""
        winget = find_executable("winget")
        if not winget:
            self._open_url(fallback_url)
            return

        def _run():
            try:
                proc = subprocess.Popen(
                    [winget, "install", "--id", winget_id, "--silent", "--accept-source-agreements",
                     "--accept-package-agreements"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self.after(0, lambda l=line: self._log_append(f"  {l}"))
                proc.wait()
                if proc.returncode == 0:
                    self.after(0, lambda: self._log_append(f"✓ Installed {winget_id} — re-checking prereqs..."))
                    self.after(500, self._refresh_prereqs)
                else:
                    self.after(0, lambda: self._open_url(fallback_url))
            except Exception as ex:
                self.after(0, lambda: self._open_url(fallback_url))

        self._log_append(f"Installing {winget_id} via winget...")
        threading.Thread(target=_run, daemon=True).start()

    def _az_login(self):
        """Launch 'az login' in a subprocess (opens browser for auth)."""
        az = find_executable("az") or find_executable("az.cmd")
        if not az:
            return

        def _run():
            try:
                proc = subprocess.Popen(
                    [az, "login"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self.after(0, lambda l=line: self._log_append(f"  {l}"))
                proc.wait()
                self.after(500, self._refresh_prereqs)
            except Exception:
                pass

        self._log_append("Opening Azure login in browser...")
        threading.Thread(target=_run, daemon=True).start()

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self._install_dir.get())
        if d:
            self._install_dir.set(d)

    FABRIC_ITEM_SUFFIXES = (
        ".Notebook", ".Lakehouse", ".SemanticModel", ".Report",
        ".DataPipeline", ".Warehouse", ".SQLEndpoint", ".Eventhouse",
        ".Environment", ".KQLDatabase", ".MLModel", ".MLExperiment",
    )

    @staticmethod
    def _scan_fabric_items(root: Path) -> list[dict]:
        """Scan for Fabric items by looking for .platform files or item type suffixes."""
        items = []
        for p in root.rglob(".platform"):
            item_dir = p.parent
            items.append({"name": item_dir.name, "path": str(item_dir)})
        # Also catch folders with known suffixes (some git exports lack .platform)
        for p in root.rglob("item.metadata.json"):
            item_dir = p.parent
            if not any(i["path"] == str(item_dir) for i in items):
                items.append({"name": item_dir.name, "path": str(item_dir)})
        return items

    def _browse_fabric_project(self):
        d = filedialog.askdirectory(title="Select Fabric project folder")
        if not d:
            return
        self._fabric_project_dir.set(d)
        # Scan for Fabric signatures
        found = self._scan_fabric_items(Path(d))
        if found:
            types = set()
            for item in found:
                for sig in self.FABRIC_ITEM_SUFFIXES:
                    if item["name"].endswith(sig):
                        types.add(sig.lstrip("."))
                        break
            type_str = ", ".join(sorted(types)) if types else "items found"
            self._fabric_status.config(
                text=f"✓ Fabric project detected — {type_str} ({len(found)} items)",
                foreground=self._ok_col)
        else:
            self._fabric_status.config(
                text="⚠ No Fabric items detected — are you sure this is a Fabric repo?",
                foreground=self._warn_col)

    def _write_fabric_claude_md(self, project_dir: Path):
        """Write a CLAUDE.md to a Fabric project root so Claude knows the context."""
        claude_md = project_dir / "CLAUDE.md"
        # Scan what item types exist
        found = self._scan_fabric_items(project_dir)
        types_found = set()
        for item in found:
            for sig in self.FABRIC_ITEM_SUFFIXES:
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

        if claude_md.exists():
            existing = claude_md.read_text(encoding="utf-8")
            if "Fabric Project" in existing:
                claude_md.write_text(content, encoding="utf-8")
                return "updated"
            else:
                with open(claude_md, "a", encoding="utf-8") as f:
                    f.write("\n" + content)
                return "appended"
        else:
            claude_md.write_text(content, encoding="utf-8")
            return "created"

    def _browse_project(self):
        d = filedialog.askdirectory(title="Select project folder")
        if d:
            self._project_dir.set(d)

    def _toggle_code_scope(self):
        if self._code_scope.get() == "project":
            self._project_picker.pack(fill="x", pady=2)
        else:
            self._project_picker.pack_forget()

    def _on_client_toggle(self):
        if self._client_code.get():
            self._scope_frame.grid()
        else:
            self._scope_frame.grid_remove()
        self._toggle_code_scope()
        self._update_install_btn()

    def _browse_notebook(self):
        f = filedialog.askopenfilename(
            title="Select notebook template",
            filetypes=[("Jupyter notebooks", "*.ipynb"), ("All files", "*.*")]
        )
        if f:
            self._notebook_template.set(f)

    def _toggle_azure_sql_fields(self):
        if self._server_vars["azure_sql"].get():
            self._az_frame.grid()
        else:
            self._az_frame.grid_remove()
        self._toggle_sql_creds()

    def _on_server_toggle(self):
        self._toggle_azure_sql_fields()
        self._update_install_btn()

    def _toggle_sql_creds(self):
        if self._az_auth.get() == "sql":
            self._sql_cred_frame.grid()
        else:
            self._sql_cred_frame.grid_remove()

    def _update_install_btn(self):
        any_server = any(v.get() for v in self._server_vars.values())
        any_client = self._client_desktop.get() or self._client_code.get()
        self._install_btn.config(state="normal" if (any_server and any_client) else "disabled")

    def _log_append(self, text: str):
        self._log.config(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _check_update_bg(self):
        available, version, url = check_for_update()
        if available:
            self.after(0, lambda: self._show_update_banner(version, url))

    def _show_update_banner(self, version: str, url: str):
        self._update_label.config(text=f"⚠  Update available: v{version}")
        self._update_link.config(text="[Download]")
        self._update_link.bind("<Button-1>", lambda e: self._open_url(url))
        self._update_frame.grid()

    def _open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

    # ── INSTALL ───────────────────────────────────────────────────────────────

    def _on_install(self):
        if self._installing:
            return

        # Validate project dir if project scope selected
        if (self._client_code.get() and self._code_scope.get() == "project"
                and not self._project_dir.get().strip()):
            messagebox.showwarning("Missing fields",
                "Project scope selected but no project folder chosen.")
            return

        # Validate Azure SQL fields if selected
        if self._server_vars["azure_sql"].get():
            srv = self._az_server.get().strip()
            db = self._az_database.get().strip()
            if not srv or not db:
                messagebox.showwarning("Missing fields",
                    "Azure SQL selected but server and/or database is empty.\n\n"
                    "Fill in both fields or uncheck Azure SQL.")
                return
            if self._az_auth.get() == "sql":
                if not self._az_user.get().strip() or not self._az_password.get().strip():
                    messagebox.showwarning("Missing fields",
                        "SQL auth selected but username and/or password is empty.")
                    return

        self._installing = True
        self._install_btn.config(state="disabled")
        self._log_append("Starting installation...")
        threading.Thread(target=self._run_install, daemon=True).start()

    def _on_update(self):
        if self._installing:
            return
        self._installing = True
        self._install_btn.config(state="disabled")
        self._update_btn.config(state="disabled")
        self._log_append("Updating MCP tools from GitHub...")
        threading.Thread(target=self._run_update, daemon=True).start()

    def _run_update(self):
        try:
            install_dir = Path(self._install_dir.get())
            install_dir.mkdir(parents=True, exist_ok=True)
            repo_dir = install_dir / "mcp-installer"
            git = find_executable("git") or "git"
            uv = find_executable("uv") or "uv"

            if (repo_dir / ".git").exists():
                self.after(0, lambda: self._log_append("> git pull..."))
                self._run_cmd([git, "-C", str(repo_dir), "pull"], "git pull")
            else:
                self.after(0, lambda: self._log_append(f"> Cloning {MCP_REPO}..."))
                self._run_cmd([git, "clone", MCP_REPO, str(repo_dir)], "git clone")

            selected_servers = [k for k, v in self._server_vars.items() if v.get()]
            for key in selected_servers:
                srv = SERVERS[key]
                srv_dir = repo_dir / srv["dir"]
                self.after(0, lambda d=srv["dir"]: self._log_append(f"> uv sync {d}..."))
                self._run_cmd([uv, "sync"], f"uv sync {srv['dir']}", cwd=str(srv_dir))

            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("✓ MCP tools updated! Restart Claude Desktop / terminal."))
        except Exception as e:
            self.after(0, lambda: self._log_append(f"ERROR: {e}"))
            self.after(0, lambda: messagebox.showerror("Update Failed", str(e)))
        finally:
            self._installing = False
            self.after(0, lambda: self._install_btn.config(state="normal"))
            self.after(0, lambda: self._update_btn.config(state="normal"))

    def _on_cancel(self):
        self.destroy()

    def _run_install(self):
        try:
            install_dir = Path(self._install_dir.get())
            install_dir.mkdir(parents=True, exist_ok=True)

            selected_servers = [k for k, v in self._server_vars.items() if v.get()]
            total_steps = 1 + len(selected_servers) + 3  # clone + uv sync each + config + agents + notebook
            step = 0

            def progress(n: int, total: int, msg: str):
                pct = int(n / total * 100)
                self.after(0, lambda: self._progress.config(value=pct))
                self.after(0, lambda: self._log_append(f"> {msg}"))

            # Step 1: clone or pull repo
            repo_dir = install_dir / "mcp-installer"
            git = find_executable("git") or "git"
            if (repo_dir / ".git").exists():
                progress(step, total_steps, "Updating repo...")
                self._run_cmd([git, "-C", str(repo_dir), "pull"], "git pull")
            else:
                progress(step, total_steps, f"Cloning {MCP_REPO}...")
                self._run_cmd([git, "clone", MCP_REPO, str(repo_dir)], "git clone")
            step += 1

            # Step 2: uv sync for each server (skip if .venv healthy, unless force)
            uv = find_executable("uv") or "uv"
            force = self._force_reinstall.get()
            for key in selected_servers:
                srv = SERVERS[key]
                srv_dir = repo_dir / srv["dir"]
                venv = srv_dir / ".venv"
                venv_healthy = (venv / "pyvenv.cfg").exists() if venv.exists() else False
                if venv_healthy and not force:
                    progress(step, total_steps, f"{srv['dir']} already synced — skipping")
                else:
                    if force and venv.exists():
                        progress(step, total_steps, f"Removing old .venv for {srv['dir']}...")
                        shutil.rmtree(venv, ignore_errors=True)
                    progress(step, total_steps, f"uv sync {srv['dir']}...")
                    self._run_cmd([uv, "sync"], f"uv sync {srv['dir']}", cwd=str(srv_dir))
                step += 1

            # Step 3: write configs
            progress(step, total_steps, "Writing MCP configs...")
            self._write_configs(repo_dir, selected_servers)
            step += 1

            # Step 4: copy agents if Claude Code selected
            if self._client_code.get():
                progress(step, total_steps, "Copying agents to ~/.claude/agents/...")
                self._copy_agents(repo_dir, selected_servers)
            step += 1

            # Step 5: notebook template (optional)
            nb_path = self._notebook_template.get().strip()
            if nb_path and Path(nb_path).exists():
                progress(step, total_steps, "Installing notebook template...")
                self._install_notebook_template(Path(nb_path))
            step += 1

            # Step 6: Fabric project CLAUDE.md (optional)
            fp_dir = self._fabric_project_dir.get().strip()
            if fp_dir and Path(fp_dir).exists():
                progress(step, total_steps, "Writing Fabric project CLAUDE.md...")
                result = self._write_fabric_claude_md(Path(fp_dir))
                self.after(0, lambda r=result: self._log_append(f"  CLAUDE.md {r}: {fp_dir}/CLAUDE.md"))

            self.after(0, lambda: self._progress.config(value=100))
            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("✓ Installation complete!"))
            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("─── IMPORTANT: %PATH & Restart Info ───"))
            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("  VSCode / Claude Code:"))
            self.after(0, lambda: self._log_append("    VSCode snapshots %PATH when it launches."))
            self.after(0, lambda: self._log_append("    If you just installed uv, git, or Azure CLI,"))
            self.after(0, lambda: self._log_append("    close ALL VSCode windows, then reopen."))
            self.after(0, lambda: self._log_append("    Reloading a window is NOT enough — the"))
            self.after(0, lambda: self._log_append("    PATH snapshot only refreshes on full restart."))
            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("  Claude Desktop:"))
            self.after(0, lambda: self._log_append("    Fully quit Claude Desktop (check system tray)"))
            self.after(0, lambda: self._log_append("    and reopen it to load the new MCP servers."))
            self.after(0, lambda: self._log_append("    Verify: Settings ▸ Connectors — your servers"))
            self.after(0, lambda: self._log_append("    should appear there once loaded."))
            self.after(0, lambda: self._log_append(""))

            msg_parts = [
                "Installation complete!\n",
                "── %PATH & Restart ──\n",
                "VSCode snapshots %PATH at launch. If you installed uv, "
                "git, or Azure CLI during this session, close ALL VSCode "
                "windows and reopen. Reloading a window is NOT enough.\n",
                "── Claude Desktop ──\n",
                "Fully quit Claude Desktop (check the system tray icon) "
                "and reopen it. Then go to:\n"
                "  Settings ▸ Connectors\n"
                "to verify your MCP servers are loaded.\n",
                "── Claude Code ──\n",
                "Run 'claude' in any terminal. If 'uv' is not found, "
                "restart your terminal first to pick up the new PATH.",
            ]
            self.after(0, lambda: messagebox.showinfo("Install Complete", "\n".join(msg_parts)))
        except Exception as e:
            self.after(0, lambda: self._log_append(f"ERROR: {e}"))
            self.after(0, lambda: messagebox.showerror("Install Failed", str(e)))
        finally:
            self._installing = False
            self.after(0, lambda: self._install_btn.config(state="normal"))

    def _run_cmd(self, cmd: list, label: str, cwd: str | None = None,
                  timeout: int = 300):
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd
        )
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.after(0, lambda l=line: self._log_append(f"  {l}"))
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError(f"{label} timed out after {timeout}s")
        if proc.returncode != 0:
            raise RuntimeError(f"{label} failed (exit {proc.returncode})")

    def _write_configs(self, repo_dir: Path, selected_servers: list[str]):
        uv = find_executable("uv") or "uv"
        tenant_id = self._az_tenant_id.get().strip()

        # Base env for any server needing Azure auth
        sub_id = getattr(self, "_az_subscription_id", "")
        tenant_env = {}
        if tenant_id:
            tenant_env["AZURE_TENANT_ID"] = tenant_id
        if sub_id:
            tenant_env["AZURE_SUBSCRIPTION_ID"] = sub_id

        az_env = {}
        if "azure_sql" in selected_servers:
            az_env = {
                **tenant_env,
                "AZURE_SQL_SERVER": self._az_server.get(),
                "AZURE_SQL_DATABASE": self._az_database.get(),
                "AZURE_SQL_AUTH": self._az_auth.get(),
            }
            if self._az_auth.get() == "sql":
                az_env["AZURE_SQL_USER"] = self._az_user.get()
                az_env["AZURE_SQL_PASSWORD"] = self._az_password.get()

        server_configs = {}
        if "fabric" in selected_servers:
            cfg = {
                "command": uv,
                "args": ["--directory", str(repo_dir / "fabric-core"), "run", "fabric_mcp_stdio.py"],
            }
            if tenant_env:
                cfg["env"] = tenant_env
            server_configs["fabric-core"] = cfg
        if "powerbi" in selected_servers:
            server_configs["powerbi-modeling"] = {
                "command": uv,
                "args": ["--directory", str(repo_dir / "powerbi-modeling"), "run", "python", "-m", "powerbi_modeling_mcp"],
            }
        if "translation" in selected_servers:
            server_configs["powerbi-translation-audit"] = {
                "command": uv,
                "args": ["--directory", str(repo_dir / "translation-audit"), "run", "python", "server.py"],
            }
        if "azure_sql" in selected_servers:
            server_configs["azure-sql"] = {
                "command": uv,
                "args": ["--directory", str(repo_dir / "azure-sql"), "run", "python", "-m", "azure_sql_mcp"],
                "env": az_env,
            }

        if self._client_desktop.get():
            if self._is_claude_desktop_running():
                self.after(0, lambda: self._log_append(
                    "  ⚠ Claude Desktop is running — config may not take effect.\n"
                    "    Fully quit Claude Desktop (system tray) and reopen after install."))
            self._write_desktop_config(server_configs)

        if self._client_code.get():
            self._write_code_config(server_configs)

    @staticmethod
    def _is_claude_desktop_running() -> bool:
        """Check if Claude Desktop process is running."""
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq Claude.exe", "/NH"],
                stderr=subprocess.STDOUT, text=True, timeout=5
            )
            return "Claude.exe" in out
        except Exception:
            return False

    def _write_desktop_config(self, server_configs: dict):
        if platform.system() == "Windows":
            appdata = os.environ.get("APPDATA", "") or str(Path.home() / "AppData" / "Roaming")
            config_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
        elif platform.system() == "Darwin":
            config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        else:
            config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if config_path.exists():
            shutil.copy2(config_path, config_path.with_suffix(".json.bak"))
            with open(config_path) as f:
                try:
                    existing = json.load(f)
                except json.JSONDecodeError:
                    existing = {}

        existing.setdefault("mcpServers", {})
        existing["mcpServers"].update(server_configs)

        with open(config_path, "w") as f:
            json.dump(existing, f, indent=2)
        self.after(0, lambda: self._log_append(f"  Merged into: {config_path}"))

    def _write_code_config(self, server_configs: dict):
        if self._code_scope.get() == "project":
            project = self._project_dir.get().strip()
            settings_path = Path(project) / ".claude" / "settings.json"
        else:
            settings_path = Path.home() / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if settings_path.exists():
            shutil.copy2(settings_path, settings_path.with_suffix(".json.bak"))
            with open(settings_path) as f:
                try:
                    existing = json.load(f)
                except json.JSONDecodeError:
                    existing = {}

        existing.setdefault("mcpServers", {})
        existing["mcpServers"].update(server_configs)

        with open(settings_path, "w") as f:
            json.dump(existing, f, indent=2)
        self.after(0, lambda: self._log_append(f"  Written: {settings_path}"))

    def _copy_agents(self, repo_dir: Path, selected_servers: list[str]):
        agents_dest = Path.home() / ".claude" / "agents"
        agents_dest.mkdir(parents=True, exist_ok=True)

        if any(k in selected_servers for k in ("fabric", "powerbi", "translation")):
            agents_src = repo_dir / "agents" / "fabric"
            for md in agents_src.glob("*.md"):
                shutil.copy2(md, agents_dest / md.name)
                self.after(0, lambda n=md.name: self._log_append(f"  Copied agent: {n}"))

        if "azure_sql" in selected_servers:
            agents_src = repo_dir / "agents" / "azure-sql"
            for md in agents_src.glob("*.md"):
                shutil.copy2(md, agents_dest / md.name)
                self.after(0, lambda n=md.name: self._log_append(f"  Copied agent: {n}"))

    def _install_notebook_template(self, src: Path):
        """Copy notebook template and inject a reference into ~/.claude/CLAUDE.md."""
        dest_dir = Path.home() / ".claude" / "notebooks"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        shutil.copy2(src, dest)
        self.after(0, lambda: self._log_append(f"  Copied template: {dest}"))

        # Inject into CLAUDE.md (create if missing, skip if already referenced)
        claude_md = Path.home() / ".claude" / "CLAUDE.md"
        marker = "## Notebook Style"
        entry = (
            f"\n{marker}\n"
            f"When creating notebooks, follow the structure and style of this example:\n"
            f"`{dest}`\n"
        )
        existing_text = claude_md.read_text(encoding="utf-8") if claude_md.exists() else ""
        if marker not in existing_text:
            with open(claude_md, "a", encoding="utf-8") as f:
                f.write(entry)
            self.after(0, lambda: self._log_append("  Added notebook style guide to ~/.claude/CLAUDE.md"))
        else:
            # Update the path in case they picked a different file this run
            import re
            updated = re.sub(
                r"(## Notebook Style\nWhen creating notebooks.*?\n)`[^\n]+`",
                rf"\1`{dest}`",
                existing_text,
                flags=re.DOTALL,
            )
            claude_md.write_text(updated, encoding="utf-8")
            self.after(0, lambda: self._log_append("  Updated notebook style guide in ~/.claude/CLAUDE.md"))


if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()
