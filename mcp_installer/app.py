"""
MCP Server Installer — GUI Application.

Refactored from monolithic installer.py into a modular app that uses
the core modules (prereqs, downloader, config_writer, updater, path_manager).

Key improvements over v1.x:
- Wizard-style step flow (Prerequisites → Servers → Config → Install → Done)
- "Install All Missing" prerequisites button
- Downloads from GitHub Releases (no git dependency)
- DPI-aware rendering
- Per-widget mousewheel binding (no global binding conflicts)
- WM_SETTINGCHANGE broadcast after prereq installs
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from mcp_installer import __version__
from mcp_installer.constants import (
    CREATION_FLAGS, DEFAULT_INSTALL_DIR, FABRIC_ITEM_SUFFIXES,
    PREREQ_FIXES, RELEASES_API, RELEASES_PAGE, SERVERS, Theme,
)
from mcp_installer.path_manager import (
    broadcast_env_change, find_executable, refresh_process_path,
)
from mcp_installer.prereqs import (
    check_prereqs, install_all_missing, install_prereq_winget,
    load_az_accounts, run_az_login,
)
from mcp_installer.config_writer import (
    build_server_configs, copy_agents, copy_skills,
    get_desktop_config_path, install_glossary, install_notebook_template,
    is_claude_desktop_running, scan_fabric_items, write_code_config,
    write_desktop_config, write_fabric_claude_md,
    remove_desktop_config, remove_code_config,
)
from mcp_installer.updater import (
    check_for_installer_update, read_local_versions, write_local_versions,
)

# Conditionally import downloader (needs requests)
try:
    from mcp_installer.downloader import (
        ChecksumError, DownloadError, ManifestError,
        download_extras, download_server, fetch_manifest, fetch_release_info,
    )
    HAS_DOWNLOADER = True
except ImportError:
    HAS_DOWNLOADER = False


class InstallerApp(tk.Tk):
    """Main installer GUI application."""

    def __init__(self):
        super().__init__()
        self.title(f"MCP Server Installer  v{__version__}")
        self.resizable(True, True)
        self.configure(bg=Theme.BG)
        self._set_icon()

        # ── State variables ───────────────────────────────────────────────
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
        self._glossary_display = tk.StringVar()
        self._glossary_files: list[str] = []
        self._code_scope = tk.StringVar(value="global")
        self._project_dir = tk.StringVar()
        self._az_tenant_id = tk.StringVar()
        self._az_subscription_id = ""
        self._fabric_project_dir = tk.StringVar()

        self._prereqs: dict = {}
        self._az_accounts: list[dict] = []
        self._installing = False
        self._force_reinstall = tk.BooleanVar(value=False)
        self._use_releases = tk.BooleanVar(value=True)  # New: prefer releases over git

        self._build_ui()
        self.update_idletasks()
        self.minsize(580, 640)
        self._refresh_prereqs()
        self._toggle_azure_sql_fields()
        self._toggle_optional_sections()
        self._toggle_code_scope()
        self._update_install_btn()

        # Check for update in background
        threading.Thread(target=self._check_update_bg, daemon=True).start()

    # ── Icon ──────────────────────────────────────────────────────────────

    def _set_icon(self):
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "jasuni69.mcpinstaller"
                )
            except Exception:
                pass
        try:
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
            ico = base / "assets" / "icon.ico"
            png = base / "assets" / "icon.png"
            if ico.exists():
                self.iconbitmap(default=str(ico))
            elif png.exists():
                icon_img = tk.PhotoImage(file=str(png))
                self.wm_iconphoto(True, icon_img)
                self._icon_ref = icon_img
        except Exception:
            pass

    # ── UI BUILD ──────────────────────────────────────────────────────────

    def _build_ui(self):
        T = Theme  # shorthand

        # Configure ttk styles
        self._style = ttk.Style(self)
        self._style.theme_use("clam")
        self._style.configure("TFrame", background=T.BG)
        self._style.configure("Card.TFrame", background=T.CARD)
        self._style.configure("TLabel", background=T.BG, foreground=T.FG, font=T.FONT)
        self._style.configure("Card.TLabel", background=T.CARD, foreground=T.FG, font=T.FONT)
        self._style.configure("Header.TLabel", background=T.BG, foreground=T.ACCENT, font=T.FONT_HEADER)
        self._style.configure("CardHeader.TLabel", background=T.CARD, foreground=T.ACCENT, font=T.FONT_HEADER)
        self._style.configure("Muted.TLabel", background=T.CARD, foreground=T.MUTED, font=T.FONT)
        self._style.configure("TCheckbutton", background=T.CARD, foreground=T.FG, font=T.FONT)
        self._style.configure("TRadiobutton", background=T.CARD, foreground=T.FG, font=T.FONT)
        self._style.configure("TEntry", fieldbackground=T.SURFACE, foreground=T.FG, font=T.FONT)
        self._style.configure("TButton", background=T.OVERLAY, foreground=T.FG, font=T.FONT, padding=(12, 6))
        self._style.map("TButton",
                        background=[("disabled", T.BG), ("active", "#585b70")],
                        foreground=[("disabled", "#585b70"), ("active", T.FG)])
        self._style.configure("Accent.TButton", background=T.ACCENT, foreground=T.BASE_DARK,
                              font=T.FONT_BOLD, padding=(16, 8))
        self._style.map("Accent.TButton",
                        background=[("disabled", T.SURFACE), ("active", "#b4d0ff")],
                        foreground=[("disabled", "#585b70"), ("active", T.BASE_DARK)])
        self._style.configure("TCombobox", fieldbackground=T.SURFACE, foreground=T.FG, font=T.FONT)
        self._style.configure("Horizontal.TProgressbar", troughcolor=T.SURFACE,
                              background=T.ACCENT, thickness=8)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Scrollable container
        self._canvas = tk.Canvas(self, bg=T.BG, highlightthickness=0)
        self._vscroll = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vscroll.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._vscroll.grid(row=0, column=1, sticky="ns")

        main = ttk.Frame(self._canvas, padding=(20, 16))
        self._canvas_window = self._canvas.create_window((0, 0), window=main, anchor="nw")
        main.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._canvas_window, width=e.width))
        # Fix: per-widget mousewheel instead of bind_all
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self._canvas.bind("<Enter>", lambda e: self._bind_mousewheel())
        self._canvas.bind("<Leave>", lambda e: self._unbind_mousewheel())
        main.columnconfigure(0, weight=1)

        def make_card(parent, row_num, title=None):
            card = tk.Frame(parent, bg=T.CARD, highlightbackground=T.CARD_BORDER,
                           highlightthickness=1, padx=16, pady=12)
            card.grid(row=row_num, column=0, sticky="ew", pady=(0, 10))
            card.columnconfigure(1, weight=1)
            if title:
                tk.Label(card, text=title, bg=T.CARD, fg=T.ACCENT,
                         font=T.FONT_HEADER, anchor="w").grid(
                    row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
            return card

        row = 0

        # Update banner (hidden initially)
        self._update_frame = tk.Frame(main, bg=T.OVERLAY, padx=12, pady=8)
        self._update_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        self._update_frame.grid_remove()
        self._update_label = tk.Label(self._update_frame, fg=T.WARN, bg=T.OVERLAY, font=T.FONT)
        self._update_label.pack(side="left")
        self._update_link = tk.Label(self._update_frame, fg=T.ACCENT, bg=T.OVERLAY,
                                     cursor="hand2", font=("Segoe UI", 11, "underline"))
        self._update_link.pack(side="left", padx=8)
        row += 1

        # ── CARD 1: Install Location ──
        c1 = make_card(main, row, "Install Location")
        r = 1
        tk.Label(c1, text="MCP tools folder:", bg=T.CARD, fg=T.FG, font=T.FONT_BOLD
                 ).grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(c1, textvariable=self._install_dir, width=40
                  ).grid(row=r, column=1, sticky="ew", padx=(8, 4), pady=4)
        ttk.Button(c1, text="Browse", command=self._browse_dir
                   ).grid(row=r, column=2, padx=(4, 0), pady=4)
        r += 1
        tk.Label(c1, text="Tools are stored here permanently — do not delete this folder.",
                 bg=T.CARD, fg=T.MUTED, font=T.FONT_SMALL
                 ).grid(row=r, column=1, columnspan=2, sticky="w", padx=8)
        row += 1

        # ── CARD 2: Claude Clients ──
        c2 = make_card(main, row, "Claude Clients")
        r = 1
        ttk.Checkbutton(c2, text="Claude Desktop", variable=self._client_desktop,
                        command=self._update_install_btn).grid(row=r, column=0, columnspan=2, sticky="w", pady=2)
        r += 1
        ttk.Checkbutton(c2, text="Claude Code", variable=self._client_code,
                        command=self._on_client_toggle).grid(row=r, column=0, columnspan=2, sticky="w", pady=2)
        r += 1
        self._scope_frame = tk.Frame(c2, bg=T.CARD)
        self._scope_frame.grid(row=r, column=0, columnspan=3, sticky="ew", padx=(24, 0))
        r += 1
        scope_inner = tk.Frame(self._scope_frame, bg=T.CARD)
        scope_inner.pack(fill="x", pady=(2, 0))
        ttk.Radiobutton(scope_inner, text="Global (all projects)",
                        variable=self._code_scope, value="global",
                        command=self._toggle_code_scope).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(scope_inner, text="Project only",
                        variable=self._code_scope, value="project",
                        command=self._toggle_code_scope).pack(side="left")
        self._project_picker = tk.Frame(self._scope_frame, bg=T.CARD)
        self._project_picker.pack(fill="x", pady=4)
        tk.Label(self._project_picker, text="Project folder:", bg=T.CARD, fg=T.MUTED,
                 font=T.FONT).pack(side="left", padx=(0, 4))
        ttk.Entry(self._project_picker, textvariable=self._project_dir, width=30
                  ).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(self._project_picker, text="Browse",
                   command=self._browse_project).pack(side="left", padx=4)
        row += 1

        # ── CARD 3: MCP Servers ──
        c3 = make_card(main, row, "MCP Servers")
        r = 1
        for key, srv in SERVERS.items():
            ttk.Checkbutton(c3, text=srv["label"], variable=self._server_vars[key],
                            command=self._on_server_toggle
                            ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(4, 0))
            r += 1
            tk.Label(c3, text=srv["desc"], bg=T.CARD, fg=T.MUTED, font=T.FONT_SMALL
                     ).grid(row=r, column=0, columnspan=3, sticky="w", padx=(28, 0), pady=(0, 2))
            r += 1
        # Azure SQL fields
        self._az_frame = tk.Frame(c3, bg=T.CARD)
        self._az_frame.grid(row=r, column=0, columnspan=3, sticky="ew", padx=(24, 0), pady=(4, 0))
        r += 1
        az_inner = tk.Frame(self._az_frame, bg=T.CARD)
        az_inner.pack(fill="x")
        az_inner.columnconfigure(1, weight=1)
        tk.Label(az_inner, text="Server:", bg=T.CARD, fg=T.FG, font=T.FONT
                 ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(az_inner, textvariable=self._az_server, width=35
                  ).grid(row=0, column=1, sticky="ew", pady=2)
        tk.Label(az_inner, text="Database:", bg=T.CARD, fg=T.FG, font=T.FONT
                 ).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(az_inner, textvariable=self._az_database, width=35
                  ).grid(row=1, column=1, sticky="ew", pady=2)
        tk.Label(az_inner, text="Auth:", bg=T.CARD, fg=T.FG, font=T.FONT
                 ).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=2)
        auth_combo = ttk.Combobox(az_inner, textvariable=self._az_auth, values=["az_cli", "sql"],
                                  state="readonly", width=10)
        auth_combo.grid(row=2, column=1, sticky="w", pady=2)
        auth_combo.bind("<<ComboboxSelected>>", lambda e: self._toggle_sql_creds())
        self._sql_cred_frame = tk.Frame(az_inner, bg=T.CARD)
        self._sql_cred_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
        self._sql_cred_frame.columnconfigure(1, weight=1)
        tk.Label(self._sql_cred_frame, text="Username:", bg=T.CARD, fg=T.FG, font=T.FONT
                 ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(self._sql_cred_frame, textvariable=self._az_user, width=35
                  ).grid(row=0, column=1, sticky="ew")
        tk.Label(self._sql_cred_frame, text="Password:", bg=T.CARD, fg=T.FG, font=T.FONT
                 ).grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(self._sql_cred_frame, textvariable=self._az_password, show="*", width=35
                  ).grid(row=1, column=1, sticky="ew")
        row += 1

        # ── CARD 4: Optional ──
        c4 = make_card(main, row, "Optional")
        r = 1
        self._nb_frame = tk.Frame(c4, bg=T.CARD)
        self._nb_frame.grid(row=r, column=0, columnspan=3, sticky="ew")
        self._nb_frame.columnconfigure(1, weight=1)
        tk.Label(self._nb_frame, text="Notebook template:", bg=T.CARD, fg=T.FG, font=T.FONT_BOLD
                 ).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(self._nb_frame, textvariable=self._notebook_template, width=30,
                  state="readonly").grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        nb_btn_frame = tk.Frame(self._nb_frame, bg=T.CARD)
        nb_btn_frame.grid(row=0, column=2, pady=4)
        ttk.Button(nb_btn_frame, text="Browse", command=self._browse_notebook).pack(side="left", padx=2)
        ttk.Button(nb_btn_frame, text="Clear", command=lambda: self._notebook_template.set("")).pack(side="left", padx=2)
        tk.Label(self._nb_frame, text="Claude uses default notebook style if not set.",
                 bg=T.CARD, fg=T.MUTED, font=T.FONT_SMALL
                 ).grid(row=1, column=1, columnspan=2, sticky="w", padx=8)
        r += 1
        self._gl_frame = tk.Frame(c4, bg=T.CARD)
        self._gl_frame.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._gl_frame.columnconfigure(1, weight=1)
        tk.Label(self._gl_frame, text="Glossary files:", bg=T.CARD, fg=T.FG, font=T.FONT_BOLD
                 ).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(self._gl_frame, textvariable=self._glossary_display, width=30,
                  state="readonly").grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        gl_btn_frame = tk.Frame(self._gl_frame, bg=T.CARD)
        gl_btn_frame.grid(row=0, column=2, pady=4)
        ttk.Button(gl_btn_frame, text="Browse", command=self._browse_glossary).pack(side="left", padx=2)
        ttk.Button(gl_btn_frame, text="Clear", command=self._clear_glossary).pack(side="left", padx=2)
        tk.Label(self._gl_frame, text="Company-specific translation terms.",
                 bg=T.CARD, fg=T.MUTED, font=T.FONT_SMALL
                 ).grid(row=1, column=1, columnspan=2, sticky="w", padx=8)
        r += 1
        self._fp_frame = tk.Frame(c4, bg=T.CARD)
        self._fp_frame.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._fp_frame.columnconfigure(1, weight=1)
        tk.Label(self._fp_frame, text="Fabric project:", bg=T.CARD, fg=T.FG, font=T.FONT_BOLD
                 ).grid(row=0, column=0, sticky="w", pady=4)
        fp_inner = tk.Frame(self._fp_frame, bg=T.CARD)
        fp_inner.grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
        ttk.Entry(fp_inner, textvariable=self._fabric_project_dir, width=30,
                  state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(fp_inner, text="Browse", command=self._browse_fabric_project).pack(side="left", padx=4)
        ttk.Button(fp_inner, text="Clear", command=lambda: self._fabric_project_dir.set("")).pack(side="left", padx=2)
        self._fabric_status = tk.Label(self._fp_frame,
                  text="Auto-detects Fabric items and writes CLAUDE.md to project root.",
                  bg=T.CARD, fg=T.MUTED, font=T.FONT_SMALL)
        self._fabric_status.grid(row=1, column=1, columnspan=2, sticky="w", padx=8)
        row += 1

        # ── CARD 5: Prerequisites ──
        c5 = make_card(main, row, "Prerequisites")
        r = 1
        self._prereq_frame = tk.Frame(c5, bg=T.CARD)
        self._prereq_frame.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        r += 1
        prereq_btn_frame = tk.Frame(c5, bg=T.CARD)
        prereq_btn_frame.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Button(prereq_btn_frame, text="↻ Refresh", command=self._refresh_prereqs
                   ).pack(side="left")
        # NEW: Install All Missing button
        self._install_all_btn = ttk.Button(prereq_btn_frame, text="⬇ Install All Missing",
                                            command=self._on_install_all_prereqs,
                                            style="Accent.TButton")
        self._install_all_btn.pack(side="left", padx=(12, 0))
        r += 1
        tk.Label(c5, text="Azure account:", bg=T.CARD, fg=T.FG, font=T.FONT_BOLD
                 ).grid(row=r, column=0, sticky="w", pady=(4, 2))
        r += 1
        self._az_account_combo = ttk.Combobox(c5, state="readonly", width=50)
        self._az_account_combo.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        self._az_account_combo.bind("<<ComboboxSelected>>", lambda e: self._on_account_selected())
        row += 1

        # ── Info Note ──
        note_frame = tk.Frame(main, bg=T.SURFACE, padx=12, pady=10)
        note_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        tk.Label(note_frame,
            text="ℹ  After installing prerequisites, the installer broadcasts PATH changes\n"
                 "   to other apps. For Claude Desktop: fully quit (system tray) and reopen.\n"
                 "   Azure tokens expire — run 'az login' to renew.",
            fg=T.TEAL, bg=T.SURFACE, font=T.FONT_SMALL, justify="left", anchor="w"
            ).pack(fill="x")
        row += 1

        # ── Progress + Log ──
        self._progress_label = tk.Label(main, text="", fg=T.ACCENT, bg=T.BG, font=T.FONT_BOLD, anchor="w")
        self._progress_label.grid(row=row, column=0, sticky="ew", padx=4, pady=(8, 2))
        row += 1
        self._progress = ttk.Progressbar(main, mode="determinate", style="Horizontal.TProgressbar")
        self._progress.grid(row=row, column=0, sticky="ew", padx=4, pady=(0, 4))
        row += 1
        self._log = scrolledtext.ScrolledText(main, width=1, height=8, state="disabled",
                                               bg=T.DARK, fg=T.FG, font=T.FONT_MONO,
                                               insertbackground=T.FG, relief="flat", borderwidth=0)
        self._log.grid(row=row, column=0, sticky="nsew", padx=4, pady=4)
        # Configure log colors
        self._log.tag_configure("success", foreground=T.OK)
        self._log.tag_configure("error", foreground=T.WARN)
        self._log.tag_configure("info", foreground=T.ACCENT)
        main.rowconfigure(row, weight=1)
        row += 1

        # ── Action Buttons ──
        btn_frame = tk.Frame(main, bg=T.BG)
        btn_frame.grid(row=row, column=0, sticky="ew", padx=4, pady=(8, 4))
        ttk.Checkbutton(btn_frame, text="Force reinstall", variable=self._force_reinstall).pack(side="left")
        self._update_btn = ttk.Button(btn_frame, text="Update MCP Tools", command=self._on_update)
        self._update_btn.pack(side="left", padx=(12, 0))
        self._uninstall_btn = ttk.Button(btn_frame, text="Uninstall Selected", command=self._on_uninstall)
        self._uninstall_btn.pack(side="left", padx=(8, 0))
        self._cancel_btn = ttk.Button(btn_frame, text="Close", command=self._on_cancel)
        self._cancel_btn.pack(side="right", padx=(8, 0))
        self._install_btn = ttk.Button(btn_frame, text="  Install  ", style="Accent.TButton",
                                       command=self._on_install)
        self._install_btn.pack(side="right")

    # ── Mousewheel (fixed: per-widget, not global) ────────────────────────

    def _bind_mousewheel(self):
        self._canvas.bind_all("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _unbind_mousewheel(self):
        self._canvas.unbind_all("<MouseWheel>")

    # ── Prerequisites panel ───────────────────────────────────────────────

    def _refresh_prereqs(self):
        for w in self._prereq_frame.winfo_children():
            w.destroy()
        tk.Label(self._prereq_frame, text="Checking...", fg=Theme.MUTED,
                 bg=Theme.CARD, font=Theme.FONT_MONO).grid(row=0, column=0, sticky="w")

        def _check():
            refresh_process_path()
            results = check_prereqs()
            self.after(0, lambda: self._populate_prereqs(results))

        threading.Thread(target=_check, daemon=True).start()

    def _populate_prereqs(self, results: dict):
        for w in self._prereq_frame.winfo_children():
            w.destroy()
        self._prereqs = results
        tid = self._prereqs.get("_tenant_id", "")
        if tid:
            self._az_tenant_id.set(tid)
        self._load_az_accounts()

        labels = {
            "uv":         "uv",
            "git":        "git (optional)",
            "azure_cli":  "Azure CLI",
            "azure_auth": "Azure authenticated",
            "dotnet9":    ".NET 9.x (Power BI Modeling)",
            "odbc_driver": "ODBC Driver 18 (Azure SQL)",
        }
        has_missing = False
        for i, (key, label) in enumerate(labels.items()):
            ok, detail = self._prereqs.get(key, (False, ""))
            icon = "✓" if ok else "✗"
            color = Theme.OK if ok else Theme.WARN
            if not ok:
                has_missing = True

            tk.Label(self._prereq_frame, text=f"{icon} {label}",
                     fg=color, bg=Theme.CARD, font=Theme.FONT_MONO,
                     anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            detail_lbl = tk.Label(self._prereq_frame, text=detail,
                     fg=Theme.MUTED, bg=Theme.CARD, font=("Consolas", 9),
                     anchor="w")
            detail_lbl.grid(row=i, column=1, sticky="w", padx=8, pady=2)
            if key == "azure_auth":
                self._auth_detail_label = detail_lbl

            if not ok:
                winget_id, url = PREREQ_FIXES.get(key, (None, None))
                if key == "azure_auth":
                    btn = tk.Label(self._prereq_frame, text="Sign in",
                                   fg=Theme.ACCENT, bg=Theme.CARD,
                                   font=Theme.FONT_LINK, cursor="hand2")
                    btn.grid(row=i, column=2, sticky="w", padx=4)
                    btn.bind("<Button-1>", lambda e: self._az_login())
                elif winget_id:
                    btn = tk.Label(self._prereq_frame, text="Install",
                                   fg=Theme.ACCENT, bg=Theme.CARD,
                                   font=Theme.FONT_LINK, cursor="hand2")
                    btn.grid(row=i, column=2, sticky="w", padx=4)
                    btn.bind("<Button-1>", lambda e, w=winget_id, u=url: self._install_single_prereq(w, u))
                elif url:
                    btn = tk.Label(self._prereq_frame, text="Download",
                                   fg=Theme.ACCENT, bg=Theme.CARD,
                                   font=Theme.FONT_LINK, cursor="hand2")
                    btn.grid(row=i, column=2, sticky="w", padx=4)
                    btn.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        # Show/hide Install All button based on whether anything is missing
        if has_missing:
            self._install_all_btn.pack(side="left", padx=(12, 0))
        else:
            self._install_all_btn.pack_forget()

    def _install_single_prereq(self, winget_id: str, fallback_url: str):
        winget = find_executable("winget")
        if not winget:
            webbrowser.open(fallback_url)
            return

        def _run():
            self.after(0, lambda: self._log_append(f"Installing {winget_id}...", "info"))
            success = install_prereq_winget(
                winget_id,
                log_callback=lambda msg: self.after(0, lambda m=msg: self._log_append(m))
            )
            if success:
                self.after(0, lambda: self._log_append(f"✓ Installed {winget_id}", "success"))
                self.after(500, self._refresh_prereqs)
            else:
                self.after(0, lambda: webbrowser.open(fallback_url))

        threading.Thread(target=_run, daemon=True).start()

    def _on_install_all_prereqs(self):
        """NEW: Install all missing prerequisites in one click."""
        if not self._prereqs:
            return

        self._install_all_btn.config(state="disabled")
        self._log_append("Installing all missing prerequisites...", "info")

        def _run():
            def log_cb(msg):
                self.after(0, lambda m=msg: self._log_append(m))

            def progress_cb(current, total, label):
                pct = int(current / total * 100) if total else 0
                self.after(0, lambda: self._progress.config(value=pct))
                self.after(0, lambda l=label: self._progress_label.config(text=l))

            results = install_all_missing(self._prereqs, log_cb, progress_cb)

            succeeded = sum(1 for v in results.values() if v)
            failed = sum(1 for v in results.values() if not v)

            if failed:
                self.after(0, lambda: self._log_append(
                    f"Done: {succeeded} installed, {failed} failed — check log above", "error"))
            elif succeeded:
                self.after(0, lambda: self._log_append(
                    f"✓ All {succeeded} prerequisites installed!", "success"))
            else:
                self.after(0, lambda: self._log_append("No prerequisites needed installation", "info"))

            self.after(0, lambda: self._progress.config(value=0))
            self.after(0, lambda: self._progress_label.config(text=""))
            self.after(0, lambda: self._install_all_btn.config(state="normal"))
            self.after(500, self._refresh_prereqs)

        threading.Thread(target=_run, daemon=True).start()

    def _load_az_accounts(self):
        accounts = load_az_accounts()
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

    def _on_account_selected(self):
        idx = self._az_account_combo.current()
        if idx < 0 or idx >= len(self._az_accounts):
            return
        acct = self._az_accounts[idx]
        self._az_tenant_id.set(acct.get("tenantId", ""))
        self._az_subscription_id = acct.get("id", "")
        if hasattr(self, "_auth_detail_label") and acct.get("tenantId"):
            self._auth_detail_label.config(text=f"Authenticated — tenant {acct['tenantId']}")

    def _az_login(self):
        def _run():
            success = run_az_login(
                log_callback=lambda msg: self.after(0, lambda m=msg: self._log_append(m))
            )
            self.after(500, self._refresh_prereqs)
        self._log_append("Opening Azure login in browser...", "info")
        threading.Thread(target=_run, daemon=True).start()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self._install_dir.get())
        if d:
            self._install_dir.set(d)

    def _browse_project(self):
        d = filedialog.askdirectory(title="Select project folder")
        if d:
            self._project_dir.set(d)

    def _browse_notebook(self):
        f = filedialog.askopenfilename(
            title="Select notebook template",
            filetypes=[("Jupyter notebooks", "*.ipynb"), ("All files", "*.*")])
        if f:
            self._notebook_template.set(f)

    def _browse_glossary(self):
        files = filedialog.askopenfilenames(
            title="Select glossary files",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if files:
            self._glossary_files = list(files)
            self._glossary_display.set(", ".join(Path(f).name for f in files))

    def _clear_glossary(self):
        self._glossary_files = []
        self._glossary_display.set("")

    def _browse_fabric_project(self):
        d = filedialog.askdirectory(title="Select Fabric project folder")
        if not d:
            return
        self._fabric_project_dir.set(d)
        found = scan_fabric_items(Path(d))
        if found:
            types = set()
            for item in found:
                for sig in FABRIC_ITEM_SUFFIXES:
                    if item["name"].endswith(sig):
                        types.add(sig.lstrip("."))
                        break
            type_str = ", ".join(sorted(types)) if types else "items found"
            self._fabric_status.config(
                text=f"✓ Fabric project detected — {type_str} ({len(found)} items)",
                foreground=Theme.OK)
        else:
            self._fabric_status.config(
                text="⚠ No Fabric items detected — are you sure this is a Fabric repo?",
                foreground=Theme.WARN)

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

    def _toggle_azure_sql_fields(self):
        if self._server_vars["azure_sql"].get():
            self._az_frame.grid()
        else:
            self._az_frame.grid_remove()
        self._toggle_sql_creds()

    def _on_server_toggle(self):
        self._toggle_azure_sql_fields()
        self._toggle_optional_sections()
        self._update_install_btn()

    def _toggle_optional_sections(self):
        fabric = self._server_vars["fabric"].get()
        translation = self._server_vars.get("translation", tk.BooleanVar()).get()
        powerbi = self._server_vars.get("powerbi", tk.BooleanVar()).get()
        if fabric:
            self._nb_frame.grid()
            self._fp_frame.grid()
        else:
            self._nb_frame.grid_remove()
            self._fp_frame.grid_remove()
        if translation or powerbi:
            self._gl_frame.grid()
        else:
            self._gl_frame.grid_remove()

    def _toggle_sql_creds(self):
        if self._az_auth.get() == "sql":
            self._sql_cred_frame.grid()
        else:
            self._sql_cred_frame.grid_remove()

    def _update_install_btn(self):
        any_server = any(v.get() for v in self._server_vars.values())
        any_client = self._client_desktop.get() or self._client_code.get()
        self._install_btn.config(state="normal" if (any_server and any_client) else "disabled")

    def _log_append(self, text: str, tag: str = ""):
        self._log.config(state="normal")
        if tag:
            self._log.insert("end", text + "\n", tag)
        else:
            self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _check_update_bg(self):
        available, version, url = check_for_installer_update()
        if available:
            self.after(0, lambda: self._show_update_banner(version, url))

    def _show_update_banner(self, version: str, url: str):
        self._update_label.config(text=f"⚠  Update available: v{version}")
        self._update_link.config(text="[Download]")
        self._update_link.bind("<Button-1>", lambda e: webbrowser.open(url))
        self._update_frame.grid()

    # ── Install ───────────────────────────────────────────────────────────

    def _on_install(self):
        if self._installing:
            return
        if (self._client_code.get() and self._code_scope.get() == "project"
                and not self._project_dir.get().strip()):
            messagebox.showwarning("Missing fields", "Project scope selected but no project folder chosen.")
            return
        if self._server_vars["azure_sql"].get():
            if not self._az_server.get().strip() or not self._az_database.get().strip():
                messagebox.showwarning("Missing fields",
                    "Azure SQL selected but server/database is empty.")
                return
            if self._az_auth.get() == "sql":
                if not self._az_user.get().strip() or not self._az_password.get().strip():
                    messagebox.showwarning("Missing fields", "SQL auth: username/password is empty.")
                    return

        self._installing = True
        self._install_btn.config(state="disabled")
        self._log_append("Starting installation...", "info")
        threading.Thread(target=self._run_install, daemon=True).start()

    def _on_update(self):
        if self._installing:
            return
        self._installing = True
        self._install_btn.config(state="disabled")
        self._update_btn.config(state="disabled")
        self._log_append("Updating MCP tools...", "info")
        threading.Thread(target=self._run_update, daemon=True).start()

    def _on_cancel(self):
        if self._installing:
            if not messagebox.askyesno("Cancel", "Installation is in progress. Close anyway?"):
                return
        self.destroy()

    def _on_uninstall(self):
        if self._installing:
            return
        
        selected = [k for k, v in self._server_vars.items() if v.get()]
        if not selected:
            messagebox.showinfo("Nothing to uninstall", "Please select the servers you wish to uninstall.")
            return
            
        if not messagebox.askyesno("Confirm Uninstall", f"Are you sure you want to completely remove {len(selected)} selected MCP tool(s) and their configurations?"):
            return
            
        self._installing = True
        self._install_btn.config(state="disabled")
        self._update_btn.config(state="disabled")
        self._uninstall_btn.config(state="disabled")
        self._log_append("Uninstalling MCP tools...", "error")
        threading.Thread(target=self._run_uninstall, daemon=True).start()

    def _run_uninstall(self):
        try:
            install_dir = Path(self._install_dir.get())
            selected = [k for k, v in self._server_vars.items() if v.get()]
            
            # Map selected keys to config keys
            key_map = {
                "fabric": "fabric-core",
                "powerbi": "powerbi-modeling",
                "translation": "powerbi-translation-audit",
                "azure_sql": "azure-sql"
            }
            config_keys = [key_map[k] for k in selected if k in key_map]
            
            # Remove configs
            if self._client_desktop.get():
                if is_claude_desktop_running():
                    self.after(0, lambda: self._log_append(
                        "  ⚠ Claude Desktop is running — quit and reopen after uninstall", "error"))
                if remove_desktop_config(config_keys):
                    self.after(0, lambda: self._log_append("  ✓ Removed from Claude Desktop config", "success"))
                    
            if self._client_code.get():
                if remove_code_config(config_keys, self._code_scope.get(), self._project_dir.get().strip()):
                    self.after(0, lambda: self._log_append("  ✓ Removed from Claude Code config", "success"))

            # Remove directories
            for key in selected:
                srv = SERVERS[key]
                srv_dir = install_dir / srv["dir"]
                if not srv_dir.exists():
                    srv_dir = install_dir / "mcp-installer" / srv["dir"]
                
                if srv_dir.exists():
                    self.after(0, lambda d=srv_dir.name: self._log_append(f"  Deleting folder: {d}..."))
                    try:
                        import stat
                        def remove_readonly(func, path, excinfo):
                            os.chmod(path, stat.S_IWRITE)
                            func(path)
                        shutil.rmtree(srv_dir, onerror=remove_readonly)
                    except Exception as e:
                        self.after(0, lambda err=str(e): self._log_append(f"  ⚠ Failed to delete: {err} (Try closing terminal/editor)", "error"))

            # Remove from local versions.json
            versions_installed = read_local_versions(install_dir)
            if versions_installed:
                for key in selected:
                    dir_name = SERVERS[key]["dir"]
                    versions_installed.pop(dir_name, None)
                write_local_versions(install_dir, versions_installed)

            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("✓ Selected MCP tools uninstalled!", "success"))
            self.after(0, lambda: messagebox.showinfo("Uninstall Complete", "Uninstallation finished successfully.\n\nRestart Claude Desktop (system tray → Quit → reopen) for config changes to apply."))
        except Exception as e:
            self.after(0, lambda err=str(e): self._log_append(f"ERROR: {err}", "error"))
            self.after(0, lambda err=str(e): messagebox.showerror("Uninstall Failed", err))
        finally:
            self._installing = False
            self.after(0, self._update_install_btn)
            self.after(0, lambda: self._update_btn.config(state="normal"))
            self.after(0, lambda: self._uninstall_btn.config(state="normal"))

    def _run_cmd(self, cmd: list, label: str, cwd: str | None = None, timeout: int = 300):
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd, creationflags=CREATION_FLAGS
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

    def _run_install(self):
        """Main install flow — uses GitHub Releases (no git)."""
        try:
            install_dir = Path(self._install_dir.get())
            install_dir.mkdir(parents=True, exist_ok=True)
            selected = [k for k, v in self._server_vars.items() if v.get()]
            uv = find_executable("uv") or "uv"
            force = self._force_reinstall.get()

            # Determine source directory for agents/skills/templates
            # Check bundled assets first (PyInstaller), then local repo
            bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
            source_dir = bundled  # agents/, skills/, templates/ from bundled or repo

            total_steps = len(selected) * 2 + 5  # download + sync each + config + agents + skills + template + extras
            step = 0

            def progress(msg: str):
                nonlocal step
                pct = int(step / total_steps * 100)
                self.after(0, lambda: self._progress.config(value=pct))
                self.after(0, lambda m=msg: self._progress_label.config(text=m))
                self.after(0, lambda m=msg: self._log_append(f"> {m}"))
                step += 1

            versions_installed: dict[str, str] = {}

            # ── Step: Download servers from releases OR fallback to git ───
            if HAS_DOWNLOADER:
                try:
                    progress("Fetching release manifest...")
                    manifest = fetch_manifest()
                    release_info = fetch_release_info()
                    manifest_version = manifest.get("installer_version", "unknown")
                    self.after(0, lambda v=manifest_version: self._log_append(
                        f"  Release version: {v}", "info"))

                    for key in selected:
                        srv = SERVERS[key]
                        dir_name = srv["dir"]
                        progress(f"Downloading {dir_name}...")
                        download_server(
                            dir_name, install_dir, manifest,
                            log_callback=lambda msg: self.after(0, lambda m=msg: self._log_append(f"  {m}"))
                        )
                        ver = manifest.get("servers", {}).get(dir_name, {}).get("version", "unknown")
                        versions_installed[dir_name] = ver

                    # Download extras (agents, skills, templates)
                    progress("Downloading extras...")
                    if download_extras(install_dir, release_info,
                                       log_callback=lambda msg: self.after(0, lambda m=msg: self._log_append(f"  {m}"))):
                        source_dir = install_dir  # Use downloaded extras

                except (DownloadError, ManifestError) as e:
                    self.after(0, lambda err=str(e): self._log_append(
                        f"  ⚠ Release download failed: {err}", "error"))
                    self.after(0, lambda: self._log_append(
                        "  Falling back to git clone...", "info"))
                    self._fallback_git_clone(install_dir, selected, progress)
                    source_dir = install_dir / "mcp-installer"
            else:
                # No requests library — use git
                self._fallback_git_clone(install_dir, selected, progress)
                source_dir = install_dir / "mcp-installer"

            # ── Step: uv sync each server ─────────────────────────────────
            for key in selected:
                srv = SERVERS[key]
                srv_dir = install_dir / srv["dir"]
                if not srv_dir.exists():
                    # Might be in mcp-installer subdirectory (git clone layout)
                    srv_dir = install_dir / "mcp-installer" / srv["dir"]
                venv = srv_dir / ".venv"
                venv_healthy = (venv / "pyvenv.cfg").exists() if venv.exists() else False

                if venv_healthy and not force:
                    progress(f"{srv['dir']} already synced — skipping")
                else:
                    sync_cmd = [uv, "sync"]
                    if force:
                        sync_cmd.append("--reinstall")
                    progress(f"uv sync {srv['dir']}...")
                    self._run_cmd(sync_cmd, f"uv sync {srv['dir']}", cwd=str(srv_dir), timeout=900)

            # ── Step: Build and write configs ─────────────────────────────
            progress("Writing MCP configs...")
            # Determine server base directory
            server_base = install_dir
            if (install_dir / "mcp-installer" / "fabric-core").exists():
                server_base = install_dir / "mcp-installer"

            server_configs = build_server_configs(
                server_base_dir=server_base,
                selected_servers=selected,
                uv_path=uv,
                tenant_id=self._az_tenant_id.get().strip(),
                subscription_id=self._az_subscription_id,
                az_server=self._az_server.get(),
                az_database=self._az_database.get(),
                az_auth=self._az_auth.get(),
                az_user=self._az_user.get(),
                az_password=self._az_password.get(),
            )

            if self._client_desktop.get():
                if is_claude_desktop_running():
                    self.after(0, lambda: self._log_append(
                        "  ⚠ Claude Desktop is running — quit and reopen after install", "error"))
                path = write_desktop_config(server_configs)
                self.after(0, lambda p=path: self._log_append(f"  Merged into: {p}"))

            if self._client_code.get():
                path = write_code_config(server_configs, self._code_scope.get(),
                                         self._project_dir.get().strip())
                self.after(0, lambda p=path: self._log_append(f"  Written: {p}"))

            # ── Step: Copy agents ─────────────────────────────────────────
            if self._client_code.get():
                progress("Copying agents...")
                if self._code_scope.get() == "project":
                    agents_dest = Path(self._project_dir.get().strip()) / ".claude" / "agents"
                else:
                    agents_dest = Path.home() / ".claude" / "agents"
                copied = copy_agents(source_dir, selected, agents_dest)
                for name in copied:
                    self.after(0, lambda n=name: self._log_append(f"  Copied agent: {n}"))

            # ── Step: Copy skills ─────────────────────────────────────────
            if self._client_code.get():
                progress("Copying skills...")
                if self._code_scope.get() == "project":
                    skills_dest = Path(self._project_dir.get().strip()) / ".claude" / "skills"
                else:
                    skills_dest = Path.home() / ".claude" / "skills"
                copied = copy_skills(source_dir, skills_dest)
                for name in copied:
                    self.after(0, lambda n=name: self._log_append(f"  Copied skill: {n}"))

            # ── Step: CLAUDE.md template ──────────────────────────────────
            if (self._client_code.get() and self._code_scope.get() == "project"):
                template_src = source_dir / "templates" / "CLAUDE.md"
                if template_src.exists():
                    project = Path(self._project_dir.get().strip())
                    dest = project / "CLAUDE.md"
                    if not dest.exists():
                        shutil.copy2(template_src, dest)
                        self.after(0, lambda d=dest: self._log_append(f"  Copied CLAUDE.md to {d}"))

            # ── Optional: notebook template ───────────────────────────────
            nb_path = self._notebook_template.get().strip()
            if nb_path and Path(nb_path).exists():
                progress("Installing notebook template...")
                if self._code_scope.get() == "project":
                    base = Path(self._project_dir.get().strip()) / ".claude"
                    claude_md = Path(self._project_dir.get().strip()) / "CLAUDE.md"
                else:
                    base = Path.home() / ".claude"
                    claude_md = Path.home() / ".claude" / "CLAUDE.md"
                install_notebook_template(Path(nb_path), base, claude_md)

            # ── Optional: glossary files ──────────────────────────────────
            if self._glossary_files:
                glossary_paths = [Path(f) for f in self._glossary_files if Path(f).exists()]
                if glossary_paths:
                    progress("Installing glossary files...")
                    if self._code_scope.get() == "project":
                        base = Path(self._project_dir.get().strip()) / ".claude"
                        claude_md = Path(self._project_dir.get().strip()) / "CLAUDE.md"
                    else:
                        base = Path.home() / ".claude"
                        claude_md = Path.home() / ".claude" / "CLAUDE.md"
                    install_glossary(glossary_paths, base, claude_md)

            # ── Optional: Fabric project CLAUDE.md ────────────────────────
            fp_dir = self._fabric_project_dir.get().strip()
            if fp_dir and Path(fp_dir).exists():
                progress("Writing Fabric project CLAUDE.md...")
                result = write_fabric_claude_md(Path(fp_dir))
                self.after(0, lambda r=result: self._log_append(f"  CLAUDE.md {r}: {fp_dir}/CLAUDE.md"))

            # ── Save versions ─────────────────────────────────────────────
            if versions_installed:
                write_local_versions(install_dir, versions_installed)
                self.after(0, lambda: self._log_append("  Saved version info", "info"))

            # ── Done ──────────────────────────────────────────────────────
            self.after(0, lambda: self._progress.config(value=100))
            self.after(0, lambda: self._progress_label.config(text="Done"))
            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("✓ Installation complete!", "success"))
            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("  Restart Claude Desktop (system tray → Quit) and reopen."))
            self.after(0, lambda: self._log_append("  Restart VSCode/terminals to pick up PATH changes."))
            self.after(0, lambda: messagebox.showinfo("Install Complete",
                "Installation complete!\n\n"
                "Restart Claude Desktop (system tray → Quit → reopen)\n"
                "and restart VSCode / terminals to pick up PATH changes."))

        except Exception as e:
            self.after(0, lambda: self._log_append(f"ERROR: {e}", "error"))
            self.after(0, lambda: messagebox.showerror("Install Failed", str(e)))
        finally:
            self._installing = False
            self.after(0, self._update_install_btn)

    def _fallback_git_clone(self, install_dir: Path, selected: list[str], progress):
        """Fallback: clone/pull repo via git if release download is unavailable."""
        from mcp_installer.constants import GITHUB_OWNER, GITHUB_REPO
        repo_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
        repo_dir = install_dir / "mcp-installer"
        git = find_executable("git") or "git"

        if (repo_dir / ".git").exists():
            progress("Updating repo (git pull)...")
            self._run_cmd([git, "-C", str(repo_dir), "pull"], "git pull")
        else:
            progress(f"Cloning {repo_url}...")
            self._run_cmd([git, "clone", repo_url, str(repo_dir)], "git clone")

    def _run_update(self):
        """Update existing MCP tools (re-download + re-sync)."""
        try:
            install_dir = Path(self._install_dir.get())
            install_dir.mkdir(parents=True, exist_ok=True)
            selected = [k for k, v in self._server_vars.items() if v.get()]
            uv = find_executable("uv") or "uv"

            if HAS_DOWNLOADER:
                try:
                    self.after(0, lambda: self._log_append("> Fetching latest release...", "info"))
                    manifest = fetch_manifest()
                    for key in selected:
                        srv = SERVERS[key]
                        self.after(0, lambda d=srv["dir"]: self._log_append(f"> Downloading {d}..."))
                        download_server(
                            srv["dir"], install_dir, manifest,
                            log_callback=lambda msg: self.after(0, lambda m=msg: self._log_append(f"  {m}"))
                        )
                except (DownloadError, ManifestError):
                    # Fallback to git
                    self._fallback_git_clone(install_dir, selected,
                        lambda msg: self.after(0, lambda m=msg: self._log_append(f"> {m}")))

            for key in selected:
                srv = SERVERS[key]
                srv_dir = install_dir / srv["dir"]
                if not srv_dir.exists():
                    srv_dir = install_dir / "mcp-installer" / srv["dir"]
                self.after(0, lambda d=srv["dir"]: self._log_append(f"> uv sync {d}..."))
                self._run_cmd([uv, "sync"], f"uv sync {srv['dir']}", cwd=str(srv_dir), timeout=900)

            self.after(0, lambda: self._log_append(""))
            self.after(0, lambda: self._log_append("✓ MCP tools updated!", "success"))
        except Exception as e:
            self.after(0, lambda: self._log_append(f"ERROR: {e}", "error"))
            self.after(0, lambda: messagebox.showerror("Update Failed", str(e)))
        finally:
            self._installing = False
            self.after(0, self._update_install_btn)
            self.after(0, lambda: self._update_btn.config(state="normal"))
            if hasattr(self, "_uninstall_btn"):
                self.after(0, lambda: self._uninstall_btn.config(state="normal"))
