# -*- mode: python ; coding: utf-8 -*-
"""Specification PyInstaller de CS2 Tracker.

Produit `CS2Tracker.exe`, un executable autonome ne necessitant ni Python ni
aucune dependance installee sur la machine cible.

Qt est volontairement exclu : le mode par defaut est l'interface web, ce qui
divise la taille de l'executable par environ quatre et accelere nettement son
demarrage. La fenetre native reste utilisable depuis les sources.

    pyinstaller packaging/cs2tracker.spec --noconfirm
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent

# L'interface web et le schema SQL sont lus a l'execution : ils doivent etre
# embarques comme donnees, pas comme modules.
datas = [
    (str(PROJECT_ROOT / "cs2tracker" / "web"), "cs2tracker/web"),
    (str(PROJECT_ROOT / "cs2tracker" / "storage" / "schema.sql"), "cs2tracker/storage"),
]

# Uvicorn et httpx chargent une partie de leurs modules dynamiquement :
# PyInstaller ne peut pas les deduire de l'analyse statique.
hiddenimports = [
    *collect_submodules("uvicorn"),
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "anyio._backends._asyncio",
]

# Tout ce qui n'est pas necessaire au mode web.
excludes = [
    "PySide6", "shiboken6", "PyQt5", "PyQt6",
    "tkinter", "matplotlib", "numpy", "pandas", "scipy",
    "PIL", "pytest", "_pytest", "playwright", "IPython",
]

a = Analysis(
    [str(PROJECT_ROOT / "run.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CS2Tracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Console visible : elle affiche l'URL de l'interface et les erreurs de
    # demarrage. Sans elle, un port occupe produirait un echec silencieux.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "packaging" / "icon.ico")
    if (PROJECT_ROOT / "packaging" / "icon.ico").is_file()
    else None,
)
