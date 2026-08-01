"""Service métier Steam : agrège les endpoints en vues exploitables.

Les appels indépendants sont lancés en parallèle (``asyncio.gather``) et les
échecs partiels sont collectés plutôt que propagés : un profil dont seuls les
amis sont privés reste analysable.
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Sequence

from cs2tracker.constants import (
    CACHE_TTL_BANS_SECONDS,
    CACHE_TTL_PROFILE_SECONDS,
    CACHE_TTL_SCHEMA_SECONDS,
    CACHE_TTL_STATS_SECONDS,
    CS2_APP_ID,
)
from cs2tracker.core.errors import (
    Cs2TrackerError,
    InvalidSteamIdError,
    PlayerNotFoundError,
    ProfilePrivateError,
)
from cs2tracker.core.models import BanStatus, Cs2Stats, PlayerProfile, PlayerSummary
from cs2tracker.core.steamid import SteamIdentity, from_steamid64, parse
from cs2tracker.core.utils import chunked, to_int
from cs2tracker.logging_setup import get_logger
from cs2tracker.steam import endpoints, parsers
from cs2tracker.steam.client import SteamClient

logger = get_logger(__name__)


class SteamService:
    """Point d'entrée unique pour toute donnée provenant de Steam."""

    def __init__(self, client: SteamClient) -> None:
        self._client = client

    # ------------------------------------------------------------------ ident
    async def resolve(self, query: str) -> SteamIdentity:
        """Résout n'importe quelle saisie (URL, vanity, SteamID2/3/64)."""
        request = parse(query)
        if request.identity is not None:
            return request.identity

        payload = await self._client.get_json(
            endpoints.RESOLVE_VANITY,
            {"vanityurl": request.vanity},
            ttl_seconds=CACHE_TTL_PROFILE_SECONDS,
        )
        response = payload.get("response", {})
        if to_int(response.get("success")) != 1 or not response.get("steamid"):
            raise PlayerNotFoundError(
                f"Vanity introuvable: {request.vanity}",
            )
        return from_steamid64(response["steamid"])

    # --------------------------------------------------------------- profils
    async def get_summaries(
        self, steamids: Sequence[str]
    ) -> dict[str, PlayerSummary]:
        """Résumés de profil par lots de 100 (limite Steam)."""
        if not steamids:
            return {}
        results: dict[str, PlayerSummary] = {}
        for batch in chunked(list(steamids), endpoints.MAX_STEAMIDS_PER_BATCH):
            payload = await self._client.get_json(
                endpoints.PLAYER_SUMMARIES,
                {"steamids": ",".join(batch)},
                ttl_seconds=CACHE_TTL_PROFILE_SECONDS,
            )
            players = payload.get("response", {}).get("players", [])
            for entry in players:
                if isinstance(entry, Mapping):
                    summary = parsers.parse_player_summary(entry)
                    results[summary.steamid64] = summary
        return results

    async def get_summary(self, steamid64: str) -> PlayerSummary:
        summaries = await self.get_summaries([steamid64])
        summary = summaries.get(steamid64)
        if summary is None:
            raise PlayerNotFoundError(f"Aucun profil pour {steamid64}")
        return summary

    async def get_bans(self, steamids: Sequence[str]) -> dict[str, BanStatus]:
        if not steamids:
            return {}
        results: dict[str, BanStatus] = {}
        for batch in chunked(list(steamids), endpoints.MAX_STEAMIDS_PER_BATCH):
            payload = await self._client.get_json(
                endpoints.PLAYER_BANS,
                {"steamids": ",".join(batch)},
                ttl_seconds=CACHE_TTL_BANS_SECONDS,
            )
            for entry in payload.get("players", []):
                if isinstance(entry, Mapping):
                    ban = parsers.parse_ban_status(entry)
                    results[ban.steamid64] = ban
        return results

    async def get_ban(self, steamid64: str) -> BanStatus | None:
        return (await self.get_bans([steamid64])).get(steamid64)

    # ----------------------------------------------------------------- stats
    async def get_cs2_stats(self, steamid64: str) -> Cs2Stats | None:
        payload = await self._client.get_json(
            endpoints.USER_STATS_FOR_GAME,
            {"steamid": steamid64, "appid": CS2_APP_ID},
            ttl_seconds=CACHE_TTL_STATS_SECONDS,
            allow_private=True,
        )
        if not payload:
            raise ProfilePrivateError()
        return parsers.parse_cs2_stats(steamid64, payload)

    async def get_achievements(self, steamid64: str) -> tuple[int, int]:
        payload = await self._client.get_json(
            endpoints.PLAYER_ACHIEVEMENTS,
            {"steamid": steamid64, "appid": CS2_APP_ID, "l": "french"},
            ttl_seconds=CACHE_TTL_STATS_SECONDS,
            allow_private=True,
        )
        return parsers.parse_achievements(payload)

    async def get_owned_games(self, steamid64: str) -> tuple[Any, ...]:
        payload = await self._client.get_json(
            endpoints.OWNED_GAMES,
            {
                "steamid": steamid64,
                "include_appinfo": 1,
                "include_played_free_games": 1,
            },
            ttl_seconds=CACHE_TTL_PROFILE_SECONDS,
            allow_private=True,
        )
        return parsers.parse_owned_games(payload)

    async def get_steam_level(self, steamid64: str) -> int:
        payload = await self._client.get_json(
            endpoints.STEAM_LEVEL,
            {"steamid": steamid64},
            ttl_seconds=CACHE_TTL_PROFILE_SECONDS,
            allow_private=True,
        )
        return to_int(payload.get("response", {}).get("player_level"))

    async def get_badges_count(self, steamid64: str) -> int:
        payload = await self._client.get_json(
            endpoints.BADGES,
            {"steamid": steamid64},
            ttl_seconds=CACHE_TTL_PROFILE_SECONDS,
            allow_private=True,
        )
        badges = payload.get("response", {}).get("badges", [])
        return len(badges) if isinstance(badges, Sequence) else 0

    async def get_friends(self, steamid64: str) -> tuple[Mapping[str, Any], ...]:
        payload = await self._client.get_json(
            endpoints.FRIEND_LIST,
            {"steamid": steamid64, "relationship": "friend"},
            ttl_seconds=CACHE_TTL_PROFILE_SECONDS,
            allow_private=True,
        )
        friends = payload.get("friendslist", {}).get("friends", [])
        return tuple(f for f in friends if isinstance(f, Mapping))

    async def get_recently_played(self, steamid64: str) -> tuple[Any, ...]:
        payload = await self._client.get_json(
            endpoints.RECENTLY_PLAYED,
            {"steamid": steamid64},
            ttl_seconds=CACHE_TTL_PROFILE_SECONDS,
            allow_private=True,
        )
        games = payload.get("response", {}).get("games", [])
        return tuple(g for g in games if isinstance(g, Mapping))

    # ------------------------------------------------------------- meta jeu
    async def get_game_schema(self) -> Mapping[str, Any]:
        payload = await self._client.get_json(
            endpoints.SCHEMA_FOR_GAME,
            {"appid": CS2_APP_ID, "l": "french"},
            ttl_seconds=CACHE_TTL_SCHEMA_SECONDS,
            allow_private=True,
        )
        return payload.get("game", {})

    async def get_current_players(self) -> int:
        payload = await self._client.get_json(
            endpoints.CURRENT_PLAYERS,
            {"appid": CS2_APP_ID},
            ttl_seconds=60,
            allow_private=True,
        )
        return to_int(payload.get("response", {}).get("player_count"))

    async def get_servers_status(self) -> Mapping[str, Any]:
        payload = await self._client.get_json(
            endpoints.CS2_SERVERS_STATUS, {}, ttl_seconds=120, allow_private=True
        )
        return payload.get("result", {})

    # ------------------------------------------------------------- agrégation
    async def get_full_profile(self, query: str) -> PlayerProfile:
        """Vue complète : profil + bans + stats + méta-compte + succès.

        Chaque sous-appel est isolé : une ressource privée n'annule pas le reste.
        """
        identity = await self.resolve(query)
        steamid = str(identity.steamid64)

        tasks = {
            "summary": self.get_summary(steamid),
            "ban": self.get_ban(steamid),
            "stats": self.get_cs2_stats(steamid),
            "games": self.get_owned_games(steamid),
            "level": self.get_steam_level(steamid),
            "badges": self.get_badges_count(steamid),
            "friends": self.get_friends(steamid),
            "achievements": self.get_achievements(steamid),
        }
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        results = dict(zip(tasks.keys(), gathered))

        errors: list[str] = []

        def unwrap(name: str, default: Any) -> Any:
            value = results.get(name)
            if isinstance(value, BaseException):
                message = (
                    value.user_message
                    if isinstance(value, Cs2TrackerError)
                    else "erreur inattendue"
                )
                errors.append(f"{name}: {message}")
                logger.info("Sous-appel '%s' indisponible: %s", name, value)
                return default
            return value

        summary = unwrap("summary", None)
        ban = unwrap("ban", None)
        stats = unwrap("stats", None)
        games = unwrap("games", ())
        level = unwrap("level", 0)
        badges = unwrap("badges", 0)
        friends = unwrap("friends", ())
        achievements = unwrap("achievements", (0, 0))

        account = parsers.build_account_overview(
            games=games,
            steam_level=level,
            friends=friends,
            badges_count=badges,
            cs2_app_id=CS2_APP_ID,
        )

        return PlayerProfile(
            identity=identity.as_dict(),
            summary=summary,
            bans=ban,
            stats=stats,
            account=account,
            achievements_unlocked=achievements[0],
            achievements_total=achievements[1],
            errors=tuple(errors),
        )

    async def get_lobby_profiles(
        self, queries: Sequence[str]
    ) -> tuple[PlayerProfile, ...]:
        """Charge en parallèle jusqu'à 10 joueurs (lobby complet)."""
        if not queries:
            return ()
        results = await asyncio.gather(
            *(self.get_full_profile(q) for q in queries), return_exceptions=True
        )
        profiles: list[PlayerProfile] = []
        for query, result in zip(queries, results):
            if isinstance(result, BaseException):
                logger.warning("Profil '%s' non charge: %s", query, result)
                continue
            profiles.append(result)
        return tuple(profiles)


def describe_identity(query: str) -> dict[str, Any]:
    """Analyse hors-ligne d'une saisie (aucun appel réseau)."""
    request = parse(query)
    if request.identity is not None:
        return {"resolved": True, **request.identity.as_dict()}
    if request.vanity:
        return {"resolved": False, "vanity": request.vanity}
    raise InvalidSteamIdError(f"Saisie non interpretable: {query!r}")
