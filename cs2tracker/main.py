"""Point d'entrée de l'application.

Modes disponibles :
  ``cs2tracker``               interface web locale + API (mode par defaut)
  ``cs2tracker --desktop``     fenetre native Qt au lieu du navigateur
  ``cs2tracker --api-only``    API seule, pour un client tiers ou un service
  ``cs2tracker --analyse X``   analyse d'un joueur en console
  ``cs2tracker --install-gsi`` ecrit la configuration GSI dans CS2

Le mode par defaut est volontairement le mode web : il ne depend pas de Qt,
ce qui rend l'executable Windows nettement plus leger et son demarrage plus
rapide. La fenetre Qt reste disponible pour qui prefere une application native.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import webbrowser

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
        "--desktop",
        action="store_true",
        help="Ouvrir la fenetre native Qt au lieu du navigateur",
    )
    mode.add_argument(
        "--api-only", action="store_true", help="Demarrer uniquement l'API locale"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Ne pas ouvrir automatiquement le navigateur",
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
    parser.add_argument("--version", action="store_true", help="Afficher la version")
    return parser.parse_args(argv)


def _run_web(open_browser: bool) -> int:
    """Mode par defaut : API locale + interface web, sans dependance a Qt."""
    from cs2tracker.server import ApiServer

    settings = get_settings()
    server = ApiServer(settings)
    url = f"{settings.api_base_url}/app/"

    if open_browser:
        def launch_when_ready() -> None:
            if server.wait_until_ready():
                webbrowser.open(url)
            else:
                logger.error("L'API n'a pas demarre : ouvre %s manuellement.", url)

        threading.Thread(target=launch_when_ready, daemon=True).start()

    print(f"{__app_name__} {__version__}")
    print(f"  Interface : {url}")
    print(f"  API       : {settings.api_base_url}/docs")
    if not settings.has_steam_key:
        print("  Cle API Steam absente — renseigne-la dans l'onglet Configuration.")
    print("  Ctrl+C pour quitter.")

    try:
        server.run_blocking()
    except KeyboardInterrupt:
        pass
    return 0


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

    if args.install_gsi:
        return _run_install_gsi()

    if args.analyse:
        return _run_console_analysis(args.analyse)

    if args.api_only:
        from cs2tracker.server import run_api_only

        run_api_only(settings)
        return 0

    if args.desktop:
        try:
            return _run_gui()
        except ImportError:
            print(
                "La fenetre native necessite PySide6 : installe-le avec\n"
                "    pip install PySide6\n"
                "ou lance l'application sans --desktop pour utiliser l'interface web."
            )
            return 2

    return _run_web(open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
