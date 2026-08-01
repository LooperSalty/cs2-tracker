"""Routes des matchs enregistrés localement."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from cs2tracker.api.deps import ContextDep
from cs2tracker.api.schemas import ok
from cs2tracker.core.errors import PlayerNotFoundError

router = APIRouter(prefix="/api/matches", tags=["matchs"])


@router.get("", summary="Matchs recents")
async def list_matches(
    context: ContextDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> dict:
    return ok(context.matches.list_recent(limit=limit))


@router.get("/current", summary="Match en cours d'enregistrement")
async def current_match(context: ContextDep) -> dict:
    status = context.recorder.status()
    match_id = status.get("match_id")
    detail = context.matches.get(int(match_id)) if match_id else None
    return ok({"recorder": status, "match": detail})


@router.get("/{match_id}", summary="Detail d'un match")
async def match_detail(
    context: ContextDep,
    match_id: Annotated[int, Path(ge=1)],
) -> dict:
    match = context.matches.get(match_id)
    if match is None:
        raise PlayerNotFoundError(f"Match {match_id} introuvable")
    return ok(match)


@router.get("/{match_id}/rounds", summary="Manches d'un match")
async def match_rounds(
    context: ContextDep,
    match_id: Annotated[int, Path(ge=1)],
) -> dict:
    return ok(context.matches.rounds_of(match_id))


@router.get("/{match_id}/players", summary="Joueurs d'un match")
async def match_players(
    context: ContextDep,
    match_id: Annotated[int, Path(ge=1)],
) -> dict:
    return ok(context.matches.players_of(match_id))
