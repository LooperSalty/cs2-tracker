"""Démarrage du serveur API, en processus principal ou en thread de fond."""

from __future__ import annotations

import threading
import time
from typing import Callable

import httpx
import uvicorn

from cs2tracker.api.app import create_app
from cs2tracker.config import Settings, get_settings
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Délai maximal d'attente du démarrage de l'API avant d'ouvrir l'interface.
STARTUP_TIMEOUT_SECONDS = 20.0
_HEALTH_POLL_INTERVAL = 0.25


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

    def run_blocking(self) -> None:
        self._server.run()

    def start_background(self) -> None:
        if self._thread is not None:
            return
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
