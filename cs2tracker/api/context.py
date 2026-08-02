"""Contexte applicatif : instancie et partage les services entre les routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cs2tracker.config import Settings
from cs2tracker.core.errors import MissingApiKeyError
from cs2tracker.gsi.installer import is_installed
from cs2tracker.gsi.locator import try_find_cs2
from cs2tracker.gsi.recorder import MatchRecorder
from cs2tracker.gsi.state import LiveStateStore
from cs2tracker.logging_setup import get_logger
from cs2tracker.steam.client import SteamClient
from cs2tracker.steam.service import SteamService
from cs2tracker.storage.db import Database
from cs2tracker.faceit import FaceitClient
from cs2tracker.storage.audit import AuditRepository
from cs2tracker.storage.matches_history import (
    PlayerMatchRepository,
    TeammateRepository,
)
from cs2tracker.storage.repositories import (
    AnalysisRepository,
    MatchRepository,
    PlayerRepository,
    SettingsRepository,
    SnapshotRepository,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class AppContext:
    """Conteneur de dépendances, créé une fois au démarrage de l'API."""

    settings: Settings
    database: Database
    live: LiveStateStore
    players: PlayerRepository
    snapshots: SnapshotRepository
    analyses: AnalysisRepository
    matches: MatchRepository
    settings_repo: SettingsRepository
    audit: AuditRepository
    player_matches: PlayerMatchRepository
    teammates: TeammateRepository
    recorder: MatchRecorder
    steam_client: SteamClient | None = None
    steam_service: SteamService | None = None
    faceit: FaceitClient | None = None

    @property
    def steam(self) -> SteamService:
        if self.steam_service is None:
            raise MissingApiKeyError()
        return self.steam_service

    @property
    def has_steam(self) -> bool:
        return self.steam_service is not None

    async def apply_steam_key(self, key: str) -> bool:
        """Remplace le client Steam à chaud, sans redémarrer l'application.

        Le client était historiquement construit une seule fois au démarrage,
        ce qui obligeait à relancer le programme après avoir saisi une clé.
        Le reconstruire ici rend la clé utilisable immédiatement.

        Renvoie ``False`` si la clé est vide.
        """
        cleaned = key.strip()
        if not cleaned:
            return False

        previous = self.steam_client
        self.settings = self.settings.with_steam_key(cleaned)
        self.steam_client = SteamClient(cleaned)
        self.steam_service = SteamService(self.steam_client)

        # L'ancien client detient un pool de connexions : le fermer apres avoir
        # bascule evite toute fenetre pendant laquelle aucun client n'existe.
        if previous is not None:
            try:
                await previous.close()
            except Exception as exc:  # noqa: BLE001 - la bascule prime
                logger.debug("Fermeture de l'ancien client Steam : %s", exc)

        logger.info("Cle API Steam appliquee sans redemarrage.")
        return True

    def system_status(self) -> dict[str, Any]:
        installation = try_find_cs2(self.settings.cs2_path_override)
        return {
            "steam_api_configured": self.has_steam,
            "cs2_detected": installation is not None,
            "cs2_paths": installation.as_dict() if installation else None,
            "gsi_config_installed": is_installed(self.settings.cs2_path_override),
            "gsi_endpoint": self.settings.gsi_endpoint,
            "api_base_url": self.settings.api_base_url,
            "database": self.database.stats(),
            "recorder": self.recorder.status(),
            "steam_requests": (
                self.steam_client.request_count if self.steam_client else 0
            ),
            "cache": self.steam_client.cache.stats() if self.steam_client else None,
        }


def build_context(settings: Settings) -> AppContext:
    database = Database(settings.db_path)
    database.connect()

    players = PlayerRepository(database)
    matches = MatchRepository(database)

    steam_client: SteamClient | None = None
    steam_service: SteamService | None = None
    if settings.has_steam_key:
        steam_client = SteamClient(settings.steam_api_key)
        steam_service = SteamService(steam_client)
    else:
        logger.warning(
            "Aucune cle API Steam : les fonctions de profil resteront indisponibles."
        )

    return AppContext(
        settings=settings,
        database=database,
        live=LiveStateStore(),
        players=players,
        snapshots=SnapshotRepository(database),
        analyses=AnalysisRepository(database),
        matches=matches,
        settings_repo=SettingsRepository(database),
        audit=AuditRepository(database),
        player_matches=PlayerMatchRepository(database),
        teammates=TeammateRepository(database),
        faceit=FaceitClient(settings.faceit_api_key),
        recorder=MatchRecorder(matches, players, enabled=settings.record_matches),
        steam_client=steam_client,
        steam_service=steam_service,
    )


async def shutdown_context(context: AppContext) -> None:
    if context.steam_client is not None:
        await context.steam_client.close()
    if context.faceit is not None:
        await context.faceit.close()
    context.database.close()
