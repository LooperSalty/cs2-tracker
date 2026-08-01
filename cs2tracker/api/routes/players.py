"""Routes joueurs : recherche, profil, statistiques, historique."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from fastapi.responses import PlainTextResponse

from cs2tracker.anticheat.percentiles import rank_player, rank_weapon_accuracy
from cs2tracker.api.deps import ContextDep, SteamDep, SteamIdDep, validate_query
from cs2tracker.api.schemas import (
    FavouriteRequest,
    LobbyPasteRequest,
    NotesRequest,
    SearchRequest,
    ok,
)
from cs2tracker.core.errors import PlayerNotFoundError
from cs2tracker.core.steamid import extract_all
from cs2tracker.steam.parsers import summarize_weapon_totals
from cs2tracker.steam.service import describe_identity
from cs2tracker.steam.weapons import favourite_weapon_name

router = APIRouter(prefix="/api/players", tags=["joueurs"])


def _profile_payload(profile, context: ContextDep, steamid: str) -> dict:
    """Profil enrichi du classement dans la population et de l'evolution.

    Les trois informations arrivent en une seule requete : l'interface affiche
    ainsi la page complete sans cascade d'appels.
    """
    payload = profile.as_dict()
    payload["percentiles"] = rank_player(profile.stats)
    payload["drift"] = context.snapshots.drift(steamid) if steamid else None
    return payload


@router.get("/resolve/{query}", summary="Resoudre une identite Steam")
async def resolve(query: str, steam: SteamDep) -> dict:
    identity = await steam.resolve(validate_query(query))
    return ok(identity.as_dict())


@router.get("/parse/{query}", summary="Analyser une saisie sans appel reseau")
async def parse_only(query: str) -> dict:
    return ok(describe_identity(validate_query(query)))


@router.post("/search", summary="Rechercher et charger un profil complet")
async def search(
    payload: SearchRequest, context: ContextDep, steam: SteamDep
) -> dict:
    profile = await steam.get_full_profile(payload.query)
    steamid = context.players.upsert_from_profile(profile)
    if context.settings.auto_snapshot:
        context.snapshots.save(profile)
    return ok(_profile_payload(profile, context, steamid))


@router.get("/tracked", summary="Joueurs deja suivis localement")
async def tracked(
    context: ContextDep,
    favourites_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    return ok(context.players.list_all(favourites_only=favourites_only, limit=limit))


@router.post("/extract", summary="Extraire les SteamID d'un texte colle")
async def extract_from_text(payload: LobbyPasteRequest) -> dict:
    """Repere les identifiants Steam dans un collage libre.

    Cible principale : la sortie de la commande ``status`` de la console CS2.
    En partie classique, le jeu ne transmet que ton propre etat par GSI ; coller
    le ``status`` est le seul moyen d'obtenir les dix joueurs du lobby.
    """
    identities = extract_all(payload.text)
    return ok(
        {
            "found": len(identities),
            "players": [identity.as_dict() for identity in identities],
        }
    )


@router.get("/{steamid}/percentiles", summary="Position dans la population")
async def percentiles(steamid: SteamIdDep, steam: SteamDep) -> dict:
    """Classe chaque statistique du joueur par rapport a la population."""
    stats = await steam.get_cs2_stats(steamid)
    return ok(rank_player(stats))


@router.get("/{steamid}/export.csv", summary="Exporter l'historique en CSV")
async def export_csv(steamid: SteamIdDep, context: ContextDep) -> PlainTextResponse:
    """Historique des releves au format CSV, ouvrable dans un tableur."""
    snapshots = context.snapshots.history(steamid, limit=1_000)
    columns = [
        "captured_at", "kills", "deaths", "rounds_played", "matches_played",
        "matches_won", "time_played", "headshot_kills", "shots_fired",
        "shots_hit", "damage_done", "mvps", "kd_ratio", "headshot_rate", "accuracy",
    ]
    lines = [";".join(columns)]
    for snapshot in reversed(snapshots):
        lines.append(";".join(str(snapshot.get(column, "")) for column in columns))

    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="cs2tracker-{steamid}.csv"'
        },
    )


@router.get("/{steamid}", summary="Profil complet d'un joueur")
async def profile(
    steamid: SteamIdDep,
    context: ContextDep,
    steam: SteamDep,
    snapshot: Annotated[bool, Query(description="Enregistrer un instantane")] = True,
) -> dict:
    result = await steam.get_full_profile(steamid)
    context.players.upsert_from_profile(result)
    if snapshot and context.settings.auto_snapshot:
        context.snapshots.save(result)
    return ok(_profile_payload(result, context, steamid))


@router.get("/{steamid}/summary", summary="Resume de profil Steam")
async def summary(steamid: SteamIdDep, steam: SteamDep) -> dict:
    return ok((await steam.get_summary(steamid)).as_dict())


@router.get("/{steamid}/bans", summary="Sanctions Valve enregistrees")
async def bans(steamid: SteamIdDep, steam: SteamDep) -> dict:
    ban = await steam.get_ban(steamid)
    if ban is None:
        raise PlayerNotFoundError(f"Aucune donnee de sanction pour {steamid}")
    return ok(ban.as_dict())


@router.get("/{steamid}/stats", summary="Statistiques CS2 a vie")
async def stats(steamid: SteamIdDep, steam: SteamDep) -> dict:
    result = await steam.get_cs2_stats(steamid)
    if result is None:
        raise PlayerNotFoundError(
            f"Aucune statistique CS2 disponible pour {steamid}",
        )
    payload = result.as_dict()
    payload["last_match"]["favourite_weapon"] = favourite_weapon_name(
        result.last_match_favweapon_id
    )
    return ok(payload)


@router.get("/{steamid}/weapons", summary="Detail par arme")
async def weapons(steamid: SteamIdDep, steam: SteamDep) -> dict:
    result = await steam.get_cs2_stats(steamid)
    if result is None:
        raise PlayerNotFoundError(f"Aucune statistique d'arme pour {steamid}")
    return ok(
        {
            "weapons": [
                {
                    **weapon.as_dict(),
                    # Chaque arme est comparee a sa propre categorie : une
                    # precision d'AWP n'a rien a voir avec celle d'une SMG.
                    "ranking": rank_weapon_accuracy(
                        weapon.key, weapon.accuracy, weapon.category
                    ),
                }
                for weapon in result.weapons
            ],
            "aggregate": summarize_weapon_totals(result.weapons),
        }
    )


@router.get("/{steamid}/maps", summary="Detail par carte")
async def maps(steamid: SteamIdDep, steam: SteamDep) -> dict:
    result = await steam.get_cs2_stats(steamid)
    if result is None:
        raise PlayerNotFoundError(f"Aucune statistique de carte pour {steamid}")
    return ok([m.as_dict() for m in result.maps])


@router.get("/{steamid}/games", summary="Jeux possedes et temps de jeu")
async def games(
    steamid: SteamIdDep,
    steam: SteamDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> dict:
    owned = await steam.get_owned_games(steamid)
    ordered = sorted(owned, key=lambda g: g.playtime_forever_minutes, reverse=True)
    return ok(
        {
            "total_games": len(owned),
            "top_games": [g.as_dict() for g in ordered[:limit]],
        }
    )


@router.get("/{steamid}/friends", summary="Liste d'amis")
async def friends(
    steamid: SteamIdDep,
    steam: SteamDep,
    with_profiles: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    raw_friends = await steam.get_friends(steamid)
    if not with_profiles:
        return ok({"count": len(raw_friends), "friends": list(raw_friends)[:limit]})

    ids = [str(f.get("steamid")) for f in raw_friends[:limit] if f.get("steamid")]
    summaries = await steam.get_summaries(ids)
    return ok(
        {
            "count": len(raw_friends),
            "friends": [
                {
                    "steamid": steam_id,
                    "friend_since": next(
                        (f.get("friend_since") for f in raw_friends if str(f.get("steamid")) == steam_id),
                        None,
                    ),
                    "profile": summaries[steam_id].as_dict()
                    if steam_id in summaries
                    else None,
                }
                for steam_id in ids
            ],
        }
    )


@router.get("/{steamid}/achievements", summary="Succes CS2")
async def achievements(steamid: SteamIdDep, steam: SteamDep) -> dict:
    unlocked, total = await steam.get_achievements(steamid)
    return ok(
        {
            "unlocked": unlocked,
            "total": total,
            "rate": round(unlocked / total, 3) if total else 0.0,
        }
    )


@router.get("/{steamid}/recent", summary="Jeux joues recemment")
async def recent(steamid: SteamIdDep, steam: SteamDep) -> dict:
    return ok(list(await steam.get_recently_played(steamid)))


@router.get("/{steamid}/history", summary="Historique local des statistiques")
async def history(
    steamid: SteamIdDep,
    context: ContextDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict:
    return ok(
        {
            "snapshots": context.snapshots.history(steamid, limit=limit),
            "progression": context.snapshots.progression(steamid),
            "drift": context.snapshots.drift(steamid),
            "matches": context.matches.player_history(steamid, limit=50),
        }
    )


@router.post("/{steamid}/snapshot", summary="Forcer un instantane de statistiques")
async def snapshot(steamid: SteamIdDep, context: ContextDep, steam: SteamDep) -> dict:
    result = await steam.get_full_profile(steamid)
    context.players.upsert_from_profile(result)
    snapshot_id = context.snapshots.save(result)
    return ok({"snapshot_id": snapshot_id, "saved": snapshot_id > 0})


@router.put("/{steamid}/favourite", summary="Marquer comme favori")
async def favourite(
    steamid: SteamIdDep, context: ContextDep, payload: FavouriteRequest
) -> dict:
    context.players.ensure(steamid)
    context.players.set_favourite(steamid, payload.favourite)
    return ok({"steamid": steamid, "favourite": payload.favourite})


@router.put("/{steamid}/notes", summary="Enregistrer une note personnelle")
async def notes(
    steamid: SteamIdDep, context: ContextDep, payload: NotesRequest
) -> dict:
    context.players.ensure(steamid)
    context.players.set_notes(steamid, payload.notes)
    return ok({"steamid": steamid, "notes": payload.notes})


@router.delete("/{steamid}", summary="Supprimer un joueur du suivi local")
async def delete(steamid: SteamIdDep, context: ContextDep) -> dict:
    context.players.delete(steamid)
    return ok({"deleted": steamid})
