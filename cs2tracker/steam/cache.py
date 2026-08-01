"""Cache mémoire TTL, thread-safe, à éviction LRU.

Objectif : ne pas marteler l'API Steam lorsque l'UI rafraîchit une vue ou
lorsqu'on analyse dix joueurs partageant des ressources communes.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from cs2tracker.constants import CACHE_MAX_ENTRIES
from cs2tracker.core.utils import now_ts


@dataclass(frozen=True, slots=True)
class CacheEntry:
    value: Any
    expires_at: float

    def is_fresh(self, at: float) -> bool:
        return at < self.expires_at


class TtlCache:
    """Cache clé → valeur avec durée de vie et taille bornée."""

    def __init__(self, max_entries: int = CACHE_MAX_ENTRIES) -> None:
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_entries = max_entries
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            if not entry.is_fresh(now_ts()):
                del self._entries[key]
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return entry.value

    async def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        async with self._lock:
            self._entries[key] = CacheEntry(value=value, expires_at=now_ts() + ttl_seconds)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    async def invalidate(self, prefix: str = "") -> int:
        async with self._lock:
            if not prefix:
                removed = len(self._entries)
                self._entries.clear()
                return removed
            doomed = [key for key in self._entries if key.startswith(prefix)]
            for key in doomed:
                del self._entries[key]
            return len(doomed)

    def stats(self) -> dict[str, int | float]:
        total = self._hits + self._misses
        return {
            "entries": len(self._entries),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total else 0.0,
        }
