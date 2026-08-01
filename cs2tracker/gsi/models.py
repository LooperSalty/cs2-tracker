"""Modèles immuables du Game State Integration de CS2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from cs2tracker.core.utils import safe_div


@dataclass(frozen=True, slots=True)
class Provider:
    name: str
    appid: int
    version: int
    steamid: str
    timestamp: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "appid": self.appid,
            "version": self.version,
            "steamid": self.steamid,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True, slots=True)
class TeamState:
    score: int
    consecutive_round_losses: int
    timeouts_remaining: int
    matches_won_this_series: int
    name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "consecutive_round_losses": self.consecutive_round_losses,
            "timeouts_remaining": self.timeouts_remaining,
            "matches_won_this_series": self.matches_won_this_series,
        }


@dataclass(frozen=True, slots=True)
class MapState:
    name: str
    mode: str
    phase: str
    round_number: int
    team_ct: TeamState | None
    team_t: TeamState | None
    num_matches_to_win_series: int
    current_spectators: int
    round_wins: Mapping[str, str] = field(default_factory=dict)

    @property
    def total_score(self) -> int:
        ct = self.team_ct.score if self.team_ct else 0
        t = self.team_t.score if self.team_t else 0
        return ct + t

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode,
            "phase": self.phase,
            "round": self.round_number,
            "team_ct": self.team_ct.as_dict() if self.team_ct else None,
            "team_t": self.team_t.as_dict() if self.team_t else None,
            "num_matches_to_win_series": self.num_matches_to_win_series,
            "current_spectators": self.current_spectators,
            "round_wins": dict(self.round_wins),
        }


@dataclass(frozen=True, slots=True)
class RoundState:
    phase: str
    bomb: str
    win_team: str

    def as_dict(self) -> dict[str, Any]:
        return {"phase": self.phase, "bomb": self.bomb, "win_team": self.win_team}


@dataclass(frozen=True, slots=True)
class PlayerState:
    health: int
    armor: int
    helmet: bool
    defusekit: bool
    flashed: int
    smoked: int
    burning: int
    money: int
    round_kills: int
    round_killhs: int
    round_totaldmg: int
    equip_value: int

    @property
    def is_alive(self) -> bool:
        return self.health > 0

    @property
    def round_headshot_rate(self) -> float:
        return safe_div(self.round_killhs, self.round_kills)

    def as_dict(self) -> dict[str, Any]:
        return {
            "health": self.health,
            "armor": self.armor,
            "helmet": self.helmet,
            "defusekit": self.defusekit,
            "flashed": self.flashed,
            "smoked": self.smoked,
            "burning": self.burning,
            "money": self.money,
            "round_kills": self.round_kills,
            "round_headshot_kills": self.round_killhs,
            "round_damage": self.round_totaldmg,
            "equipment_value": self.equip_value,
            "alive": self.is_alive,
        }


@dataclass(frozen=True, slots=True)
class MatchStats:
    kills: int
    assists: int
    deaths: int
    mvps: int
    score: int

    @property
    def kd(self) -> float:
        return safe_div(self.kills, self.deaths)

    @property
    def kda(self) -> float:
        return safe_div(self.kills + self.assists, self.deaths)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kills": self.kills,
            "assists": self.assists,
            "deaths": self.deaths,
            "mvps": self.mvps,
            "score": self.score,
            "kd": round(self.kd, 3),
            "kda": round(self.kda, 3),
        }


@dataclass(frozen=True, slots=True)
class Weapon:
    slot: str
    name: str
    paintkit: str
    weapon_type: str
    state: str
    ammo_clip: int
    ammo_clip_max: int
    ammo_reserve: int

    @property
    def is_active(self) -> bool:
        return self.state == "active"

    @property
    def clean_name(self) -> str:
        return self.name.removeprefix("weapon_")

    def as_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "name": self.clean_name,
            "raw_name": self.name,
            "skin": self.paintkit,
            "type": self.weapon_type,
            "state": self.state,
            "ammo_clip": self.ammo_clip,
            "ammo_clip_max": self.ammo_clip_max,
            "ammo_reserve": self.ammo_reserve,
            "active": self.is_active,
        }


@dataclass(frozen=True, slots=True)
class Vector3:
    x: float
    y: float
    z: float

    def as_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 2), "y": round(self.y, 2), "z": round(self.z, 2)}


@dataclass(frozen=True, slots=True)
class GsiPlayer:
    steamid: str
    name: str
    clan: str
    team: str
    activity: str
    observer_slot: int
    state: PlayerState | None
    match_stats: MatchStats | None
    weapons: tuple[Weapon, ...]
    position: Vector3 | None
    forward: Vector3 | None

    @property
    def active_weapon(self) -> Weapon | None:
        return next((w for w in self.weapons if w.is_active), None)

    @property
    def has_bomb(self) -> bool:
        return any(w.name == "weapon_c4" for w in self.weapons)

    @property
    def utility_count(self) -> int:
        return sum(1 for w in self.weapons if w.weapon_type == "Grenade")

    def as_dict(self) -> dict[str, Any]:
        active = self.active_weapon
        return {
            "steamid": self.steamid,
            "name": self.name,
            "clan": self.clan,
            "team": self.team,
            "activity": self.activity,
            "observer_slot": self.observer_slot,
            "state": self.state.as_dict() if self.state else None,
            "match_stats": self.match_stats.as_dict() if self.match_stats else None,
            "weapons": [w.as_dict() for w in self.weapons],
            "active_weapon": active.clean_name if active else None,
            "has_bomb": self.has_bomb,
            "utility_count": self.utility_count,
            "position": self.position.as_dict() if self.position else None,
            "forward": self.forward.as_dict() if self.forward else None,
        }


@dataclass(frozen=True, slots=True)
class BombState:
    state: str
    countdown: float
    player_steamid: str
    position: Vector3 | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "countdown": round(self.countdown, 1),
            "carrier": self.player_steamid,
            "position": self.position.as_dict() if self.position else None,
        }


@dataclass(frozen=True, slots=True)
class PhaseCountdown:
    phase: str
    ends_in: float

    def as_dict(self) -> dict[str, Any]:
        return {"phase": self.phase, "ends_in": round(self.ends_in, 1)}


@dataclass(frozen=True, slots=True)
class GameState:
    """Instantané complet d'un payload GSI."""

    received_at: float
    provider: Provider | None
    map_state: MapState | None
    round_state: RoundState | None
    player: GsiPlayer | None
    allplayers: tuple[GsiPlayer, ...]
    bomb: BombState | None
    phase_countdown: PhaseCountdown | None
    grenades: Mapping[str, Any] = field(default_factory=dict)
    previously: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def in_match(self) -> bool:
        return self.map_state is not None and self.map_state.phase != "gameover"

    @property
    def is_spectating(self) -> bool:
        """Vrai si l'on observe (les données ``allplayers`` sont alors fournies)."""
        return bool(self.allplayers) and (
            self.player is None or self.player.activity == "textinput" or len(self.allplayers) > 1
        )

    def player_by_steamid(self, steamid: str) -> GsiPlayer | None:
        if self.player and self.player.steamid == steamid:
            return self.player
        return next((p for p in self.allplayers if p.steamid == steamid), None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "received_at": self.received_at,
            "provider": self.provider.as_dict() if self.provider else None,
            "map": self.map_state.as_dict() if self.map_state else None,
            "round": self.round_state.as_dict() if self.round_state else None,
            "player": self.player.as_dict() if self.player else None,
            "allplayers": [p.as_dict() for p in self.allplayers],
            "bomb": self.bomb.as_dict() if self.bomb else None,
            "phase_countdown": (
                self.phase_countdown.as_dict() if self.phase_countdown else None
            ),
            "grenades": dict(self.grenades),
            "in_match": self.in_match,
            "spectating": self.is_spectating,
        }
