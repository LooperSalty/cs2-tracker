"""Routes d'analyse anti-triche."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query

from cs2tracker.anticheat.engine import DISCLAIMER, analyse
from cs2tracker.anticheat.report import to_compact_dict, to_text
from cs2tracker.anticheat.weights import DEFAULT_CONFIG
from cs2tracker.api.deps import ContextDep, SteamDep, SteamIdDep
from cs2tracker.api.schemas import BatchAnalyseRequest, ok
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/anticheat", tags=["anti-triche"])


@router.get("/disclaimer", summary="Portee et limites de l'analyse")
async def disclaimer() -> dict:
    return ok(
        {
            "disclaimer": DISCLAIMER,
            "methodology": {
                "sources": [
                    "Steam Web API (donnees publiques)",
                    "Game State Integration officiel de CS2",
                ],
                "never_used": [
                    "lecture de la memoire du jeu",
                    "injection de code",
                    "modification des fichiers du jeu (hors .cfg GSI officiel)",
                    "interception du trafic reseau du jeu",
                ],
                "known_false_positives": [
                    "comptes secondaires (smurfs)",
                    "joueurs de niveau competitif ou professionnel",
                    "styles de jeu atypiques (AWP exclusif, entry fragger)",
                    "echantillons statistiques trop faibles",
                ],
            },
            "verdict_bands": {
                "CLEAN": "0-29",
                "LOW": "30-49",
                "MODERATE": "50-69",
                "HIGH": "70-84",
                "CRITICAL": "85-100",
                "INDETERMINE": "confiance insuffisante",
            },
        }
    )


@router.get("/weights", summary="Ponderation courante des detecteurs")
async def weights() -> dict:
    return ok(
        {
            "weights": dict(DEFAULT_CONFIG.weights),
            "engine": {
                "min_confidence": DEFAULT_CONFIG.min_confidence,
                "aggregation_exponent": DEFAULT_CONFIG.aggregation_exponent,
                "critical_signal_floor": DEFAULT_CONFIG.critical_signal_floor,
                "confirmed_ban_floor": DEFAULT_CONFIG.confirmed_ban_floor,
                "corroboration_threshold": DEFAULT_CONFIG.corroboration_threshold,
                "min_global_confidence": DEFAULT_CONFIG.min_global_confidence,
            },
        }
    )


@router.get("/{steamid}", summary="Analyser un joueur")
async def analyse_player(
    steamid: SteamIdDep,
    context: ContextDep,
    steam: SteamDep,
    use_live: Annotated[bool, Query(description="Croiser avec le temps reel")] = True,
    persist: Annotated[bool, Query(description="Enregistrer le rapport")] = True,
    include_features: Annotated[bool, Query()] = True,
) -> dict:
    profile = await steam.get_full_profile(steamid)
    live = await context.live.raw_metrics(steamid) if use_live else None
    result = analyse(profile, live)

    context.players.upsert_from_profile(profile)
    if persist:
        context.analyses.save(result)

    return ok(result.as_dict(include_features=include_features))


@router.get("/{steamid}/report", summary="Rapport texte lisible")
async def text_report(
    steamid: SteamIdDep, context: ContextDep, steam: SteamDep
) -> dict:
    profile = await steam.get_full_profile(steamid)
    live = await context.live.raw_metrics(steamid)
    result = analyse(profile, live)
    return ok({"text": to_text(result), "verdict": result.verdict})


@router.get("/{steamid}/history", summary="Historique des analyses")
async def analysis_history(
    steamid: SteamIdDep,
    context: ContextDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    return ok(
        {
            "history": context.analyses.history(steamid, limit=limit),
            "latest": context.analyses.latest(steamid),
        }
    )


@router.post("/batch", summary="Analyser plusieurs joueurs (lobby)")
async def analyse_batch(
    payload: BatchAnalyseRequest, context: ContextDep, steam: SteamDep
) -> dict:
    profiles = await steam.get_lobby_profiles(payload.players)

    async def analyse_one(profile):
        steamid = str(profile.identity.get("steamid64", ""))
        live = (
            await context.live.raw_metrics(steamid) if payload.use_live_data else None
        )
        return analyse(profile, live)

    results = await asyncio.gather(*(analyse_one(p) for p in profiles))
    ordered = sorted(results, key=lambda r: r.suspicion_score, reverse=True)

    if payload.persist:
        for profile, result in zip(profiles, results):
            context.players.upsert_from_profile(profile)
            context.analyses.save(result)

    return ok(
        {
            "requested": len(payload.players),
            "analysed": len(ordered),
            "results": [r.as_dict(include_features=False) for r in ordered],
            "summary": [to_compact_dict(r) for r in ordered],
            "disclaimer": DISCLAIMER,
        }
    )


@router.post("/lobby/live", summary="Analyser tous les joueurs vus en direct")
async def analyse_live_lobby(context: ContextDep, steam: SteamDep) -> dict:
    steamids = [sid for sid in await context.live.observed_steamids() if sid.isdigit()]
    if not steamids:
        return ok(
            {
                "analysed": 0,
                "results": [],
                "message": (
                    "Aucun joueur observe. Les donnees de tous les joueurs ne sont "
                    "transmises qu'en mode spectateur ou sur une retransmission GOTV."
                ),
            }
        )

    profiles = await steam.get_lobby_profiles(steamids[:10])
    results = []
    for profile in profiles:
        steamid = str(profile.identity.get("steamid64", ""))
        live = await context.live.raw_metrics(steamid)
        result = analyse(profile, live)
        context.players.upsert_from_profile(profile)
        context.analyses.save(result)
        results.append(result)

    ordered = sorted(results, key=lambda r: r.suspicion_score, reverse=True)
    return ok(
        {
            "analysed": len(ordered),
            "results": [r.as_dict(include_features=False) for r in ordered],
            "summary": [to_compact_dict(r) for r in ordered],
            "disclaimer": DISCLAIMER,
        }
    )


@router.get("/leaderboard/suspicious", summary="Joueurs les plus suspects analyses")
async def leaderboard(
    context: ContextDep, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> dict:
    return ok(context.analyses.most_suspicious(limit=limit))
