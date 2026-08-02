"""Icône de zone de notification : l'application vit en arrière-plan.

Fermer la fenêtre ne quitte pas le programme — l'API doit continuer à recevoir
les données du jeu pendant la partie. Seule l'entrée « Quitter » arrête tout.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Callable

from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Taille de l'icône générée. 64 px suffit à toutes les densités d'écran.
_ICON_SIZE = 64


def _bundled_icon_path() -> Path | None:
    """Icône embarquée, y compris depuis un exécutable figé."""
    roots = [Path(__file__).resolve().parent]
    bundle = getattr(sys, "_MEIPASS", "")
    if bundle:
        roots.append(Path(bundle) / "cs2tracker" / "desktop")
    for root in roots:
        candidate = root / "tray_icon.png"
        if candidate.is_file():
            return candidate
    return None


def build_icon_image():
    """Icône de la zone de notification.

    On charge le logo de l'application ; à défaut — ressource absente ou
    illisible — un réticule est dessiné à la volée, pour qu'une icône soit
    toujours affichée.
    """
    from PIL import Image, ImageDraw

    path = _bundled_icon_path()
    if path is not None:
        try:
            return Image.open(path).convert("RGBA")
        except OSError as exc:
            logger.warning("Icone %s illisible (%s), repli sur le trace.", path, exc)

    image = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (11, 14, 19, 255))
    draw = ImageDraw.Draw(image)

    accent = (255, 106, 61, 255)
    centre = _ICON_SIZE // 2
    thickness = 6
    arm = 22
    gap = 7

    # Réticule : quatre branches séparées par un vide central.
    draw.rectangle(
        [centre - thickness // 2, centre - arm, centre + thickness // 2, centre - gap],
        fill=accent,
    )
    draw.rectangle(
        [centre - thickness // 2, centre + gap, centre + thickness // 2, centre + arm],
        fill=accent,
    )
    draw.rectangle(
        [centre - arm, centre - thickness // 2, centre - gap, centre + thickness // 2],
        fill=accent,
    )
    draw.rectangle(
        [centre + gap, centre - thickness // 2, centre + arm, centre + thickness // 2],
        fill=accent,
    )
    return image


class TrayController:
    """Pilote l'icône système dans son propre thread."""

    def __init__(
        self,
        *,
        on_show: Callable[[], None],
        on_overlay: Callable[[], None],
        on_quit: Callable[[], None],
        app_name: str,
    ) -> None:
        self._on_show = on_show
        self._on_overlay = on_overlay
        self._on_quit = on_quit
        self._app_name = app_name
        self._icon = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            import pystray
        except ImportError:
            logger.warning("pystray absent : pas d'icone de zone de notification.")
            return

        menu = pystray.Menu(
            pystray.MenuItem("Ouvrir CS2 Tracker", self._handle_show, default=True),
            pystray.MenuItem("Afficher l'overlay en jeu", self._handle_overlay),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quitter", self._handle_quit),
        )
        self._icon = pystray.Icon(
            "cs2tracker", build_icon_image(), self._app_name, menu
        )
        self._thread = threading.Thread(
            target=self._icon.run, name="cs2tracker-tray", daemon=True
        )
        self._thread.start()
        logger.info("Icone de zone de notification active.")

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:  # noqa: BLE001 - l'arret ne doit jamais bloquer
                logger.debug("Arret de l'icone systeme ignore.")
            self._icon = None

    def notify(self, message: str, title: str = "") -> None:
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title or self._app_name)
        except Exception:  # noqa: BLE001 - les notifications sont facultatives
            logger.debug("Notification systeme indisponible.")

    # --- rappels du menu -----------------------------------------------------
    def _handle_show(self, *_args: object) -> None:
        self._safe(self._on_show, "ouverture de la fenetre")

    def _handle_overlay(self, *_args: object) -> None:
        self._safe(self._on_overlay, "lancement de l'overlay")

    def _handle_quit(self, *_args: object) -> None:
        self.stop()
        self._safe(self._on_quit, "arret de l'application")

    @staticmethod
    def _safe(action: Callable[[], None], label: str) -> None:
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - un menu ne doit jamais planter
            logger.error("Echec lors de %s : %s", label, exc)
