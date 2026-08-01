"""Dépôt d'état temps réel : dernier ``GameState``, flux d'événements, abonnés.

Un seul écrivain (l'endpoint ``/gsi``) et de multiples lecteurs (API REST,
WebSocket, UI). L'accès est protégé par un verrou asyncio.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any, Sequence

from cs2tracker.constants import GSI_EVENT_BUFFER_SIZE, GSI_STALE_AFTER_SECONDS
from cs2tracker.core.utils import now_ts
from cs2tracker.gsi.events import GameEvent, diff_states
from cs2tracker.gsi.models import GameState
from cs2tracker.gsi.tracker import MatchTracker
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    """Vue cohérente de l'état live, sûre à sérialiser."""

    connected: bool
    last_update: float | None
    seconds_since_update: float | None
    state: GameState | None
    payload_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "last_update": self.last_update,
            "seconds_since_update": (
                round(self.seconds_since_update, 1)
                if self.seconds_since_update is not None
                else None
            ),
            "payload_count": self.payload_count,
            "state": self.state.as_dict() if self.state else None,
        }


class LiveStateStore:
    """Source de vérité unique pour l'état temps réel du jeu."""

    def __init__(self, *, buffer_size: int = GSI_EVENT_BUFFER_SIZE) -> None:
        self._lock = asyncio.Lock()
        self._current: GameState | None = None
        self._events: deque[GameEvent] = deque(maxlen=buffer_size)
        self._event_sequence = 0
        self._sequenced: deque[tuple[int, GameEvent]] = deque(maxlen=buffer_size)
        self._tracker = MatchTracker()
        self._payload_count = 0
        self._last_update: float | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    # --- écriture ------------------------------------------------------------
    async def update(self, state: GameState) -> tuple[GameEvent, ...]:
        """Enregistre un nouvel état et diffuse les événements déduits."""
        async with self._lock:
            events = diff_states(self._current, state)
            self._current = state
            self._payload_count += 1
            self._last_update = state.received_at
            for event in events:
                self._event_sequence += 1
                self._events.append(event)
                self._sequenced.append((self._event_sequence, event))
            self._tracker.ingest(state, events)
            subscribers = list(self._subscribers)

        if subscribers:
            message = {
                "type": "state",
                "state": state.as_dict(),
                "events": [e.as_dict() for e in events],
            }
            for queue in subscribers:
                # Un abonné lent ne doit jamais bloquer l'ingestion.
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    logger.debug("Abonne WebSocket sature, message ignore")
        return events

    async def reset(self) -> None:
        async with self._lock:
            self._current = None
            self._events.clear()
            self._sequenced.clear()
            self._tracker.reset()
            self._payload_count = 0
            self._last_update = None

    # --- lecture -------------------------------------------------------------
    async def snapshot(self) -> LiveSnapshot:
        async with self._lock:
            last = self._last_update
            elapsed = (now_ts() - last) if last else None
            return LiveSnapshot(
                connected=bool(last and elapsed is not None and elapsed < GSI_STALE_AFTER_SECONDS),
                last_update=last,
                seconds_since_update=elapsed,
                state=self._current,
                payload_count=self._payload_count,
            )

    async def recent_events(
        self, *, since: int = 0, limit: int = 200
    ) -> tuple[int, list[dict[str, Any]]]:
        """Événements postérieurs au numéro de séquence ``since``."""
        async with self._lock:
            selected = [
                {"seq": seq, **event.as_dict()}
                for seq, event in self._sequenced
                if seq > since
            ]
            return self._event_sequence, selected[-limit:]

    async def tracker_snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "match": self._tracker.summary(),
                "players": {
                    steamid: metrics.as_dict()
                    for steamid, metrics in self._tracker.players.items()
                },
            }

    async def live_metrics(self, steamid: str) -> dict[str, Any] | None:
        async with self._lock:
            metrics = self._tracker.metrics_for(steamid)
            return metrics.as_dict() if metrics else None

    async def raw_metrics(self, steamid: str):
        """Métriques brutes (objet) pour le moteur anti-triche."""
        async with self._lock:
            return self._tracker.metrics_for(steamid)

    async def all_raw_metrics(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._tracker.players)

    async def scoreboard(self) -> list[dict[str, Any]]:
        """Tableau des scores trié, fusionnant état GSI et métriques cumulées."""
        async with self._lock:
            state = self._current
            players = dict(self._tracker.players)

        if state is None:
            return []

        rows: list[dict[str, Any]] = []
        candidates = list(state.allplayers)
        if not candidates and state.player:
            candidates = [state.player]

        for player in candidates:
            metrics = players.get(player.steamid)
            stats = player.match_stats
            rows.append(
                {
                    "steamid": player.steamid,
                    "name": player.name,
                    "team": player.team,
                    "alive": player.state.is_alive if player.state else None,
                    "health": player.state.health if player.state else None,
                    "armor": player.state.armor if player.state else None,
                    "money": player.state.money if player.state else None,
                    "kills": stats.kills if stats else 0,
                    "deaths": stats.deaths if stats else 0,
                    "assists": stats.assists if stats else 0,
                    "mvps": stats.mvps if stats else 0,
                    "score": stats.score if stats else 0,
                    "kd": round(stats.kd, 2) if stats else 0.0,
                    "adr": round(metrics.adr, 1) if metrics else 0.0,
                    "headshot_rate": (
                        round(metrics.live_headshot_rate, 3) if metrics else 0.0
                    ),
                    "active_weapon": (
                        player.active_weapon.clean_name if player.active_weapon else None
                    ),
                    "has_bomb": player.has_bomb,
                }
            )
        return sorted(rows, key=lambda r: (r["team"], -r["kills"]))

    async def observed_steamids(self) -> Sequence[str]:
        async with self._lock:
            return tuple(self._tracker.players.keys())

    # --- abonnements ---------------------------------------------------------
    async def subscribe(self, maxsize: int = 64) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
