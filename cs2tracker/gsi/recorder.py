"""Enregistrement persistant des matchs observés via le GSI.

Le recorder écoute les événements produits par le diff engine et matérialise
un match en base : création à la première manche, mise à jour à chaque fin de
manche, clôture sur ``match_end`` ou changement de carte.
"""

from __future__ import annotations

from typing import Any, Mapping

from cs2tracker.core.utils import now_ts
from cs2tracker.gsi.events import EventType, GameEvent
from cs2tracker.gsi.models import GameState
from cs2tracker.gsi.tracker import LivePlayerMetrics
from cs2tracker.logging_setup import get_logger
from cs2tracker.storage.repositories import MatchRepository, PlayerRepository

logger = get_logger(__name__)

#: Un match n'est persisté qu'à partir de ce nombre de manches, pour éviter
#: de polluer la base avec des échauffements et des connexions avortées.
MIN_ROUNDS_TO_PERSIST = 3


class MatchRecorder:
    """Fait le lien entre le flux temps réel et la base locale."""

    def __init__(
        self,
        matches: MatchRepository,
        players: PlayerRepository,
        *,
        enabled: bool = True,
    ) -> None:
        self._matches = matches
        self._players = players
        self._enabled = enabled
        self._current_match_id: int | None = None
        self._current_map = ""
        self._rounds_seen = 0
        self._last_activity = 0.0

    @property
    def current_match_id(self) -> int | None:
        return self._current_match_id

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "match_id": self._current_match_id,
            "map": self._current_map,
            "rounds_recorded": self._rounds_seen,
            "last_activity": self._last_activity,
        }

    def handle(
        self,
        state: GameState,
        events: tuple[GameEvent, ...],
        metrics: Mapping[str, LivePlayerMetrics],
    ) -> None:
        """Point d'entrée unique appelé après chaque payload GSI."""
        if not self._enabled or not events:
            return
        self._last_activity = now_ts()
        try:
            for event in events:
                self._handle_event(event, state, metrics)
        except Exception as exc:  # noqa: BLE001 - l'enregistrement ne doit jamais casser l'ingestion
            logger.error("Enregistrement du match interrompu: %s", exc)

    def _handle_event(
        self,
        event: GameEvent,
        state: GameState,
        metrics: Mapping[str, LivePlayerMetrics],
    ) -> None:
        if event.type in {EventType.MAP_CHANGE, EventType.MATCH_START}:
            self._close_current(state, metrics)
            self._start_new(state)
            return

        if event.type == EventType.ROUND_END:
            self._record_round(event, state, metrics)
            return

        if event.type == EventType.MATCH_END:
            self._close_current(state, metrics)

    def _start_new(self, state: GameState) -> None:
        map_state = state.map_state
        if map_state is None or not map_state.name:
            return
        self._current_map = map_state.name
        self._rounds_seen = 0
        self._current_match_id = None  # créé paresseusement à la 1re manche

    def _ensure_match(self, state: GameState) -> int | None:
        if self._current_match_id is not None:
            return self._current_match_id
        map_state = state.map_state
        if map_state is None or not map_state.name:
            return None
        self._current_match_id = self._matches.create(
            map_state.name, map_state.mode, {"opened_by": "gsi"}
        )
        self._current_map = map_state.name
        logger.info("Nouveau match enregistre (#%s, %s)", self._current_match_id, map_state.name)
        return self._current_match_id

    def _record_round(
        self,
        event: GameEvent,
        state: GameState,
        metrics: Mapping[str, LivePlayerMetrics],
    ) -> None:
        match_id = self._ensure_match(state)
        if match_id is None:
            return
        self._rounds_seen += 1
        map_state = state.map_state
        self._matches.save_round(
            match_id,
            event.round_number,
            event.detail.get("win_team", ""),
            {
                "score_ct": map_state.team_ct.score if map_state and map_state.team_ct else 0,
                "score_t": map_state.team_t.score if map_state and map_state.team_t else 0,
                "bomb": state.bomb.state if state.bomb else "",
            },
        )
        if self._rounds_seen >= MIN_ROUNDS_TO_PERSIST:
            self._persist_players(match_id, metrics)

    def _persist_players(
        self, match_id: int, metrics: Mapping[str, LivePlayerMetrics]
    ) -> None:
        values = list(metrics.values())
        if not values:
            return
        self._matches.save_players(match_id, values)
        for player in values:
            if player.steamid:
                self._players.ensure(player.steamid, player.name)

    def _close_current(
        self, state: GameState, metrics: Mapping[str, LivePlayerMetrics]
    ) -> None:
        if self._current_match_id is None:
            return
        if self._rounds_seen < MIN_ROUNDS_TO_PERSIST:
            logger.debug("Match #%s trop court, non finalise", self._current_match_id)
            self._current_match_id = None
            self._rounds_seen = 0
            return

        map_state = state.map_state
        self._persist_players(self._current_match_id, metrics)
        self._matches.finish(
            self._current_match_id,
            score_ct=map_state.team_ct.score if map_state and map_state.team_ct else 0,
            score_t=map_state.team_t.score if map_state and map_state.team_t else 0,
            rounds_total=self._rounds_seen,
            summary={
                "map": self._current_map,
                "mode": map_state.mode if map_state else "",
                "players": len(metrics),
            },
        )
        logger.info("Match #%s cloture (%d manches)", self._current_match_id, self._rounds_seen)
        self._current_match_id = None
        self._rounds_seen = 0
