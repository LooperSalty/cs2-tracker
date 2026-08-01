"""Modèles de domaine — tous immuables (``frozen=True``).

Aucune méthode ne modifie l'instance : les évolutions passent par
``dataclasses.replace`` qui produit une copie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from cs2tracker.core.utils import safe_div, ts_to_iso


@dataclass(frozen=True, slots=True)
class PlayerSummary:
    """``ISteamUser/GetPlayerSummaries``."""

    steamid64: str
    persona_name: str
    profile_url: str
    avatar: str
    avatar_medium: str
    avatar_full: str
    visibility_state: int
    profile_state: int
    last_logoff: int | None
    time_created: int | None
    persona_state: int
    country_code: str | None
    state_code: str | None
    real_name: str | None
    primary_clan_id: str | None
    game_id: str | None
    game_extra_info: str | None

    @property
    def is_public(self) -> bool:
        return self.visibility_state == 3

    @property
    def is_in_game(self) -> bool:
        return bool(self.game_id)

    @property
    def is_playing_cs2(self) -> bool:
        return self.game_id == "730"

    @property
    def persona_state_label(self) -> str:
        return {
            0: "Hors ligne",
            1: "En ligne",
            2: "Occupe",
            3: "Absent",
            4: "Ne pas deranger",
            5: "Echange",
            6: "Jeu",
        }.get(self.persona_state, "Inconnu")

    def as_dict(self) -> dict[str, Any]:
        return {
            "steamid64": self.steamid64,
            "persona_name": self.persona_name,
            "profile_url": self.profile_url,
            "avatar": self.avatar_full or self.avatar,
            "avatar_medium": self.avatar_medium,
            "visibility_state": self.visibility_state,
            "is_public": self.is_public,
            "profile_state": self.profile_state,
            "last_logoff": ts_to_iso(self.last_logoff),
            "time_created": ts_to_iso(self.time_created),
            "persona_state": self.persona_state,
            "persona_state_label": self.persona_state_label,
            "country_code": self.country_code,
            "state_code": self.state_code,
            "real_name": self.real_name,
            "primary_clan_id": self.primary_clan_id,
            "in_game": self.is_in_game,
            "playing_cs2": self.is_playing_cs2,
            "game_extra_info": self.game_extra_info,
        }


@dataclass(frozen=True, slots=True)
class BanStatus:
    """``ISteamUser/GetPlayerBans``."""

    steamid64: str
    community_banned: bool
    vac_banned: bool
    number_of_vac_bans: int
    days_since_last_ban: int
    number_of_game_bans: int
    economy_ban: str

    @property
    def has_any_ban(self) -> bool:
        return (
            self.community_banned
            or self.vac_banned
            or self.number_of_game_bans > 0
            or self.economy_ban.lower() not in {"none", ""}
        )

    @property
    def total_bans(self) -> int:
        return self.number_of_vac_bans + self.number_of_game_bans

    def as_dict(self) -> dict[str, Any]:
        return {
            "steamid64": self.steamid64,
            "community_banned": self.community_banned,
            "vac_banned": self.vac_banned,
            "number_of_vac_bans": self.number_of_vac_bans,
            "number_of_game_bans": self.number_of_game_bans,
            "days_since_last_ban": self.days_since_last_ban,
            "economy_ban": self.economy_ban,
            "has_any_ban": self.has_any_ban,
            "total_bans": self.total_bans,
        }


@dataclass(frozen=True, slots=True)
class WeaponStats:
    """Statistiques agrégées pour une arme donnée."""

    key: str
    display_name: str
    category: str
    kills: int
    shots_fired: int
    shots_hit: int

    @property
    def accuracy(self) -> float:
        return safe_div(self.shots_hit, self.shots_fired)

    @property
    def kills_per_hit(self) -> float:
        return safe_div(self.kills, self.shots_hit)

    @property
    def shots_per_kill(self) -> float:
        return safe_div(self.shots_fired, self.kills)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.display_name,
            "category": self.category,
            "kills": self.kills,
            "shots_fired": self.shots_fired,
            "shots_hit": self.shots_hit,
            "accuracy": round(self.accuracy, 4),
            "kills_per_hit": round(self.kills_per_hit, 4),
            "shots_per_kill": round(self.shots_per_kill, 2),
        }


@dataclass(frozen=True, slots=True)
class MapStats:
    """Statistiques agrégées pour une carte donnée."""

    key: str
    display_name: str
    rounds_played: int
    wins: int

    @property
    def win_rate(self) -> float:
        return safe_div(self.wins, self.rounds_played)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.display_name,
            "rounds_played": self.rounds_played,
            "wins": self.wins,
            "win_rate": round(self.win_rate, 4),
        }


@dataclass(frozen=True, slots=True)
class Cs2Stats:
    """Statistiques CS2/CS:GO à vie (``GetUserStatsForGame``)."""

    steamid64: str
    total_kills: int
    total_deaths: int
    total_time_played: int
    total_planted_bombs: int
    total_defused_bombs: int
    total_wins: int
    total_damage_done: int
    total_money_earned: int
    total_rescued_hostages: int
    total_kills_headshot: int
    total_shots_fired: int
    total_shots_hit: int
    total_rounds_played: int
    total_matches_played: int
    total_matches_won: int
    total_mvps: int
    total_contribution_score: int
    total_wins_pistolround: int
    last_match_kills: int
    last_match_deaths: int
    last_match_mvps: int
    last_match_damage: int
    last_match_rounds: int
    last_match_wins: int
    last_match_max_players: int
    last_match_money_spent: int
    last_match_favweapon_id: int
    weapons: tuple[WeaponStats, ...] = field(default_factory=tuple)
    maps: tuple[MapStats, ...] = field(default_factory=tuple)
    raw: Mapping[str, int] = field(default_factory=dict, repr=False)

    # --- ratios dérivés ------------------------------------------------------
    @property
    def kd_ratio(self) -> float:
        return safe_div(self.total_kills, self.total_deaths)

    @property
    def headshot_rate(self) -> float:
        return safe_div(self.total_kills_headshot, self.total_kills)

    @property
    def accuracy(self) -> float:
        return safe_div(self.total_shots_hit, self.total_shots_fired)

    @property
    def kills_per_round(self) -> float:
        return safe_div(self.total_kills, self.total_rounds_played)

    @property
    def deaths_per_round(self) -> float:
        return safe_div(self.total_deaths, self.total_rounds_played)

    @property
    def damage_per_round(self) -> float:
        return safe_div(self.total_damage_done, self.total_rounds_played)

    @property
    def damage_per_kill(self) -> float:
        return safe_div(self.total_damage_done, self.total_kills)

    @property
    def round_win_rate(self) -> float:
        return safe_div(self.total_wins, self.total_rounds_played)

    @property
    def match_win_rate(self) -> float:
        return safe_div(self.total_matches_won, self.total_matches_played)

    @property
    def mvp_rate(self) -> float:
        return safe_div(self.total_mvps, self.total_rounds_played)

    @property
    def hours_played(self) -> float:
        return self.total_time_played / 3600.0

    @property
    def kills_per_hour(self) -> float:
        return safe_div(self.total_kills, self.hours_played)

    @property
    def shots_per_kill(self) -> float:
        return safe_div(self.total_shots_fired, self.total_kills)

    @property
    def hits_per_kill(self) -> float:
        return safe_div(self.total_shots_hit, self.total_kills)

    @property
    def bomb_plant_rate(self) -> float:
        return safe_div(self.total_planted_bombs, self.total_rounds_played)

    @property
    def has_meaningful_sample(self) -> bool:
        return self.total_rounds_played >= 100 and self.total_kills >= 100

    def as_dict(self) -> dict[str, Any]:
        return {
            "steamid64": self.steamid64,
            "totals": {
                "kills": self.total_kills,
                "deaths": self.total_deaths,
                "assists_proxy_mvps": self.total_mvps,
                "time_played_seconds": self.total_time_played,
                "hours_played": round(self.hours_played, 1),
                "rounds_played": self.total_rounds_played,
                "matches_played": self.total_matches_played,
                "matches_won": self.total_matches_won,
                "rounds_won": self.total_wins,
                "damage_done": self.total_damage_done,
                "money_earned": self.total_money_earned,
                "headshot_kills": self.total_kills_headshot,
                "shots_fired": self.total_shots_fired,
                "shots_hit": self.total_shots_hit,
                "bombs_planted": self.total_planted_bombs,
                "bombs_defused": self.total_defused_bombs,
                "hostages_rescued": self.total_rescued_hostages,
                "pistol_rounds_won": self.total_wins_pistolround,
                "contribution_score": self.total_contribution_score,
            },
            "ratios": {
                "kd": round(self.kd_ratio, 3),
                "headshot_rate": round(self.headshot_rate, 4),
                "accuracy": round(self.accuracy, 4),
                "kills_per_round": round(self.kills_per_round, 3),
                "deaths_per_round": round(self.deaths_per_round, 3),
                "damage_per_round": round(self.damage_per_round, 2),
                "damage_per_kill": round(self.damage_per_kill, 2),
                "round_win_rate": round(self.round_win_rate, 4),
                "match_win_rate": round(self.match_win_rate, 4),
                "mvp_rate": round(self.mvp_rate, 4),
                "kills_per_hour": round(self.kills_per_hour, 2),
                "shots_per_kill": round(self.shots_per_kill, 2),
                "hits_per_kill": round(self.hits_per_kill, 2),
                "bomb_plant_rate": round(self.bomb_plant_rate, 4),
            },
            "last_match": {
                "kills": self.last_match_kills,
                "deaths": self.last_match_deaths,
                "mvps": self.last_match_mvps,
                "damage": self.last_match_damage,
                "rounds": self.last_match_rounds,
                "wins": self.last_match_wins,
                "max_players": self.last_match_max_players,
                "money_spent": self.last_match_money_spent,
                "favourite_weapon_id": self.last_match_favweapon_id,
                "kd": round(safe_div(self.last_match_kills, self.last_match_deaths), 3),
                "adr": round(safe_div(self.last_match_damage, self.last_match_rounds), 1),
            },
            "weapons": [weapon.as_dict() for weapon in self.weapons],
            "maps": [game_map.as_dict() for game_map in self.maps],
            "sample_is_meaningful": self.has_meaningful_sample,
        }


@dataclass(frozen=True, slots=True)
class OwnedGame:
    appid: int
    name: str
    playtime_forever_minutes: int
    playtime_2weeks_minutes: int
    last_played: int | None

    @property
    def hours(self) -> float:
        return self.playtime_forever_minutes / 60.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "appid": self.appid,
            "name": self.name,
            "hours": round(self.hours, 1),
            "hours_2weeks": round(self.playtime_2weeks_minutes / 60.0, 1),
            "last_played": ts_to_iso(self.last_played),
        }


@dataclass(frozen=True, slots=True)
class AccountOverview:
    """Signaux « méta-compte » utiles à l'analyse anti-triche."""

    steam_level: int
    games_owned: int
    cs2_hours: float
    cs2_hours_2weeks: float
    cs2_last_played: int | None
    friends_count: int
    friends_oldest_since: int | None
    badges_count: int
    total_playtime_hours: float

    @property
    def cs2_share_of_playtime(self) -> float:
        return safe_div(self.cs2_hours, self.total_playtime_hours)

    def as_dict(self) -> dict[str, Any]:
        return {
            "steam_level": self.steam_level,
            "games_owned": self.games_owned,
            "cs2_hours": round(self.cs2_hours, 1),
            "cs2_hours_2weeks": round(self.cs2_hours_2weeks, 1),
            "cs2_last_played": ts_to_iso(self.cs2_last_played),
            "friends_count": self.friends_count,
            "friends_oldest_since": ts_to_iso(self.friends_oldest_since),
            "badges_count": self.badges_count,
            "total_playtime_hours": round(self.total_playtime_hours, 1),
            "cs2_share_of_playtime": round(self.cs2_share_of_playtime, 3),
        }


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    """Vue agrégée complète d'un joueur."""

    identity: dict[str, Any]
    summary: PlayerSummary | None
    bans: BanStatus | None
    stats: Cs2Stats | None
    account: AccountOverview | None
    achievements_unlocked: int
    achievements_total: int
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def achievement_rate(self) -> float:
        return safe_div(self.achievements_unlocked, self.achievements_total)

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "summary": self.summary.as_dict() if self.summary else None,
            "bans": self.bans.as_dict() if self.bans else None,
            "stats": self.stats.as_dict() if self.stats else None,
            "account": self.account.as_dict() if self.account else None,
            "achievements": {
                "unlocked": self.achievements_unlocked,
                "total": self.achievements_total,
                "rate": round(self.achievement_rate, 3),
            },
            "partial_errors": list(self.errors),
        }
