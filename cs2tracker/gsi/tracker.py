"""Agrégation temps réel par joueur et par manche.

Ce module produit les *features comportementales* consommées ensuite par le
moteur anti-triche : cadence des kills, régularité des dégâts, taux de HS en
direct, usage d'utilitaires, etc.

Toutes les structures sont immuables : chaque mise à jour renvoie une copie via
``dataclasses.replace``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from cs2tracker.core.utils import (
    coefficient_of_variation,
    mean,
    safe_div,
    stdev,
)
from cs2tracker.gsi.events import EventType, GameEvent
from cs2tracker.gsi.models import GameState, GsiPlayer

#: Un intervalle entre deux kills sous ce seuil est un « enchaînement rapide ».
FAST_CHAIN_SECONDS = 1.2
#: Nombre minimal de manches avant que les métriques live aient du sens.
MIN_ROUNDS_FOR_LIVE_ANALYSIS = 5


@dataclass(frozen=True, slots=True)
class RoundRecord:
    """Bilan figé d'une manche pour un joueur."""

    round_number: int
    kills: int
    headshots: int
    damage: int
    died: bool
    money_start: int
    equip_value: int
    utility_bought: int
    kill_offsets: tuple[float, ...]

    @property
    def headshot_rate(self) -> float:
        return safe_div(self.headshots, self.kills)

    @property
    def kill_intervals(self) -> tuple[float, ...]:
        if len(self.kill_offsets) < 2:
            return ()
        return tuple(
            self.kill_offsets[i + 1] - self.kill_offsets[i]
            for i in range(len(self.kill_offsets) - 1)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "round": self.round_number,
            "kills": self.kills,
            "headshots": self.headshots,
            "damage": self.damage,
            "died": self.died,
            "headshot_rate": round(self.headshot_rate, 3),
            "equipment_value": self.equip_value,
            "utility_bought": self.utility_bought,
            "kill_offsets": [round(o, 2) for o in self.kill_offsets],
        }


@dataclass(frozen=True, slots=True)
class LivePlayerMetrics:
    """Cumul des observations temps réel sur un joueur."""

    steamid: str
    name: str
    team: str
    rounds: tuple[RoundRecord, ...] = field(default_factory=tuple)
    current_round: int = 0
    current_kills: int = 0
    current_headshots: int = 0
    current_damage: int = 0
    current_kill_offsets: tuple[float, ...] = field(default_factory=tuple)
    round_started_at: float = 0.0
    total_kills: int = 0
    total_deaths: int = 0
    total_assists: int = 0
    total_mvps: int = 0
    total_utility_bought: int = 0
    first_seen_at: float = 0.0
    last_seen_at: float = 0.0

    # --- agrégats dérivés ----------------------------------------------------
    @property
    def rounds_observed(self) -> int:
        return len(self.rounds)

    @property
    def damage_series(self) -> tuple[float, ...]:
        return tuple(float(r.damage) for r in self.rounds)

    @property
    def kills_series(self) -> tuple[float, ...]:
        return tuple(float(r.kills) for r in self.rounds)

    @property
    def adr(self) -> float:
        return mean(self.damage_series)

    @property
    def adr_variability(self) -> float:
        """Coefficient de variation des dégâts par manche.

        Une valeur anormalement basse traduit une régularité peu humaine ;
        une valeur normale se situe autour de 0.6-1.0.
        """
        return coefficient_of_variation(self.damage_series)

    @property
    def kills_per_round(self) -> float:
        return mean(self.kills_series)

    @property
    def live_headshot_rate(self) -> float:
        total_kills = sum(r.kills for r in self.rounds) + self.current_kills
        total_hs = sum(r.headshots for r in self.rounds) + self.current_headshots
        return safe_div(total_hs, total_kills)

    @property
    def multi_kill_rounds(self) -> int:
        return sum(1 for r in self.rounds if r.kills >= 3)

    @property
    def multi_kill_rate(self) -> float:
        return safe_div(self.multi_kill_rounds, self.rounds_observed)

    @property
    def all_kill_intervals(self) -> tuple[float, ...]:
        intervals: list[float] = []
        for record in self.rounds:
            intervals.extend(record.kill_intervals)
        return tuple(intervals)

    @property
    def kill_interval_stdev(self) -> float:
        """Dispersion des délais entre kills consécutifs.

        Un tueur humain alterne duels rapides et lents ; une dispersion
        quasi nulle sur un échantillon fourni est atypique.
        """
        return stdev(self.all_kill_intervals)

    @property
    def fast_chain_rate(self) -> float:
        intervals = self.all_kill_intervals
        if not intervals:
            return 0.0
        fast = sum(1 for i in intervals if i <= FAST_CHAIN_SECONDS)
        return safe_div(fast, len(intervals))

    @property
    def survival_rate(self) -> float:
        if not self.rounds:
            return 0.0
        return safe_div(sum(1 for r in self.rounds if not r.died), self.rounds_observed)

    @property
    def utility_per_round(self) -> float:
        return safe_div(self.total_utility_bought, max(1, self.rounds_observed))

    @property
    def has_enough_rounds(self) -> bool:
        return self.rounds_observed >= MIN_ROUNDS_FOR_LIVE_ANALYSIS

    def as_dict(self) -> dict[str, Any]:
        return {
            "steamid": self.steamid,
            "name": self.name,
            "team": self.team,
            "rounds_observed": self.rounds_observed,
            "totals": {
                "kills": self.total_kills,
                "deaths": self.total_deaths,
                "assists": self.total_assists,
                "mvps": self.total_mvps,
                "kd": round(safe_div(self.total_kills, self.total_deaths), 3),
            },
            "live": {
                "adr": round(self.adr, 1),
                "adr_variability": round(self.adr_variability, 3),
                "kills_per_round": round(self.kills_per_round, 2),
                "headshot_rate": round(self.live_headshot_rate, 3),
                "multi_kill_rate": round(self.multi_kill_rate, 3),
                "multi_kill_rounds": self.multi_kill_rounds,
                "kill_interval_stdev": round(self.kill_interval_stdev, 3),
                "fast_chain_rate": round(self.fast_chain_rate, 3),
                "survival_rate": round(self.survival_rate, 3),
                "utility_per_round": round(self.utility_per_round, 2),
            },
            "current_round": {
                "round": self.current_round,
                "kills": self.current_kills,
                "headshots": self.current_headshots,
                "damage": self.current_damage,
            },
            "rounds": [r.as_dict() for r in self.rounds[-30:]],
            "analysable": self.has_enough_rounds,
        }


def _record_from_current(
    metrics: LivePlayerMetrics, player: GsiPlayer | None, died: bool
) -> RoundRecord:
    state = player.state if player else None
    return RoundRecord(
        round_number=metrics.current_round,
        kills=metrics.current_kills,
        headshots=metrics.current_headshots,
        damage=metrics.current_damage,
        died=died,
        money_start=state.money if state else 0,
        equip_value=state.equip_value if state else 0,
        utility_bought=player.utility_count if player else 0,
        kill_offsets=metrics.current_kill_offsets,
    )


class MatchTracker:
    """Accumule les métriques de tous les joueurs observés sur un match.

    L'objet est un conteneur mutable *de références* : les métriques elles-mêmes
    sont remplacées par des copies, jamais modifiées sur place.
    """

    def __init__(self) -> None:
        self._players: dict[str, LivePlayerMetrics] = {}
        self._round_number = 0
        self._round_started_at = 0.0
        self._map_name = ""
        self._mode = ""
        self._started_at = 0.0

    # --- lecture -------------------------------------------------------------
    @property
    def players(self) -> Mapping[str, LivePlayerMetrics]:
        return dict(self._players)

    @property
    def round_number(self) -> int:
        return self._round_number

    @property
    def map_name(self) -> str:
        return self._map_name

    def metrics_for(self, steamid: str) -> LivePlayerMetrics | None:
        return self._players.get(steamid)

    def summary(self) -> dict[str, Any]:
        return {
            "map": self._map_name,
            "mode": self._mode,
            "round": self._round_number,
            "started_at": self._started_at,
            "players_tracked": len(self._players),
        }

    def reset(self) -> None:
        self._players = {}
        self._round_number = 0
        self._round_started_at = 0.0
        self._map_name = ""
        self._mode = ""
        self._started_at = 0.0

    # --- écriture ------------------------------------------------------------
    def ingest(self, state: GameState, events: tuple[GameEvent, ...]) -> None:
        """Met à jour les métriques depuis un nouvel état et ses événements."""
        if state.map_state is not None:
            if state.map_state.name and state.map_state.name != self._map_name:
                self.reset()
                self._map_name = state.map_state.name
                self._mode = state.map_state.mode
                self._started_at = state.received_at
            self._round_number = state.map_state.round_number

        self._ensure_players(state)
        self._apply_events(state, events)
        self._sync_from_state(state)

    def _ensure_players(self, state: GameState) -> None:
        candidates: list[GsiPlayer] = list(state.allplayers)
        if state.player and state.player.steamid:
            candidates.append(state.player)
        for player in candidates:
            if not player.steamid:
                continue
            existing = self._players.get(player.steamid)
            if existing is None:
                self._players[player.steamid] = LivePlayerMetrics(
                    steamid=player.steamid,
                    name=player.name,
                    team=player.team,
                    current_round=self._round_number,
                    round_started_at=state.received_at,
                    first_seen_at=state.received_at,
                    last_seen_at=state.received_at,
                )
            elif existing.name != player.name or existing.team != player.team:
                self._players[player.steamid] = replace(
                    existing, name=player.name or existing.name, team=player.team
                )

    def _apply_events(self, state: GameState, events: tuple[GameEvent, ...]) -> None:
        for event in events:
            if event.type in {EventType.ROUND_START, EventType.ROUND_FREEZE}:
                self._close_round(state, event)
                continue
            if not event.steamid:
                continue
            metrics = self._players.get(event.steamid)
            if metrics is None:
                continue
            self._players[event.steamid] = _apply_player_event(metrics, event)

    def _close_round(self, state: GameState, event: GameEvent) -> None:
        """Fige la manche en cours pour chaque joueur et ouvre la suivante."""
        for steamid, metrics in list(self._players.items()):
            player = state.player_by_steamid(steamid)
            has_activity = (
                metrics.current_kills or metrics.current_damage or metrics.rounds
            )
            if not has_activity and metrics.current_round == 0:
                self._players[steamid] = replace(
                    metrics,
                    current_round=event.round_number,
                    round_started_at=event.at,
                )
                continue
            died = bool(player and player.state and not player.state.is_alive)
            record = _record_from_current(metrics, player, died)
            self._players[steamid] = replace(
                metrics,
                rounds=metrics.rounds + (record,),
                current_round=event.round_number,
                current_kills=0,
                current_headshots=0,
                current_damage=0,
                current_kill_offsets=(),
                round_started_at=event.at,
            )
        self._round_started_at = event.at

    def _sync_from_state(self, state: GameState) -> None:
        """Recale les compteurs de manche sur la vérité du GSI."""
        for steamid, metrics in list(self._players.items()):
            player = state.player_by_steamid(steamid)
            if player is None:
                continue
            updates: dict[str, Any] = {"last_seen_at": state.received_at}
            if player.state is not None:
                updates["current_kills"] = max(
                    metrics.current_kills, player.state.round_kills
                )
                updates["current_headshots"] = max(
                    metrics.current_headshots, player.state.round_killhs
                )
                updates["current_damage"] = max(
                    metrics.current_damage, player.state.round_totaldmg
                )
            if player.match_stats is not None:
                updates["total_kills"] = player.match_stats.kills
                updates["total_deaths"] = player.match_stats.deaths
                updates["total_assists"] = player.match_stats.assists
                updates["total_mvps"] = player.match_stats.mvps
            self._players[steamid] = replace(metrics, **updates)


def _apply_player_event(
    metrics: LivePlayerMetrics, event: GameEvent
) -> LivePlayerMetrics:
    if event.type in {EventType.KILL, EventType.HEADSHOT_KILL}:
        count = int(event.detail.get("count", 1))
        headshots = int(event.detail.get("headshots", 0))
        offset = max(0.0, event.at - metrics.round_started_at)
        new_offsets = metrics.current_kill_offsets + tuple(offset for _ in range(count))
        return replace(
            metrics,
            current_kills=metrics.current_kills + count,
            current_headshots=metrics.current_headshots + headshots,
            current_kill_offsets=new_offsets,
        )
    if event.type == EventType.DAMAGE_TAKEN:
        return metrics
    if event.type == EventType.MVP:
        return replace(metrics, total_mvps=metrics.total_mvps + 1)
    return metrics
