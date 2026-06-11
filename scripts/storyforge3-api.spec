# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the StoryForge3 API sidecar (--onedir)."""

block_cipher = None

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "anyio._backends._asyncio",
    "httptools",
    "storyforge3.api.app",
    "storyforge3.api.deps",
    "storyforge3.api.response",
    "storyforge3.api.errors",
    "storyforge3.api.routes",
    "pydantic_settings",
    "mcp",
]

a = Analysis(
    ["scripts/desktop_entry.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "PIL", "scipy"],
    noarchive=False,
    optimize=0,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="storyforge3-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="storyforge3-api",
)
