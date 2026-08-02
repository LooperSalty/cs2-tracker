"""Routes d'analyse anti-triche."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query

from cs2tracker.anticheat.engine import DISCLAIMER, analyse
from cs2tracker.anticheat.report import to_compact_dict, to_text
from cs2tracker.anticheat.weights import DEFAULT_CONFIG
from cs2tracker.api.deps import ContextDep, SteamDep, SteamIdDep
from cs2tracker.api.schemas import BatchAnalyseRequest, LobbyPasteRequest, ok
from cs2tracker.core.steamid import extract_all
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

    # L'analyse ne peut mesurer une derive que si un releve anterieur existe :
    # on enregistre le releve courant *apres* avoir lu l'historique.
    drift = context.snapshots.drift(steamid)
    result = analyse(profile, live, drift=drift)

    context.players.upsert_from_profile(profile)
    if persist:
        context.snapshots.save(profile)
        context.analyses.save(result)
        _record_verdict(context, profile, result)

    return ok(result.as_dict(include_features=include_features))


def _record_verdict(context: ContextDep, profile, result) -> None:
    """Consigne le verdict pour pouvoir le confronter plus tard aux sanctions.

    L'état des bannissements **au moment de l'analyse** est enregistré : seule
    une sanction postérieure validera le verdict. Un compte déjà banni ne prouve
    rien, puisque le moteur voyait la sanction.
    """
    bans = profile.bans
    context.audit.record(
        result.steamid,
        analysed_at=result.analysed_at,
        score=result.suspicion_score,
        verdict=result.verdict,
        bans_at_verdict=bans.total_bans if bans else 0,
    )


@router.get("/{steamid}/report", summary="Rapport texte lisible")
async def text_report(
    steamid: SteamIdDep, context: ContextDep, steam: SteamDep
) -> dict:
    profile = await steam.get_full_profile(steamid)
    live = await context.live.raw_metrics(steamid)
    result = analyse(profile, live, drift=context.snapshots.drift(steamid))
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


async def _analyse_profiles(
    profiles, context: ContextDep, *, use_live: bool, persist: bool
) -> dict:
    """Analyse un ensemble de profils deja charges et met en forme le lot."""

    async def analyse_one(profile):
        steamid = str(profile.identity.get("steamid64", ""))
        live = await context.live.raw_metrics(steamid) if use_live else None
        drift = context.snapshots.drift(steamid)
        return analyse(profile, live, drift=drift)

    results = await asyncio.gather(*(analyse_one(p) for p in profiles))
    ordered = sorted(results, key=lambda r: r.suspicion_score, reverse=True)

    if persist:
        for profile, result in zip(profiles, results):
            context.players.upsert_from_profile(profile)
            context.snapshots.save(profile)
            context.analyses.save(result)
            _record_verdict(context, profile, result)

        # Les joueurs d'un meme lobby se sont croises : on alimente le graphe
        # qui permettra ensuite de reperer les groupes.
        lobby = [
            (str(p.identity.get("steamid64", "")), "")
            for p in profiles
            if p.identity.get("steamid64")
        ]
        if len(lobby) >= 2:
            context.teammates.record_lobby(lobby)

    return {
        "analysed": len(ordered),
        "results": [r.as_dict(include_features=False) for r in ordered],
        "summary": [to_compact_dict(r) for r in ordered],
        "disclaimer": DISCLAIMER,
    }


@router.post("/batch", summary="Analyser plusieurs joueurs (lobby)")
async def analyse_batch(
    payload: BatchAnalyseRequest, context: ContextDep, steam: SteamDep
) -> dict:
    profiles = await steam.get_lobby_profiles(payload.players)
    result = await _analyse_profiles(
        profiles, context, use_live=payload.use_live_data, persist=payload.persist
    )
    return ok({"requested": len(payload.players), **result})


@router.post("/lobby/paste", summary="Analyser un lobby colle depuis la console CS2")
async def analyse_pasted_lobby(
    payload: LobbyPasteRequest, context: ContextDep, steam: SteamDep
) -> dict:
    """Analyse les joueurs reperes dans un collage de la commande ``status``.

    En partie classique, CS2 ne transmet que ton propre etat par GSI : coller le
    ``status`` de la console est le seul moyen d'obtenir les dix joueurs du
    lobby. Le texte est balaye a la recherche des identifiants, quel que soit
    son formatage exact.
    """
    identities = extract_all(payload.text, limit=12)
    if not identities:
        return ok(
            {
                "found": 0,
                "analysed": 0,
                "results": [],
                "summary": [],
                "message": (
                    "Aucun identifiant Steam trouve. Ouvre la console CS2 (touche ~), "
                    "tape `status`, puis colle toute la sortie ici."
                ),
            }
        )

    steamids = [str(identity.steamid64) for identity in identities]
    if not payload.analyse:
        return ok(
            {
                "found": len(identities),
                "players": [identity.as_dict() for identity in identities],
            }
        )

    profiles = await steam.get_lobby_profiles(steamids)
    result = await _analyse_profiles(profiles, context, use_live=True, persist=True)
    return ok({"found": len(identities), **result})


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
    return ok(await _analyse_profiles(profiles, context, use_live=True, persist=True))


@router.get("/leaderboard/suspicious", summary="Joueurs les plus suspects analyses")
async def leaderboard(
    context: ContextDep, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> dict:
    return ok(context.analyses.most_suspicious(limit=limit))
