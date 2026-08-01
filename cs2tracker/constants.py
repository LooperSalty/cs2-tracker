"""Constantes globales. Aucune valeur magique ne doit vivre ailleurs."""

from __future__ import annotations

from typing import Final

# --- Steam -------------------------------------------------------------------
CS2_APP_ID: Final[int] = 730
STEAM_API_BASE: Final[str] = "https://api.steampowered.com"
STEAM_COMMUNITY_BASE: Final[str] = "https://steamcommunity.com"

#: Offset de base des SteamID64 pour les comptes "individual" (universe 1, type 1).
STEAMID64_BASE: Final[int] = 76561197960265728

# --- Réseau ------------------------------------------------------------------
HTTP_TIMEOUT_SECONDS: Final[float] = 15.0
HTTP_MAX_RETRIES: Final[int] = 3
HTTP_BACKOFF_BASE_SECONDS: Final[float] = 0.6
#: Steam autorise ~100k requêtes/jour ; on se limite volontairement.
STEAM_RATE_LIMIT_PER_SECOND: Final[float] = 8.0

# --- Cache -------------------------------------------------------------------
CACHE_TTL_PROFILE_SECONDS: Final[int] = 300
CACHE_TTL_STATS_SECONDS: Final[int] = 120
CACHE_TTL_BANS_SECONDS: Final[int] = 600
CACHE_TTL_SCHEMA_SECONDS: Final[int] = 86_400
CACHE_MAX_ENTRIES: Final[int] = 2_048

# --- Game State Integration --------------------------------------------------
GSI_DEFAULT_HOST: Final[str] = "127.0.0.1"
GSI_DEFAULT_PORT: Final[int] = 8642
GSI_CONFIG_FILENAME: Final[str] = "gamestate_integration_cs2tracker.cfg"
#: Au-delà de ce délai sans payload, on considère le lien GSI comme mort.
GSI_STALE_AFTER_SECONDS: Final[float] = 30.0
GSI_EVENT_BUFFER_SIZE: Final[int] = 2_000

# --- Analyse anti-triche -----------------------------------------------------
SUSPICION_MIN: Final[float] = 0.0
SUSPICION_MAX: Final[float] = 100.0

#: Bornes basses inclusives de chaque palier de verdict.
VERDICT_BANDS: Final[tuple[tuple[float, str, str], ...]] = (
    (85.0, "CRITICAL", "Faisceau d'indices tres lourd"),
    (70.0, "HIGH", "Comportement fortement atypique"),
    (50.0, "MODERATE", "Plusieurs signaux inhabituels"),
    (30.0, "LOW", "Quelques ecarts mineurs"),
    (0.0, "CLEAN", "Rien d'anormal detecte"),
)

#: Nombre minimal d'observations pour qu'un detecteur soit pleinement confiant.
CONFIDENCE_FULL_SAMPLE: Final[int] = 5_000
CONFIDENCE_MIN_SAMPLE: Final[int] = 50

# --- Stockage ----------------------------------------------------------------
DB_FILENAME: Final[str] = "cs2tracker.db"
DB_SCHEMA_VERSION: Final[int] = 1

# --- Divers ------------------------------------------------------------------
SECONDS_PER_HOUR: Final[int] = 3_600
UNKNOWN: Final[str] = "unknown"
