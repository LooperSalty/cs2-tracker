"""Regroupement des routeurs de l'API."""

from cs2tracker.api.routes import anticheat, live, matches, me, players, system

ALL_ROUTERS = (
    system.router,
    me.router,
    players.router,
    anticheat.router,
    matches.router,
    live.router,
)

__all__ = ["ALL_ROUTERS", "anticheat", "live", "matches", "me", "players", "system"]
