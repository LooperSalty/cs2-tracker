"""Point d'entrée de l'application.

Modes disponibles :
  ``cs2tracker``               fenetre native + API locale (mode par defaut)
  ``cs2tracker --browser``     API + interface dans le navigateur
  ``cs2tracker --api-only``    API seule, pour un client tiers ou un service
  ``cs2tracker --qt``          ancienne fenetre Qt (necessite PySide6)
  ``cs2tracker --analyse X``   analyse d'un joueur en console
  ``cs2tracker --install-gsi`` ecrit la configuration GSI dans CS2

Le mode par defaut ouvre une vraie fenetre d'application : l'interface est
rendue par WebView2, le moteur integre a Windows. Aucun navigateur ne s'ouvre
et aucune console n'apparait. Fermer la fenetre laisse l'application en
arriere-plan, dans la zone de notification, pour que l'API continue de recevoir
les donnees du jeu pendant la partie.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from cs2tracker import __app_name__, __version__
from cs2tracker.config import get_settings
from cs2tracker.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cs2tracker",
        description=f"{__app_name__} {__version__} — suivi CS2 et analyse anti-triche.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--browser",
        action="store_true",
        help="Ouvrir l'interface dans le navigateur au lieu d'une fenetre",
    )
    mode.add_argument(
        "--api-only", action="store_true", help="Demarrer uniquement l'API locale"
    )
    mode.add_argument(
        "--qt", action="store_true", help="Ancienne fenetre Qt (necessite PySide6)"
    )
    parser.add_argument(
        "--analyse",
        metavar="JOUEUR",
        help="Analyser un joueur en console (SteamID, URL ou vanity) puis quitter",
    )
    parser.add_argument(
        "--install-gsi",
        action="store_true",
        help="Installer la configuration GSI dans CS2 puis quitter",
    )
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="Lancer aussi l'overlay affiche par-dessus le jeu",
    )
    parser.add_argument(
        "--wait-for-pid",
        type=int,
        metavar="PID",
        help=argparse.SUPPRESS,  # usage interne : redemarrage de l'application
    )
    parser.add_argument("--version", action="store_true", help="Afficher la version")
    return parser.parse_args(argv)


def _run_gui() -> int:
    """Démarre l'API en arrière-plan puis ouvre l'interface Windows."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    from cs2tracker.server import ApiServer
    from cs2tracker.ui import theme
    from cs2tracker.ui.api_client import ApiClient
    from cs2tracker.ui.main_window import MainWindow

    settings = get_settings()
    server = ApiServer(settings)
    server.start_background()

    application = QApplication(sys.argv)
    application.setApplicationName(__app_name__)
    application.setStyleSheet(theme.STYLESHEET)

    if not server.wait_until_ready():
        QMessageBox.critical(
            None,
            "Demarrage impossible",
            "L'API locale n'a pas demarre dans le delai imparti.\n\n"
            f"Verifie que le port {settings.api_port} est libre, puis relance "
            "l'application.",
        )
        return 1

    client = ApiClient(settings.api_base_url)
    window = MainWindow(client)
    window.show()

    if not settings.has_steam_key:
        QMessageBox.information(
            window,
            "Cle API Steam requise",
            "Aucune cle API Steam n'est configuree : les profils et statistiques "
            "resteront indisponibles.\n\n"
            "Rends-toi dans l'onglet « Configuration » pour en renseigner une "
            "(gratuite sur steamcommunity.com/dev/apikey).",
        )

    exit_code = application.exec()
    server.stop()
    return exit_code


def _run_console_analysis(query: str) -> int:
    """Analyse un joueur sans interface et affiche le rapport."""
    from cs2tracker.anticheat.engine import analyse
    from cs2tracker.anticheat.report import to_text
    from cs2tracker.core.errors import Cs2TrackerError
    from cs2tracker.steam.client import SteamClient
    from cs2tracker.steam.service import SteamService

    settings = get_settings()
    if not settings.has_steam_key:
        print(
            "Cle API Steam absente. Renseigne STEAM_API_KEY dans le fichier .env "
            "(gratuite sur https://steamcommunity.com/dev/apikey)."
        )
        return 2

    async def run() -> int:
        async with SteamClient(settings.steam_api_key) as client:
            service = SteamService(client)
            try:
                profile = await service.get_full_profile(query)
            except Cs2TrackerError as exc:
                print(f"Analyse impossible : {exc.user_message}")
                return 1
            print(to_text(analyse(profile)))
            return 0

    return asyncio.run(run())


def _run_install_gsi() -> int:
    from cs2tracker.core.errors import Cs2TrackerError
    from cs2tracker.gsi.installer import install_config

    settings = get_settings()
    try:
        result = install_config(
            settings.gsi_endpoint,
            settings.gsi_token,
            cs2_path_override=settings.cs2_path_override,
        )
    except Cs2TrackerError as exc:
        print(f"Installation impossible : {exc.user_message}")
        return 1
    print(result.message)
    print(f"Fichier : {result.config_path}")
    return 0 if result.installed else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level, settings.data_path)

    if args.version:
        print(f"{__app_name__} {__version__}")
        return 0

    # Redemarrage en cours : l'instance precedente detient encore le port.
    if args.wait_for_pid:
        from cs2tracker.restart import wait_for_process

        logger.info("Attente de la fin du processus %s...", args.wait_for_pid)
        wait_for_process(args.wait_for_pid)

    if args.install_gsi:
        return _run_install_gsi()

    if args.analyse:
        return _run_console_analysis(args.analyse)

    if args.overlay:
        from cs2tracker.desktop import overlay_launcher

        _started, message = overlay_launcher.launch(settings.api_port)
        logger.info(message)

    if args.api_only:
        from cs2tracker.server import run_api_only

        run_api_only(settings)
        return 0

    if args.qt:
        try:
            return _run_gui()
        except ImportError:
            print(
                "L'ancienne fenetre Qt necessite PySide6 :\n"
                "    pip install PySide6\n"
                "Lance l'application sans --qt pour la fenetre native."
            )
            return 2

    from cs2tracker.desktop.app import open_in_browser_fallback, run_desktop

    if args.browser:
        return open_in_browser_fallback(settings)
    return run_desktop(settings)


if __name__ == "__main__":
    raise SystemExit(main())
