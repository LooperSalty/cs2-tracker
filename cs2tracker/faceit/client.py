"""Client de l'API FACEIT.

**Pourquoi FACEIT et pas le rang Premier de CS2.** Le classement Premier n'est
pas exposé par l'API Steam : l'obtenir supposerait de dialoguer avec le Game
Coordinator via un compte Steam connecté — lourd, fragile, et à la limite des
conditions d'utilisation.

FACEIT publie au contraire une API documentée et gratuite, qui donne le niveau,
l'ELO, et surtout des **statistiques par match** — ce que Steam ne fournit
jamais. C'est le seul classement compétitif réellement accessible, et il sert
aussi à segmenter les références de comparaison (voir ``anticheat/tiers.py``).

Une clé FACEIT est nécessaire, distincte de la clé Steam. Sans elle, toutes les
fonctions dégradent proprement plutôt que d'échouer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import httpx

from cs2tracker.constants import HTTP_TIMEOUT_SECONDS
from cs2tracker.core.utils import safe_div, to_float, to_int
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

API_BASE = "https://open.faceit.com/data/v4"
#: Identifiant du jeu CS2 chez FACEIT (« csgo » designe l'ancien titre).
GAME_ID = "cs2"


@dataclass(frozen=True, slots=True)
class FaceitProfile:
    """Profil FACEIT d'un joueur, réduit à ce qui nous sert."""

    player_id: str
    nickname: str
    country: str
    level: int
    elo: int
    avatar: str
    faceit_url: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "nickname": self.nickname,
            "country": self.country,
            "level": self.level,
            "elo": self.elo,
            "avatar": self.avatar,
            "url": self.faceit_url,
        }


@dataclass(frozen=True, slots=True)
class FaceitMatch:
    """Un match FACEIT, avec les statistiques individuelles du joueur."""

    match_id: str
    played_at: int
    map_name: str
    rounds: int
    kills: int
    deaths: int
    assists: int
    headshots: int
    mvps: int
    won: bool
    #: FACEIT ne publie pas les degats bruts : l'ADR est fourni tel quel.
    adr: float = 0.0

    @property
    def kills_per_round(self) -> float:
        return safe_div(self.kills, self.rounds)

    def as_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "played_at": self.played_at,
            "map": self.map_name,
            "rounds": self.rounds,
            "kills": self.kills,
            "deaths": self.deaths,
            "assists": self.assists,
            "headshots": self.headshots,
            "mvps": self.mvps,
            "won": self.won,
            "adr": round(self.adr, 1),
            "kd": round(safe_div(self.kills, self.deaths), 3),
        }


class FaceitUnavailable(Exception):
    """Aucune clé FACEIT configurée, ou service injoignable."""


class FaceitClient:
    """Accès en lecture seule à l'API FACEIT."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key.strip()
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def start(self) -> None:
        if self._client is None and self.configured:
            self._client = httpx.AsyncClient(
                base_url=API_BASE,
                timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                },
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise FaceitUnavailable("Aucune cle FACEIT configuree.")
        await self.start()
        assert self._client is not None

        try:
            response = await self._client.get(path, params=dict(params or {}))
        except httpx.HTTPError as exc:
            raise FaceitUnavailable(f"FACEIT injoignable : {exc}") from exc

        if response.status_code == 404:
            return {}
        if response.status_code in {401, 403}:
            raise FaceitUnavailable("Cle FACEIT refusee.")
        if response.status_code != 200:
            raise FaceitUnavailable(f"FACEIT a repondu {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise FaceitUnavailable("Reponse FACEIT illisible.") from exc
        return payload if isinstance(payload, dict) else {}

    # --- profil --------------------------------------------------------------
    async def profile_by_steamid(self, steamid64: str) -> FaceitProfile | None:
        """Retrouve un joueur FACEIT depuis son SteamID64.

        Beaucoup de joueurs n'ont pas de compte FACEIT : l'absence de résultat
        est un cas normal, pas une erreur.
        """
        payload = await self._get(
            "/players", {"game": GAME_ID, "game_player_id": steamid64}
        )
        if not payload or not payload.get("player_id"):
            return None

        games = payload.get("games") or {}
        cs2 = games.get(GAME_ID) or games.get("csgo") or {}

        return FaceitProfile(
            player_id=str(payload.get("player_id", "")),
            nickname=str(payload.get("nickname", "")),
            country=str(payload.get("country", "")),
            level=to_int(cs2.get("skill_level")),
            elo=to_int(cs2.get("faceit_elo")),
            avatar=str(payload.get("avatar", "")),
            faceit_url=str(payload.get("faceit_url", "")).replace("{lang}", "fr"),
        )

    # --- statistiques --------------------------------------------------------
    async def lifetime_stats(self, player_id: str) -> dict[str, Any]:
        payload = await self._get(f"/players/{player_id}/stats/{GAME_ID}")
        lifetime = payload.get("lifetime") or {}
        if not lifetime:
            return {}
        return {
            "matches": to_int(lifetime.get("Matches")),
            "wins": to_int(lifetime.get("Wins")),
            "win_rate": to_float(lifetime.get("Win Rate %")) / 100.0,
            "kd": to_float(lifetime.get("Average K/D Ratio")),
            "headshot_rate": to_float(lifetime.get("Average Headshots %")) / 100.0,
            "longest_win_streak": to_int(lifetime.get("Longest Win Streak")),
            "current_win_streak": to_int(lifetime.get("Current Win Streak")),
        }

    async def recent_matches(
        self, player_id: str, limit: int = 30
    ) -> tuple[FaceitMatch, ...]:
        """Derniers matchs avec les statistiques individuelles du joueur."""
        payload = await self._get(
            f"/players/{player_id}/games/{GAME_ID}/stats",
            {"offset": 0, "limit": min(limit, 100)},
        )
        items = payload.get("items")
        if not isinstance(items, Sequence):
            return ()

        matches: list[FaceitMatch] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            stats = item.get("stats") or {}
            matches.append(
                FaceitMatch(
                    match_id=str(stats.get("Match Id", "")),
                    played_at=to_int(stats.get("Match Finished At")) // 1000,
                    map_name=str(stats.get("Map", "")),
                    rounds=to_int(stats.get("Rounds")),
                    kills=to_int(stats.get("Kills")),
                    deaths=to_int(stats.get("Deaths")),
                    assists=to_int(stats.get("Assists")),
                    headshots=to_int(stats.get("Headshots")),
                    mvps=to_int(stats.get("MVPs")),
                    won=to_int(stats.get("Result")) == 1,
                    adr=to_float(stats.get("ADR")),
                )
            )
        return tuple(matches)


@dataclass(frozen=True, slots=True)
class FaceitSnapshot:
    """Tout ce que FACEIT sait d'un joueur, en une structure."""

    available: bool
    reason: str = ""
    profile: FaceitProfile | None = None
    lifetime: Mapping[str, Any] = field(default_factory=dict)
    matches: tuple[FaceitMatch, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "profile": self.profile.as_dict() if self.profile else None,
            "lifetime": dict(self.lifetime),
            "matches": [match.as_dict() for match in self.matches],
        }


async def fetch_snapshot(
    client: FaceitClient, steamid64: str, match_limit: int = 30
) -> FaceitSnapshot:
    """Charge profil, statistiques et matchs. Ne lève jamais."""
    if not client.configured:
        return FaceitSnapshot(
            available=False,
            reason=(
                "Aucune cle FACEIT configuree. Elle est gratuite sur "
                "developers.faceit.com et s'ajoute dans l'onglet Configuration."
            ),
        )

    try:
        profile = await client.profile_by_steamid(steamid64)
    except FaceitUnavailable as exc:
        return FaceitSnapshot(available=False, reason=str(exc))

    if profile is None:
        return FaceitSnapshot(
            available=False, reason="Ce joueur n'a pas de compte FACEIT."
        )

    try:
        lifetime = await client.lifetime_stats(profile.player_id)
        matches = await client.recent_matches(profile.player_id, limit=match_limit)
    except FaceitUnavailable as exc:
        # Le profil seul reste utile : il porte le niveau, qui sert a segmenter
        # les references de comparaison.
        logger.info("Statistiques FACEIT partielles : %s", exc)
        return FaceitSnapshot(available=True, profile=profile, reason=str(exc))

    return FaceitSnapshot(
        available=True, profile=profile, lifetime=lifetime, matches=matches
    )
