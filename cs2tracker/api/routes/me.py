"""Routes « moi » : le profil de l'utilisateur, sans ressaisir son SteamID.

L'identité est déterminée une fois puis mémorisée. Trois sources la
renseignent, de la plus fiable à la moins fiable : la partie CS2 en cours, la
session Steam ouverte, puis l'historique de connexion local.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from cs2tracker.anticheat.engine import analyse
from cs2tracker.anticheat.percentiles import rank_player, rank_weapon_accuracy
from cs2tracker.api.deps import ContextDep, SteamDep
from cs2tracker.api.schemas import SetMeRequest, ok
from cs2tracker.constants import CS2_APP_ID
from cs2tracker.core.errors import Cs2TrackerError, PlayerNotFoundError
from cs2tracker.core.steamid import from_steamid64
from cs2tracker.logging_setup import get_logger
from cs2tracker.steam.local_user import (
    account_from_gsi,
    detect_local_account,
    is_ambiguous,
    read_known_accounts,
)
from cs2tracker.steam.parsers import group_raw_stats, summarize_weapon_totals
from cs2tracker.steam.weapons import favourite_weapon_name

logger = get_logger(__name__)

router = APIRouter(prefix="/api/me", tags=["mes-stats"])


async def _resolve_me(context: ContextDep) -> tuple[str, str]:
    """Renvoie ``(steamid, origine)`` pour l'utilisateur courant.

    Ne devine **que** lorsque la réponse est certaine. Si plusieurs comptes
    Steam existent sur la machine, on préfère ne rien renvoyer plutôt que
    d'afficher les statistiques de quelqu'un d'autre : la clé API appartient au
    compte connecté sur le *site* Steam, la détection observe le *client*, et
    rien ne relie les deux.
    """
    stored = context.settings_repo.get_me()
    if stored:
        return stored, "choix enregistre"

    # Une partie en cours identifie le joueur local sans ambiguite : c'est la
    # seule source qui prime sur l'incertitude du multi-compte.
    snapshot = await context.live.snapshot()
    if snapshot.state is not None and snapshot.state.provider is not None:
        from_game = account_from_gsi(snapshot.state.provider.steamid)
        if from_game is not None:
            return from_game.steamid64, from_game.source

    if is_ambiguous():
        return "", "plusieurs comptes"

    detected = detect_local_account()
    if detected is not None:
        return detected.steamid64, detected.source
    return "", ""


async def _enrich_candidates(context: ContextDep) -> list[dict[str, Any]]:
    """Complète chaque compte local avec son avatar et ses heures de CS2.

    Choisir entre dix pseudos locaux est difficile ; choisir entre dix cartes
    portant l'avatar et le temps de jeu CS2 est immédiat. C'est ce qui permet à
    l'utilisateur de désigner du premier coup le compte auquel appartient sa
    clé API.
    """
    accounts = read_known_accounts()
    candidates = [account.as_dict() for account in accounts]
    if not candidates or not context.has_steam:
        return candidates

    steamids = [str(entry["steamid64"]) for entry in candidates]

    # Un seul appel couvre les dix comptes.
    try:
        summaries = await context.steam.get_summaries(steamids)
    except Cs2TrackerError as exc:
        logger.info("Profils des comptes locaux indisponibles : %s", exc)
        return candidates

    async def cs2_hours(steamid: str) -> float | None:
        try:
            games = await context.steam.get_owned_games(steamid)
        except Cs2TrackerError:
            return None
        cs2 = next((g for g in games if g.appid == CS2_APP_ID), None)
        return round(cs2.hours, 1) if cs2 else None

    hours = await asyncio.gather(
        *(cs2_hours(steamid) for steamid in steamids), return_exceptions=True
    )

    for entry, played in zip(candidates, hours):
        summary = summaries.get(str(entry["steamid64"]))
        if summary is not None:
            entry["persona_name"] = summary.persona_name or entry["persona_name"]
            entry["avatar"] = summary.avatar_medium or summary.avatar
            entry["profile_public"] = summary.is_public
        entry["cs2_hours"] = played if isinstance(played, float) else None

    # Volontairement pas de tri par heures de jeu ni de compte « recommande ».
    # Le nombre d'heures CS2 ne dit rien du compte recherche : un joueur peut
    # vouloir consulter un compte secondaire, et la cle API n'appartient pas
    # necessairement au compte le plus joue. Ces informations servent a
    # *reconnaitre* son compte, pas a en designer un a sa place. L'ordre reste
    # chronologique, tel que Steam l'a enregistre.
    return candidates


@router.get("/identity", summary="Qui suis-je ?")
async def identity(context: ContextDep) -> dict:
    steamid, source = await _resolve_me(context)
    candidates = await _enrich_candidates(context)
    return ok(
        {
            "steamid64": steamid or None,
            "source": source or None,
            "confirmed": bool(context.settings_repo.get_me()),
            "identity": from_steamid64(steamid).as_dict() if steamid else None,
            "candidates": candidates,
            "detected_accounts": len(candidates),
            "ambiguous": is_ambiguous(),
        }
    )


@router.put("", summary="Definir mon compte")
async def set_me(payload: SetMeRequest, context: ContextDep) -> dict:
    """Fixe l'identité de l'utilisateur, écrasant la détection automatique."""
    identity_value = from_steamid64(payload.steamid64)
    context.settings_repo.set_me(str(identity_value.steamid64))
    return ok({"steamid64": str(identity_value.steamid64), "confirmed": True})


@router.delete("", summary="Oublier mon compte")
async def clear_me(context: ContextDep) -> dict:
    """Repasse en détection automatique."""
    context.settings_repo.clear_me()
    steamid, source = await _resolve_me(context)
    return ok({"cleared": True, "detected": steamid or None, "source": source or None})


@router.get("", summary="Mon profil complet")
async def me(
    context: ContextDep,
    steam: SteamDep,
    include_raw: Annotated[bool, Query(description="Joindre toutes les stats brutes")] = True,
) -> dict:
    """Profil, classement, évolution et intégralité des statistiques CS2."""
    steamid, source = await _resolve_me(context)
    if not steamid:
        raise PlayerNotFoundError(
            f"Compte indetermine ({source or 'aucune source'}).",
            user_message=(
                "Plusieurs comptes Steam existent sur ce PC. Choisis celui qui "
                "est le tien — c'est celui auquel appartient ta cle API."
                if source == "plusieurs comptes"
                else "Impossible de deviner ton compte Steam. Renseigne ton SteamID64."
            ),
        )

    profile = await steam.get_full_profile(steamid)
    context.players.upsert_from_profile(profile)
    if context.settings.auto_snapshot:
        context.snapshots.save(profile)

    stats = profile.stats
    payload: dict[str, Any] = profile.as_dict()
    payload["source"] = source
    payload["confirmed"] = bool(context.settings_repo.get_me())
    payload["percentiles"] = rank_player(stats)
    payload["drift"] = context.snapshots.drift(steamid)

    if stats is not None:
        payload["stats"]["last_match"]["favourite_weapon"] = favourite_weapon_name(
            stats.last_match_favweapon_id
        )
        payload["weapon_aggregate"] = summarize_weapon_totals(stats.weapons)
        payload["weapon_rankings"] = {
            weapon.key: rank_weapon_accuracy(weapon.key, weapon.accuracy, weapon.category)
            for weapon in stats.weapons
        }
        # L'integralite des compteurs renvoyes par Steam, classes par famille.
        payload["raw_groups"] = group_raw_stats(stats.raw) if include_raw else []
        payload["raw_count"] = len(stats.raw)

    return ok(payload)


@router.get("/anticheat", summary="Analyse de mon propre compte")
async def my_analysis(context: ContextDep, steam: SteamDep) -> dict:
    """Utile pour comprendre ce que le moteur voit sur un profil légitime."""
    steamid, _source = await _resolve_me(context)
    if not steamid:
        raise PlayerNotFoundError("Aucun compte detecte.")

    profile = await steam.get_full_profile(steamid)
    live = await context.live.raw_metrics(steamid)
    drift = context.snapshots.drift(steamid)
    result = analyse(profile, live, drift=drift)
    return ok(result.as_dict(include_features=False))


@router.get("/export.csv", summary="Exporter toutes mes statistiques")
async def export_all(context: ContextDep, steam: SteamDep) -> PlainTextResponse:
    """Intégralité des compteurs Steam, une ligne par statistique."""
    steamid, _source = await _resolve_me(context)
    if not steamid:
        raise PlayerNotFoundError("Aucun compte detecte.")

    stats = await steam.get_cs2_stats(steamid)
    if stats is None:
        raise PlayerNotFoundError("Aucune statistique CS2 disponible.")

    lines = ["famille;statistique;valeur"]
    for group in group_raw_stats(stats.raw):
        for entry in group["stats"]:
            lines.append(f"{group['label']};{entry['name']};{entry['value']}")

    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="mes-stats-cs2-{steamid}.csv"'
        },
    )
