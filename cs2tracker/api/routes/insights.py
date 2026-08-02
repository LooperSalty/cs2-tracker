"""Routes d'analyse approfondie : matchs, entourage, comparaison, FACEIT."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query

from cs2tracker.anticheat.compare import compare
from cs2tracker.anticheat.tiers import TIERS, assign_tier
from cs2tracker.api.deps import ContextDep, SteamDep, SteamIdDep
from cs2tracker.api.schemas import CompareRequest, ok
from cs2tracker.core.errors import PlayerNotFoundError
from cs2tracker.faceit import fetch_snapshot
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["analyse-approfondie"])


# --------------------------------------------------------------- match par match
@router.get("/players/{steamid}/matches", summary="Historique match par match")
async def player_matches(
    steamid: SteamIdDep,
    context: ContextDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    """Distribution des performances, là où les stats à vie ne montrent qu'un point."""
    return ok(
        {
            "matches": context.player_matches.list_for(steamid, limit=limit),
            "distribution": context.player_matches.distribution(steamid, limit=limit),
            "outliers": context.player_matches.outliers(steamid, limit=limit),
        }
    )


# ------------------------------------------------------------------- entourage
@router.get("/players/{steamid}/companions", summary="Joueurs frequemment croises")
async def companions(
    steamid: SteamIdDep,
    context: ContextDep,
    min_matches: Annotated[int, Query(ge=1, le=50)] = 2,
) -> dict:
    return ok(
        {
            "companions": context.teammates.companions(steamid, min_matches=min_matches),
            "group_risk": context.teammates.group_risk(steamid, min_matches=min_matches),
        }
    )


@router.get("/groups", summary="Groupes de comptes suspects jouant ensemble")
async def groups(
    context: ContextDep,
    min_matches: Annotated[int, Query(ge=1, le=50)] = 3,
    min_score: Annotated[float, Query(ge=0, le=100)] = 60.0,
) -> dict:
    """Composantes connexes du graphe restreint aux comptes déjà signalés.

    Croiser un tricheur relève du hasard ; en croiser plusieurs, toujours les
    mêmes, beaucoup moins.
    """
    clusters = context.teammates.clusters(min_matches=min_matches, min_score=min_score)
    return ok(
        {
            "clusters": clusters,
            "count": len(clusters),
            "criteria": {"min_matches": min_matches, "min_score": min_score},
            "note": (
                "Le graphe se construit a partir des lobbies analyses. Analyse "
                "plusieurs parties pour qu'il devienne exploitable."
            ),
        }
    )


# ----------------------------------------------------------------------- FACEIT
@router.get("/players/{steamid}/faceit", summary="Profil et matchs FACEIT")
async def faceit_profile(steamid: SteamIdDep, context: ContextDep) -> dict:
    """Niveau, ELO et statistiques par match — inaccessibles via Steam.

    Le rang Premier de CS2 n'est pas exposé par l'API Steam ; FACEIT est le seul
    classement compétitif réellement consultable.
    """
    if context.faceit is None:
        return ok({"available": False, "reason": "Integration FACEIT indisponible."})

    snapshot = await fetch_snapshot(context.faceit, steamid)
    payload = snapshot.as_dict()

    # Les matchs FACEIT alimentent l'historique par match : c'est la source la
    # plus riche dont on dispose pour un joueur ordinaire.
    if snapshot.matches:
        from cs2tracker.storage.matches_history import MatchRecord
        from cs2tracker.core.utils import ts_to_iso

        context.player_matches.save_many(
            MatchRecord(
                steamid64=steamid,
                played_at=ts_to_iso(match.played_at) or "",
                source="faceit",
                external_id=match.match_id,
                map_name=match.map_name,
                rounds=match.rounds,
                kills=match.kills,
                deaths=match.deaths,
                assists=match.assists,
                headshots=match.headshots,
                damage=int(match.adr * match.rounds),
                mvps=match.mvps,
                won=match.won,
            )
            for match in snapshot.matches
        )
        payload["imported_matches"] = len(snapshot.matches)

    return ok(payload)


# ------------------------------------------------------------------ paliers
@router.get("/players/{steamid}/tier", summary="Palier de niveau estime")
async def player_tier(steamid: SteamIdDep, context: ContextDep, steam: SteamDep) -> dict:
    """Palier auquel le joueur est comparé.

    Comparer un joueur de niveau compétitif à la moyenne générale le signale
    systématiquement. On le compare donc à ses pairs.
    """
    stats = await steam.get_cs2_stats(steamid)
    faceit_level = None
    if context.faceit is not None and context.faceit.configured:
        snapshot = await fetch_snapshot(context.faceit, steamid, match_limit=0)
        if snapshot.profile is not None:
            faceit_level = snapshot.profile.level

    assignment = assign_tier(
        faceit_level=faceit_level,
        hours_played=stats.hours_played if stats else 0.0,
        kills_per_round=stats.kills_per_round if stats else 0.0,
        rounds_played=stats.total_rounds_played if stats else 0,
    )
    return ok({**assignment.as_dict(), "all_tiers": [tier.as_dict() for tier in TIERS]})


# -------------------------------------------------------------------- comparaison
@router.post("/compare", summary="Comparer deux joueurs")
async def compare_players(
    payload: CompareRequest, context: ContextDep, steam: SteamDep
) -> dict:
    """Confronte deux profils métrique par métrique."""
    left, right = await asyncio.gather(
        steam.get_full_profile(payload.left),
        steam.get_full_profile(payload.right),
        return_exceptions=True,
    )

    for side, result in (("gauche", left), ("droite", right)):
        if isinstance(result, BaseException):
            raise PlayerNotFoundError(
                f"Profil {side} illisible: {result}",
                user_message=f"Le joueur {side} n'a pas pu etre charge.",
            )

    context.players.upsert_from_profile(left)
    context.players.upsert_from_profile(right)
    return ok(compare(left, right))
