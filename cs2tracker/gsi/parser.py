"""Décodage des payloads JSON envoyés par CS2 vers nos modèles immuables.

Le format GSI varie selon le contexte (joueur, spectateur, GOTV, menu) : le
parseur ne suppose la présence d'aucun bloc.
"""

from __future__ import annotations

from typing import Any, Mapping

from cs2tracker.core.utils import now_ts, to_float, to_int
from cs2tracker.gsi.models import (
    BombState,
    GameState,
    GsiPlayer,
    MapState,
    MatchStats,
    PhaseCountdown,
    PlayerState,
    Provider,
    RoundState,
    TeamState,
    Vector3,
    Weapon,
)
from cs2tracker.steam.maps import normalize_map_name


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parse_vector(raw: Any) -> Vector3 | None:
    """``"1.00, 2.00, 3.00"`` → ``Vector3``."""
    if not isinstance(raw, str):
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        return None
    return Vector3(x=to_float(parts[0]), y=to_float(parts[1]), z=to_float(parts[2]))


def _parse_provider(raw: Any) -> Provider | None:
    data = _as_mapping(raw)
    if not data:
        return None
    return Provider(
        name=str(data.get("name", "")),
        appid=to_int(data.get("appid")),
        version=to_int(data.get("version")),
        steamid=str(data.get("steamid", "")),
        timestamp=to_int(data.get("timestamp")),
    )


def _parse_team(raw: Any, side: str) -> TeamState | None:
    data = _as_mapping(raw)
    if not data:
        return None
    return TeamState(
        score=to_int(data.get("score")),
        consecutive_round_losses=to_int(data.get("consecutive_round_losses")),
        timeouts_remaining=to_int(data.get("timeouts_remaining")),
        matches_won_this_series=to_int(data.get("matches_won_this_series")),
        name=str(data.get("name", side)),
    )


def _parse_map(raw: Any) -> MapState | None:
    data = _as_mapping(raw)
    if not data:
        return None
    round_wins = data.get("round_wins")
    return MapState(
        name=normalize_map_name(str(data.get("name", ""))),
        mode=str(data.get("mode", "")),
        phase=str(data.get("phase", "")),
        round_number=to_int(data.get("round")),
        team_ct=_parse_team(data.get("team_ct"), "CT"),
        team_t=_parse_team(data.get("team_t"), "T"),
        num_matches_to_win_series=to_int(data.get("num_matches_to_win_series")),
        current_spectators=to_int(data.get("current_spectators")),
        round_wins={
            str(k): str(v) for k, v in _as_mapping(round_wins).items()
        },
    )


def _parse_round(raw: Any) -> RoundState | None:
    data = _as_mapping(raw)
    if not data:
        return None
    return RoundState(
        phase=str(data.get("phase", "")),
        bomb=str(data.get("bomb", "")),
        win_team=str(data.get("win_team", "")),
    )


def _parse_player_state(raw: Any) -> PlayerState | None:
    data = _as_mapping(raw)
    if not data:
        return None
    return PlayerState(
        health=to_int(data.get("health")),
        armor=to_int(data.get("armor")),
        helmet=bool(data.get("helmet", False)),
        defusekit=bool(data.get("defusekit", False)),
        flashed=to_int(data.get("flashed")),
        smoked=to_int(data.get("smoked")),
        burning=to_int(data.get("burning")),
        money=to_int(data.get("money")),
        round_kills=to_int(data.get("round_kills")),
        round_killhs=to_int(data.get("round_killhs")),
        round_totaldmg=to_int(data.get("round_totaldmg")),
        equip_value=to_int(data.get("equip_value")),
    )


def _parse_match_stats(raw: Any) -> MatchStats | None:
    data = _as_mapping(raw)
    if not data:
        return None
    return MatchStats(
        kills=to_int(data.get("kills")),
        assists=to_int(data.get("assists")),
        deaths=to_int(data.get("deaths")),
        mvps=to_int(data.get("mvps")),
        score=to_int(data.get("score")),
    )


def _parse_weapons(raw: Any) -> tuple[Weapon, ...]:
    data = _as_mapping(raw)
    weapons: list[Weapon] = []
    for slot, entry in sorted(data.items()):
        info = _as_mapping(entry)
        if not info:
            continue
        weapons.append(
            Weapon(
                slot=str(slot),
                name=str(info.get("name", "")),
                paintkit=str(info.get("paintkit", "default")),
                weapon_type=str(info.get("type", "")),
                state=str(info.get("state", "")),
                ammo_clip=to_int(info.get("ammo_clip")),
                ammo_clip_max=to_int(info.get("ammo_clip_max")),
                ammo_reserve=to_int(info.get("ammo_reserve")),
            )
        )
    return tuple(weapons)


def _parse_player(raw: Any, steamid_hint: str = "") -> GsiPlayer | None:
    data = _as_mapping(raw)
    if not data:
        return None
    return GsiPlayer(
        steamid=str(data.get("steamid", steamid_hint)),
        name=str(data.get("name", "")),
        clan=str(data.get("clan", "")),
        team=str(data.get("team", "")),
        activity=str(data.get("activity", "")),
        observer_slot=to_int(data.get("observer_slot"), -1),
        state=_parse_player_state(data.get("state")),
        match_stats=_parse_match_stats(data.get("match_stats")),
        weapons=_parse_weapons(data.get("weapons")),
        position=_parse_vector(data.get("position")),
        forward=_parse_vector(data.get("forward")),
    )


def _parse_allplayers(raw: Any) -> tuple[GsiPlayer, ...]:
    data = _as_mapping(raw)
    players: list[GsiPlayer] = []
    for steamid, entry in data.items():
        player = _parse_player(entry, steamid_hint=str(steamid))
        if player is not None:
            players.append(player)
    return tuple(
        sorted(players, key=lambda p: (p.team, -(p.match_stats.kills if p.match_stats else 0)))
    )


def _parse_bomb(raw: Any) -> BombState | None:
    data = _as_mapping(raw)
    if not data:
        return None
    return BombState(
        state=str(data.get("state", "")),
        countdown=to_float(data.get("countdown")),
        player_steamid=str(data.get("player", "")),
        position=_parse_vector(data.get("position")),
    )


def _parse_phase_countdown(raw: Any) -> PhaseCountdown | None:
    data = _as_mapping(raw)
    if not data:
        return None
    return PhaseCountdown(
        phase=str(data.get("phase", "")),
        ends_in=to_float(data.get("phase_ends_in")),
    )


def parse_payload(payload: Mapping[str, Any]) -> GameState:
    """Convertit un POST GSI complet en ``GameState`` immuable."""
    return GameState(
        received_at=now_ts(),
        provider=_parse_provider(payload.get("provider")),
        map_state=_parse_map(payload.get("map")),
        round_state=_parse_round(payload.get("round")),
        player=_parse_player(payload.get("player")),
        allplayers=_parse_allplayers(payload.get("allplayers")),
        bomb=_parse_bomb(payload.get("bomb")),
        phase_countdown=_parse_phase_countdown(payload.get("phase_countdowns")),
        grenades=_as_mapping(payload.get("grenades")),
        previously=_as_mapping(payload.get("previously")),
    )


def extract_token(payload: Mapping[str, Any]) -> str:
    return str(_as_mapping(payload.get("auth")).get("token", ""))
