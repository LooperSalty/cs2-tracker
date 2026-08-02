"""Routes d'audit : le moteur avait-il raison ?"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query

from cs2tracker.anticheat.calibration import (
    DEFAULT_THRESHOLD,
    LabelledProfile,
    blind_config,
    recommend_threshold,
    sweep_thresholds,
)
from cs2tracker.api.deps import ContextDep, SteamDep, SteamIdDep
from cs2tracker.api.schemas import CalibrationRequest, ok
from cs2tracker.core.errors import Cs2TrackerError
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])

#: Profils reverifies par appel : au-dela, l'attente devient sensible.
MAX_RECHECK_BATCH = 100


@router.get("/calibration", summary="Taux de bannissement observe par palier")
async def calibration(context: ContextDep) -> dict:
    """Courbe de calibration réelle, mesurée sur les verdicts déjà rendus.

    C'est la seule preuve possible que le score veut dire quelque chose : les
    joueurs classés « HIGH » finissent-ils effectivement bannis ?
    """
    return ok(context.audit.summary())


@router.post("/recheck", summary="Reconsulter le statut VAC des profils analyses")
async def recheck(
    context: ContextDep,
    steam: SteamDep,
    limit: Annotated[int, Query(ge=1, le=MAX_RECHECK_BATCH)] = 50,
) -> dict:
    """Interroge Valve sur les profils analysés et note les sanctions nouvelles."""
    pending = context.audit.due_for_recheck(limit=limit)
    if not pending:
        return ok(
            {
                "checked": 0,
                "newly_banned": 0,
                "message": "Aucun verdict a reverifier pour le moment.",
            }
        )

    try:
        bans = await steam.get_bans(pending)
    except Cs2TrackerError as exc:
        return ok(
            {
                "checked": 0,
                "newly_banned": 0,
                "message": f"Steam injoignable : {exc.user_message}",
            }
        )

    newly_banned = 0
    for steamid in pending:
        ban = bans.get(steamid)
        if ban is None:
            continue
        if context.audit.apply_check(steamid, ban.total_bans):
            newly_banned += 1
            logger.info("Verdict confirme : %s a ete banni depuis l'analyse.", steamid)

    return ok(
        {
            "checked": len(pending),
            "newly_banned": newly_banned,
            "summary": context.audit.summary(),
        }
    )


@router.get("/confirmations", summary="Verdicts confirmes par une sanction Valve")
async def confirmations(
    context: ContextDep, limit: Annotated[int, Query(ge=1, le=100)] = 25
) -> dict:
    return ok(context.audit.recent_confirmations(limit=limit))


@router.get("/{steamid}", summary="Historique d'audit d'un joueur")
async def player_audit(steamid: SteamIdDep, context: ContextDep) -> dict:
    return ok(context.audit.history_for(steamid))


@router.post("/calibrate", summary="Mesurer le moteur sur un corpus etiquete")
async def calibrate(
    payload: CalibrationRequest, context: ContextDep, steam: SteamDep
) -> dict:
    """Exécute le moteur sur deux corpus étiquetés et mesure sa justesse.

    Les détecteurs de sanctions sont neutralisés : sans cela, le moteur
    reconnaîtrait les tricheurs en lisant leur bannissement, ce qui produirait
    un score parfait sans rien démontrer.
    """
    async def load(ids: list[str], is_cheater: bool) -> list[LabelledProfile]:
        profiles = await steam.get_lobby_profiles(ids)
        return [LabelledProfile(profile=p, is_cheater=is_cheater) for p in profiles]

    cheaters, legit = await asyncio.gather(
        load(payload.cheaters, True), load(payload.legit, False)
    )
    labelled = cheaters + legit

    if not labelled:
        return ok(
            {
                "evaluated": 0,
                "message": "Aucun profil n'a pu etre charge pour l'evaluation.",
            }
        )

    config = blind_config()
    return ok(
        {
            "evaluated": len(labelled),
            "loaded": {"cheaters": len(cheaters), "legit": len(legit)},
            "recommendation": recommend_threshold(
                labelled,
                max_false_positive_rate=payload.max_false_positive_rate,
                config=config,
            ),
            "sweep": sweep_thresholds(labelled, config=config),
            "current_threshold": DEFAULT_THRESHOLD,
        }
    )
