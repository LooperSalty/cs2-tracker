"""Moteur de diff : transforme deux instantanés GSI successifs en événements.

Le GSI n'émet pas d'événements, seulement des états. Toute la sémantique
(« kill », « bombe posée », « manche gagnée ») se déduit des transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from cs2tracker.core.utils import now_ts
from cs2tracker.gsi.models import GameState, GsiPlayer


class EventType(str, Enum):
    KILL = "kill"
    HEADSHOT_KILL = "headshot_kill"
    MULTI_KILL = "multi_kill"
    DEATH = "death"
    ASSIST = "assist"
    MVP = "mvp"
    ROUND_START = "round_start"
    ROUND_FREEZE = "round_freeze"
    ROUND_END = "round_end"
    BOMB_PLANTED = "bomb_planted"
    BOMB_DEFUSED = "bomb_defused"
    BOMB_EXPLODED = "bomb_exploded"
    MATCH_START = "match_start"
    MATCH_END = "match_end"
    MAP_CHANGE = "map_change"
    WEAPON_SWITCH = "weapon_switch"
    DAMAGE_TAKEN = "damage_taken"
    FLASHED = "flashed"
    LOW_HEALTH = "low_health"
    CONNECTION = "connection"


@dataclass(frozen=True, slots=True)
class GameEvent:
    """Événement de jeu horodaté et attribué à un joueur quand c'est pertinent."""

    type: EventType
    at: float
    round_number: int
    steamid: str = ""
    player_name: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "at": self.at,
            "round": self.round_number,
            "steamid": self.steamid,
            "player": self.player_name,
            "detail": dict(self.detail),
        }


#: Seuil de PV en dessous duquel on émet un événement « santé critique ».
_LOW_HEALTH_THRESHOLD = 25
#: Nombre de kills dans une manche à partir duquel on parle de multi-kill.
_MULTI_KILL_THRESHOLD = 3


def _players_of(state: GameState) -> dict[str, GsiPlayer]:
    """Index steamid → joueur, en fusionnant ``player`` et ``allplayers``."""
    players: dict[str, GsiPlayer] = {p.steamid: p for p in state.allplayers}
    if state.player and state.player.steamid:
        players.setdefault(state.player.steamid, state.player)
    return players


def _round_number(state: GameState) -> int:
    return state.map_state.round_number if state.map_state else 0


def diff_states(previous: GameState | None, current: GameState) -> tuple[GameEvent, ...]:
    """Produit la liste des événements survenus entre deux états."""
    at = current.received_at or now_ts()
    round_number = _round_number(current)

    if previous is None:
        return (
            GameEvent(
                type=EventType.CONNECTION,
                at=at,
                round_number=round_number,
                detail={"message": "Liaison GSI etablie"},
            ),
        )

    events: list[GameEvent] = []
    events.extend(_map_events(previous, current, at, round_number))
    events.extend(_round_events(previous, current, at, round_number))
    events.extend(_bomb_events(previous, current, at, round_number))
    events.extend(_player_events(previous, current, at, round_number))
    return tuple(events)


def _map_events(
    previous: GameState, current: GameState, at: float, round_number: int
) -> Iterable[GameEvent]:
    prev_map, curr_map = previous.map_state, current.map_state
    if curr_map is None:
        return
    if prev_map is None or prev_map.name != curr_map.name:
        yield GameEvent(
            type=EventType.MAP_CHANGE,
            at=at,
            round_number=round_number,
            detail={"map": curr_map.name, "mode": curr_map.mode},
        )
        return
    if prev_map.phase != curr_map.phase:
        if curr_map.phase == "live" and prev_map.phase in {"warmup", ""}:
            yield GameEvent(
                type=EventType.MATCH_START,
                at=at,
                round_number=round_number,
                detail={"map": curr_map.name, "mode": curr_map.mode},
            )
        elif curr_map.phase == "gameover":
            yield GameEvent(
                type=EventType.MATCH_END,
                at=at,
                round_number=round_number,
                detail={
                    "map": curr_map.name,
                    "score_ct": curr_map.team_ct.score if curr_map.team_ct else 0,
                    "score_t": curr_map.team_t.score if curr_map.team_t else 0,
                },
            )


def _round_events(
    previous: GameState, current: GameState, at: float, round_number: int
) -> Iterable[GameEvent]:
    prev_round, curr_round = previous.round_state, current.round_state
    if curr_round is None:
        return
    if prev_round is None or prev_round.phase == curr_round.phase:
        return
    if curr_round.phase == "freezetime":
        yield GameEvent(EventType.ROUND_FREEZE, at, round_number)
    elif curr_round.phase == "live":
        yield GameEvent(EventType.ROUND_START, at, round_number)
    elif curr_round.phase == "over":
        yield GameEvent(
            type=EventType.ROUND_END,
            at=at,
            round_number=round_number,
            detail={"win_team": curr_round.win_team},
        )


def _bomb_events(
    previous: GameState, current: GameState, at: float, round_number: int
) -> Iterable[GameEvent]:
    prev_bomb, curr_bomb = previous.bomb, current.bomb
    if curr_bomb is None:
        return
    prev_state = prev_bomb.state if prev_bomb else ""
    if prev_state == curr_bomb.state:
        return
    mapping = {
        "planted": EventType.BOMB_PLANTED,
        "defused": EventType.BOMB_DEFUSED,
        "exploded": EventType.BOMB_EXPLODED,
    }
    event_type = mapping.get(curr_bomb.state)
    if event_type is not None:
        yield GameEvent(
            type=event_type,
            at=at,
            round_number=round_number,
            steamid=curr_bomb.player_steamid,
            detail={"countdown": curr_bomb.countdown},
        )


def _player_events(
    previous: GameState, current: GameState, at: float, round_number: int
) -> Iterable[GameEvent]:
    prev_players = _players_of(previous)
    for steamid, player in _players_of(current).items():
        before = prev_players.get(steamid)
        if before is None:
            continue
        yield from _single_player_events(before, player, at, round_number)


def _single_player_events(
    before: GsiPlayer, after: GsiPlayer, at: float, round_number: int
) -> Iterable[GameEvent]:
    name = after.name or after.steamid

    prev_stats, curr_stats = before.match_stats, after.match_stats
    if prev_stats and curr_stats:
        kills_delta = curr_stats.kills - prev_stats.kills
        if kills_delta > 0:
            headshots_delta = 0
            if before.state and after.state:
                headshots_delta = max(0, after.state.round_killhs - before.state.round_killhs)
            yield GameEvent(
                type=EventType.HEADSHOT_KILL if headshots_delta > 0 else EventType.KILL,
                at=at,
                round_number=round_number,
                steamid=after.steamid,
                player_name=name,
                detail={
                    "count": kills_delta,
                    "headshots": headshots_delta,
                    "weapon": after.active_weapon.clean_name if after.active_weapon else None,
                    "round_kills": after.state.round_kills if after.state else 0,
                },
            )
        if curr_stats.deaths > prev_stats.deaths:
            yield GameEvent(
                type=EventType.DEATH,
                at=at,
                round_number=round_number,
                steamid=after.steamid,
                player_name=name,
                detail={"total_deaths": curr_stats.deaths},
            )
        if curr_stats.assists > prev_stats.assists:
            yield GameEvent(
                type=EventType.ASSIST,
                at=at,
                round_number=round_number,
                steamid=after.steamid,
                player_name=name,
            )
        if curr_stats.mvps > prev_stats.mvps:
            yield GameEvent(
                type=EventType.MVP,
                at=at,
                round_number=round_number,
                steamid=after.steamid,
                player_name=name,
            )

    prev_state, curr_state = before.state, after.state
    if prev_state and curr_state:
        if (
            curr_state.round_kills >= _MULTI_KILL_THRESHOLD
            and curr_state.round_kills > prev_state.round_kills
        ):
            yield GameEvent(
                type=EventType.MULTI_KILL,
                at=at,
                round_number=round_number,
                steamid=after.steamid,
                player_name=name,
                detail={"kills": curr_state.round_kills},
            )
        damage_taken = prev_state.health - curr_state.health
        if damage_taken > 0 and curr_state.health > 0:
            yield GameEvent(
                type=EventType.DAMAGE_TAKEN,
                at=at,
                round_number=round_number,
                steamid=after.steamid,
                player_name=name,
                detail={"amount": damage_taken, "health": curr_state.health},
            )
            if curr_state.health <= _LOW_HEALTH_THRESHOLD:
                yield GameEvent(
                    type=EventType.LOW_HEALTH,
                    at=at,
                    round_number=round_number,
                    steamid=after.steamid,
                    player_name=name,
                    detail={"health": curr_state.health},
                )
        if curr_state.flashed > 0 and prev_state.flashed == 0:
            yield GameEvent(
                type=EventType.FLASHED,
                at=at,
                round_number=round_number,
                steamid=after.steamid,
                player_name=name,
                detail={"intensity": curr_state.flashed},
            )

    before_weapon = before.active_weapon
    after_weapon = after.active_weapon
    if after_weapon and (before_weapon is None or before_weapon.name != after_weapon.name):
        yield GameEvent(
            type=EventType.WEAPON_SWITCH,
            at=at,
            round_number=round_number,
            steamid=after.steamid,
            player_name=name,
            detail={
                "from": before_weapon.clean_name if before_weapon else None,
                "to": after_weapon.clean_name,
            },
        )
