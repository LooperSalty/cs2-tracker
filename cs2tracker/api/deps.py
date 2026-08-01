"""Dépendances FastAPI et validation des entrées."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import Depends, Path, Request

from cs2tracker.api.context import AppContext
from cs2tracker.core.errors import InvalidSteamIdError
from cs2tracker.steam.service import SteamService

_STEAMID64_RE = re.compile(r"^\d{17}$")
#: Longueur maximale d'une requête utilisateur (URL de profil, vanity…).
_MAX_QUERY_LENGTH = 256


def get_context(request: Request) -> AppContext:
    context = getattr(request.app.state, "context", None)
    if context is None:  # pragma: no cover - garde-fou de démarrage
        raise RuntimeError("Contexte applicatif non initialise")
    return context


def get_steam(context: Annotated[AppContext, Depends(get_context)]) -> SteamService:
    return context.steam


def validate_steamid(
    steamid: Annotated[str, Path(description="SteamID64 (17 chiffres)")],
) -> str:
    """Valide strictement un SteamID64 avant toute utilisation."""
    if not _STEAMID64_RE.match(steamid):
        raise InvalidSteamIdError(
            f"SteamID64 attendu (17 chiffres), recu: {steamid[:32]!r}"
        )
    return steamid


def validate_query(raw: str) -> str:
    """Nettoie une saisie libre destinée à la résolution d'identité."""
    text = (raw or "").strip()
    if not text:
        raise InvalidSteamIdError("Recherche vide")
    if len(text) > _MAX_QUERY_LENGTH:
        raise InvalidSteamIdError("Recherche trop longue")
    return text


ContextDep = Annotated[AppContext, Depends(get_context)]
SteamDep = Annotated[SteamService, Depends(get_steam)]
SteamIdDep = Annotated[str, Depends(validate_steamid)]
