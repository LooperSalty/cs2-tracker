# -*- mode: python ; coding: utf-8 -*-
"""Specification PyInstaller de CS2 Tracker.

Produit `CS2Tracker.exe`, application de bureau autonome ne necessitant ni
Python ni aucune dependance installee sur la machine cible.

Deux choix determinants :

* `console=False` — aucune fenetre de terminal n'apparait. En contrepartie, une
  erreur au demarrage serait invisible : `desktop/app.py` les affiche donc dans
  une boite de dialogue Windows.
* Qt est exclu — l'interface est rendue par WebView2, deja present dans
  Windows 11. Embarquer PySide6 quadruplerait la taille pour rien.

    pyinstaller packaging/cs2tracker.spec --noconfirm
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = Path(SPECPATH).parent

# L'interface web et le schema SQL sont lus a l'execution : ils doivent etre
# embarques comme donnees, pas comme modules.
datas = [
    (str(PROJECT_ROOT / "cs2tracker" / "web"), "cs2tracker/web"),
    (str(PROJECT_ROOT / "cs2tracker" / "storage" / "schema.sql"), "cs2tracker/storage"),
    # Icone de la zone de notification, chargee a l'execution.
    (
        str(PROJECT_ROOT / "cs2tracker" / "desktop" / "tray_icon.png"),
        "cs2tracker/desktop",
    ),
]

# pywebview embarque les assemblages WebView2 dans son propre paquet ; sans eux
# la fenetre ne peut pas s'ouvrir.
datas += collect_data_files("webview")
datas += collect_data_files("clr_loader")

# Modules charges dynamiquement, invisibles a l'analyse statique.
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
    # Fenetre native : backend WebView2 et pont .NET.
    "webview.platforms.edgechromium",
    "clr_loader",
    "clr_loader.netfx",
    "pythonnet",
    # Icone de zone de notification.
    "pystray._win32",
    "PIL.Image",
    "PIL.ImageDraw",
    # Remplace sys.stdout/stderr quand aucune console n'est rattachee.
    "cs2tracker.std_streams",
]

# Tout ce qui n'est pas necessaire a l'application.
excludes = [
    "PySide6", "shiboken6", "PyQt5", "PyQt6",
    "tkinter", "matplotlib", "numpy", "pandas", "scipy",
    "pytest", "_pytest", "playwright", "IPython",
    # Backends pywebview inutilises sous Windows.
    "webview.platforms.cocoa", "webview.platforms.gtk", "webview.platforms.qt",
    "webview.platforms.android",
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
    # Application fenetree : aucune console. Les erreurs de demarrage passent
    # par une boite de dialogue (voir cs2tracker/desktop/app.py).
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "packaging" / "icon.ico")
    if (PROJECT_ROOT / "packaging" / "icon.ico").is_file()
    else None,
)
