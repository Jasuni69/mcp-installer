# PyInstaller spec for MCP Server Installer
# Build: pyinstaller build.spec
# Output: dist/MCPInstaller.exe

block_cipher = None

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['requests', 'packaging', 'packaging.version', 'tkinter', 'tkinter.ttk', 'tkinter.scrolledtext'],
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
    icon='assets/icon.ico' if __import__('os').path.exists('assets/icon.ico') else None,
    onefile=True,
    windowed=True,
)
