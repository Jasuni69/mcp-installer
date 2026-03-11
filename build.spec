# PyInstaller spec for MCP Server Installer v2
# Build: pyinstaller build.spec
# Output: dist/MCPInstaller.exe

import os

block_cipher = None

icon_path = 'assets/icon.ico' if os.path.exists('assets/icon.ico') else None

a = Analysis(
    ['installer.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets/icon.ico', 'assets'),
        ('assets/icon.png', 'assets'),
        # Bundle agents, skills, templates so no git needed at runtime
        ('agents', 'agents'),
        ('skills', 'skills'),
        ('templates', 'templates'),
    ],
    hiddenimports=[
        'mcp_installer',
        'mcp_installer.app',
        'mcp_installer.constants',
        'mcp_installer.path_manager',
        'mcp_installer.prereqs',
        'mcp_installer.downloader',
        'mcp_installer.config_writer',
        'mcp_installer.updater',
        'requests',
        'packaging',
        'packaging.version',
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'winreg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MCPInstaller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
