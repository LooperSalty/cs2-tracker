"""Localisation et lancement de l'overlay natif.

L'overlay est un exécutable séparé : il peut être absent (build C++ non
effectué). Toutes les fonctions dégradent proprement dans ce cas.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

_EXE_NAME = "CS2TrackerOverlay.exe"


def _search_roots() -> list[Path]:
    """Emplacements plausibles, du plus probable au moins probable."""
    roots: list[Path] = []

    # Executable figé : PyInstaller déballe dans _MEIPASS, mais l'overlay est
    # distribué à côté du .exe, pas dedans.
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).parent)
        bundle = getattr(sys, "_MEIPASS", "")
        if bundle:
            roots.append(Path(bundle))

    project = Path(__file__).resolve().parent.parent.parent
    roots.extend(
        [
            project,
            project / "overlay" / "build" / "Release",
            project / "overlay" / "build" / "Debug",
            project / "dist",
        ]
    )
    return roots


def find_overlay() -> Path | None:
    for root in _search_roots():
        candidate = root / _EXE_NAME
        if candidate.is_file():
            return candidate
    return None


def is_running() -> bool:
    """Vrai si une instance de l'overlay est déjà active."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {_EXE_NAME}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return _EXE_NAME.lower() in result.stdout.lower()


def launch(port: int) -> tuple[bool, str]:
    """Démarre l'overlay. Renvoie ``(succès, message pour l'utilisateur)``."""
    if is_running():
        return (
            True,
            "L'overlay tourne deja. Touche F8 pour l'afficher ou le masquer.",
        )

    exe = find_overlay()
    if exe is None:
        return (
            False,
            "CS2TrackerOverlay.exe est introuvable. Telecharge-le depuis la page "
            "des releases et place-le a cote de CS2Tracker.exe.",
        )

    try:
        subprocess.Popen(
            [str(exe), "--port", str(port)],
            cwd=str(exe.parent),
            # Aucune console ne doit apparaitre au lancement.
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
    except OSError as exc:
        logger.error("Lancement de l'overlay impossible : %s", exc)
        return (False, f"Lancement de l'overlay impossible : {exc}")

    logger.info("Overlay lance depuis %s", exe)
    return (
        True,
        "Overlay lance. Regle CS2 sur « Plein ecran fenetre » pour le voir. "
        "F8 masque, F9 deplace.",
    )
