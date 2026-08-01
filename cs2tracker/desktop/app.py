"""Application de bureau : fenêtre native hébergeant l'interface.

L'interface est rendue par WebView2, le moteur de navigation intégré à Windows.
Aucun navigateur ne s'ouvre, aucune console n'apparaît : c'est une fenêtre
d'application ordinaire, qui continue de tourner en arrière-plan une fois
fermée pour que l'API reçoive les données du jeu pendant la partie.
"""

from __future__ import annotations

import sys
import threading

from cs2tracker import __app_name__, __version__
from cs2tracker.config import Settings
from cs2tracker.desktop import overlay_launcher
from cs2tracker.desktop.tray import TrayController
from cs2tracker.logging_setup import get_logger
from cs2tracker.server import ApiServer

logger = get_logger(__name__)

WINDOW_WIDTH = 1360
WINDOW_HEIGHT = 880
MIN_WIDTH = 1040
MIN_HEIGHT = 660
#: Fond de la fenêtre pendant le chargement : évite un flash blanc au démarrage.
BACKGROUND = "#0b0e13"


class DesktopApp:
    """Fenêtre WebView2 + icône système, au-dessus de l'API locale."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._server = ApiServer(settings)
        self._window = None
        self._tray: TrayController | None = None
        self._quitting = False

    # --- cycle de vie --------------------------------------------------------
    def run(self) -> int:
        import webview

        self._server.start_background()
        if not self._server.wait_until_ready():
            _show_error(
                "L'API locale n'a pas demarre.\n\n"
                f"Le port {self._settings.api_port} est peut-etre deja utilise. "
                "Ferme l'autre instance, ou change CS2T_API_PORT dans le fichier .env."
            )
            return 1

        self._window = webview.create_window(
            f"{__app_name__} {__version__}",
            f"{self._settings.api_base_url}/app/",
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(MIN_WIDTH, MIN_HEIGHT),
            background_color=BACKGROUND,
            text_select=True,
            confirm_close=False,
        )
        # Fermer la fenetre masque l'application au lieu de l'arreter : la
        # partie en cours doit continuer d'alimenter la base.
        self._window.events.closing += self._on_closing

        self._tray = TrayController(
            on_show=self._show_window,
            on_overlay=self._launch_overlay,
            on_quit=self._quit,
            app_name=__app_name__,
        )
        self._tray.start()

        # `gui="edgechromium"` force WebView2 : sans cela, pywebview pourrait
        # retomber sur un moteur MSHTML vetuste qui ne rend pas l'interface.
        webview.start(gui="edgechromium", private_mode=False)

        self._shutdown()
        return 0

    def _shutdown(self) -> None:
        if self._tray is not None:
            self._tray.stop()
        self._server.stop()
        logger.info("Application arretee.")

    # --- actions -------------------------------------------------------------
    def _on_closing(self) -> bool:
        """Retour ``False`` : la fenêtre se masque au lieu de se fermer."""
        if self._quitting:
            return True
        self._hide_window()
        if self._tray is not None:
            self._tray.notify(
                "CS2 Tracker continue en arriere-plan. "
                "Clique sur l'icone pour rouvrir la fenetre."
            )
        return False

    def _hide_window(self) -> None:
        try:
            if self._window is not None:
                self._window.hide()
        except Exception as exc:  # noqa: BLE001 - masquer ne doit jamais planter
            logger.debug("Masquage impossible : %s", exc)

    def _show_window(self) -> None:
        try:
            if self._window is not None:
                self._window.show()
                self._window.restore()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Affichage impossible : %s", exc)

    def _launch_overlay(self) -> None:
        started, message = overlay_launcher.launch(self._settings.api_port)
        if self._tray is not None:
            self._tray.notify(message)
        if not started:
            logger.warning("Overlay non lance : %s", message)

    def _quit(self) -> None:
        self._quitting = True
        try:
            if self._window is not None:
                self._window.destroy()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fermeture de la fenetre : %s", exc)


def _show_error(message: str) -> None:
    """Affiche une erreur de démarrage — sans console, rien ne serait visible."""
    logger.error(message.replace("\n", " "))
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None, message, f"{__app_name__} — demarrage impossible", 0x10
            )
            return
        except Exception:  # noqa: BLE001
            pass
    print(message, file=sys.stderr)


def run_desktop(settings: Settings) -> int:
    """Point d'entrée du mode fenêtré."""
    try:
        import webview  # noqa: F401
    except ImportError:
        _show_error(
            "Le composant d'affichage est absent.\n\n"
            "Installe-le avec :  pip install pywebview pystray pillow"
        )
        return 2

    return DesktopApp(settings).run()


def open_in_browser_fallback(settings: Settings) -> int:
    """Repli : API + navigateur, si WebView2 est indisponible."""
    import webbrowser

    server = ApiServer(settings)
    url = f"{settings.api_base_url}/app/"

    def launch_when_ready() -> None:
        if server.wait_until_ready():
            webbrowser.open(url)

    threading.Thread(target=launch_when_ready, daemon=True).start()
    try:
        server.run_blocking()
    except KeyboardInterrupt:
        pass
    return 0
