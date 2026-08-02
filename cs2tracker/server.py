"""Démarrage du serveur API, en processus principal ou en thread de fond."""

from __future__ import annotations

import socket
import threading
import time
from typing import Callable

import httpx
import uvicorn

from cs2tracker.api.app import create_app
from cs2tracker.config import Settings, get_settings
from cs2tracker.core.errors import Cs2TrackerError
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Délai maximal d'attente du démarrage de l'API avant d'ouvrir l'interface.
STARTUP_TIMEOUT_SECONDS = 20.0
_HEALTH_POLL_INTERVAL = 0.25


def port_owner(host: str, port: int) -> str:
    """Décrit ce qui occupe déjà ``host:port``, ou une chaîne vide.

    Sans cette vérification, une seconde instance échoue à s'attacher et meurt
    en silence — l'utilisateur voit alors l'ancienne version répondre et croit
    que ses modifications n'ont aucun effet.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.5)
        # SO_EXCLUSIVEADDRUSE n'existe que sous Windows ; ailleurs, la
        # tentative de bind suffit a detecter l'occupation.
        probe.bind((host, port))
    except OSError:
        return f"{host}:{port}"
    else:
        return ""
    finally:
        probe.close()


class PortBusyError(Cs2TrackerError):
    status_code = 503
    user_message = (
        "Le port de l'API est deja utilise. Une autre instance de CS2 Tracker "
        "tourne probablement deja : ferme-la, ou change CS2T_API_PORT."
    )


class ApiServer:
    """Serveur uvicorn contrôlable, exécuté dans un thread démon."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        config = uvicorn.Config(
            app=create_app(self._settings),
            host=self._settings.api_host,
            port=self._settings.api_port,
            log_level=self._settings.log_level.lower(),
            access_log=False,
            # `log_config=None` empeche uvicorn d'installer ses propres
            # gestionnaires colorises. Ils interrogent `sys.stdout.isatty()`, ce
            # qui echoue dans une application fenetree sans console. Notre
            # configuration de logs (console + fichier) suffit de toute facon.
            log_config=None,
            # Le GSI de CS2 n'envoie pas d'en-tete Connection: keep-alive fiable ;
            # une duree de vie courte evite d'accumuler des sockets mortes.
            timeout_keep_alive=15,
        )
        self._server = uvicorn.Server(config)
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return self._settings.api_base_url

    def ensure_port_free(self) -> None:
        """Lève ``PortBusyError`` si le port est déjà pris."""
        if port_owner(self._settings.api_host, self._settings.api_port):
            raise PortBusyError(
                f"Port {self._settings.api_port} deja occupe."
            )

    def run_blocking(self) -> None:
        self.ensure_port_free()
        self._server.run()

    def start_background(self) -> None:
        if self._thread is not None:
            return
        self.ensure_port_free()
        self._thread = threading.Thread(
            target=self._server.run, name="cs2tracker-api", daemon=True
        )
        self._thread.start()
        logger.info("Serveur API demarre en arriere-plan sur %s", self.base_url)

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def wait_until_ready(
        self,
        timeout: float = STARTUP_TIMEOUT_SECONDS,
        on_progress: Callable[[float], None] | None = None,
    ) -> bool:
        """Interroge ``/health`` jusqu'à obtenir une réponse ou expiration."""
        deadline = time.monotonic() + timeout
        url = f"{self.base_url}/health"
        with httpx.Client(timeout=2.0) as client:
            while time.monotonic() < deadline:
                try:
                    response = client.get(url)
                    if response.status_code == 200:
                        return True
                except httpx.HTTPError:
                    pass
                if on_progress is not None:
                    on_progress(deadline - time.monotonic())
                time.sleep(_HEALTH_POLL_INTERVAL)
        return False


def run_api_only(settings: Settings | None = None) -> None:
    """Lance uniquement l'API (mode serveur, sans interface)."""
    server = ApiServer(settings)
    logger.info("Documentation interactive : %s/docs", server.base_url)
    server.run_blocking()
