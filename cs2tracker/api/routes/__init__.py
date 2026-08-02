"""Regroupement des routeurs de l'API."""

from cs2tracker.api.routes import (
    anticheat,
    audit,
    demos,
    insights,
    live,
    matches,
    me,
    players,
    system,
)

ALL_ROUTERS = (
    system.router,
    me.router,
    players.router,
    anticheat.router,
    audit.router,
    insights.router,
    demos.router,
    matches.router,
    live.router,
)

__all__ = [
    "ALL_ROUTERS",
    "anticheat",
    "audit",
    "demos",
    "insights",
    "live",
    "matches",
    "me",
    "players",
    "system",
]
