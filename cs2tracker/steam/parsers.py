"""Transformation des payloads Steam bruts en modèles de domaine.

Toutes les fonctions sont *défensives* : Steam omet fréquemment des champs
(profil partiellement privé, statistique jamais incrémentée, schéma modifié).
Une donnée absente vaut 0, jamais une exception.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from cs2tracker.core.models import (
    AccountOverview,
    BanStatus,
    Cs2Stats,
    MapStats,
    OwnedGame,
    PlayerSummary,
    WeaponStats,
)
from cs2tracker.core.utils import safe_div, to_int
from cs2tracker.steam.maps import map_display_name
from cs2tracker.steam.weapons import WEAPONS, weapon_category, weapon_display_name

_KILL_PREFIX = "total_kills_"
_SHOT_PREFIX = "total_shots_"
_HIT_PREFIX = "total_hits_"
_MAP_WIN_PREFIX = "total_wins_map_"
_MAP_ROUND_PREFIX = "total_rounds_map_"

#: Suffixes de ``total_kills_*`` qui ne désignent pas une arme.
_NON_WEAPON_KILL_SUFFIXES = frozenset(
    {"headshot", "enemy_weapon", "knife_fight", "enemy_blinded", "against_zoomed_sniper"}
)


def parse_player_summary(entry: Mapping[str, Any]) -> PlayerSummary:
    return PlayerSummary(
        steamid64=str(entry.get("steamid", "")),
        persona_name=str(entry.get("personaname", "")),
        profile_url=str(entry.get("profileurl", "")),
        avatar=str(entry.get("avatar", "")),
        avatar_medium=str(entry.get("avatarmedium", "")),
        avatar_full=str(entry.get("avatarfull", "")),
        visibility_state=to_int(entry.get("communityvisibilitystate"), 1),
        profile_state=to_int(entry.get("profilestate")),
        last_logoff=to_int(entry.get("lastlogoff")) or None,
        time_created=to_int(entry.get("timecreated")) or None,
        persona_state=to_int(entry.get("personastate")),
        country_code=entry.get("loccountrycode") or None,
        state_code=entry.get("locstatecode") or None,
        real_name=entry.get("realname") or None,
        primary_clan_id=entry.get("primaryclanid") or None,
        game_id=str(entry["gameid"]) if entry.get("gameid") else None,
        game_extra_info=entry.get("gameextrainfo") or None,
    )


def parse_ban_status(entry: Mapping[str, Any]) -> BanStatus:
    return BanStatus(
        steamid64=str(entry.get("SteamId", "")),
        community_banned=bool(entry.get("CommunityBanned", False)),
        vac_banned=bool(entry.get("VACBanned", False)),
        number_of_vac_bans=to_int(entry.get("NumberOfVACBans")),
        days_since_last_ban=to_int(entry.get("DaysSinceLastBan")),
        number_of_game_bans=to_int(entry.get("NumberOfGameBans")),
        economy_ban=str(entry.get("EconomyBan", "none")),
    )


def stats_list_to_map(stats: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Convertit ``[{name, value}, …]`` en dictionnaire plat."""
    result: dict[str, int] = {}
    for item in stats:
        name = item.get("name")
        if isinstance(name, str):
            result[name] = to_int(item.get("value"))
    return result


def extract_weapon_stats(raw: Mapping[str, int]) -> tuple[WeaponStats, ...]:
    """Reconstruit les stats par arme, y compris les armes hors table connue."""
    keys: set[str] = set()
    for stat_name in raw:
        for prefix in (_KILL_PREFIX, _SHOT_PREFIX, _HIT_PREFIX):
            if stat_name.startswith(prefix):
                suffix = stat_name[len(prefix) :]
                if suffix and suffix not in _NON_WEAPON_KILL_SUFFIXES:
                    keys.add(suffix)
    # On garde l'ordre canonique de la table puis on ajoute les inconnues.
    known_order = [w.key for w in WEAPONS if w.key in keys]
    extras = sorted(keys - set(known_order))

    weapons: list[WeaponStats] = []
    for key in known_order + extras:
        kills = raw.get(f"{_KILL_PREFIX}{key}", 0)
        shots = raw.get(f"{_SHOT_PREFIX}{key}", 0)
        hits = raw.get(f"{_HIT_PREFIX}{key}", 0)
        if kills == 0 and shots == 0 and hits == 0:
            continue
        weapons.append(
            WeaponStats(
                key=key,
                display_name=weapon_display_name(key),
                category=weapon_category(key),
                kills=kills,
                shots_fired=shots,
                shots_hit=hits,
            )
        )
    return tuple(sorted(weapons, key=lambda w: w.kills, reverse=True))


def extract_map_stats(raw: Mapping[str, int]) -> tuple[MapStats, ...]:
    keys: set[str] = set()
    for stat_name in raw:
        for prefix in (_MAP_WIN_PREFIX, _MAP_ROUND_PREFIX):
            if stat_name.startswith(prefix):
                keys.add(stat_name[len(prefix) :])

    maps: list[MapStats] = []
    for key in sorted(keys):
        wins = raw.get(f"{_MAP_WIN_PREFIX}{key}", 0)
        rounds = raw.get(f"{_MAP_ROUND_PREFIX}{key}", 0)
        if wins == 0 and rounds == 0:
            continue
        maps.append(
            MapStats(
                key=key,
                display_name=map_display_name(key),
                rounds_played=rounds,
                wins=wins,
            )
        )
    return tuple(sorted(maps, key=lambda m: m.rounds_played, reverse=True))


def parse_cs2_stats(steamid64: str, payload: Mapping[str, Any]) -> Cs2Stats | None:
    """Construit ``Cs2Stats`` depuis ``GetUserStatsForGame``.

    Renvoie ``None`` si Steam n'a renvoyé aucune statistique (profil privé,
    joueur n'ayant jamais lancé CS2, ou stats réinitialisées).
    """
    container = payload.get("playerstats")
    if not isinstance(container, Mapping):
        return None
    raw_stats = container.get("stats")
    if not isinstance(raw_stats, Sequence) or not raw_stats:
        return None

    raw = stats_list_to_map(raw_stats)

    def value(name: str) -> int:
        return raw.get(name, 0)

    return Cs2Stats(
        steamid64=steamid64,
        total_kills=value("total_kills"),
        total_deaths=value("total_deaths"),
        total_time_played=value("total_time_played"),
        total_planted_bombs=value("total_planted_bombs"),
        total_defused_bombs=value("total_defused_bombs"),
        total_wins=value("total_wins"),
        total_damage_done=value("total_damage_done"),
        total_money_earned=value("total_money_earned"),
        total_rescued_hostages=value("total_rescued_hostages"),
        total_kills_headshot=value("total_kills_headshot"),
        total_shots_fired=value("total_shots_fired"),
        total_shots_hit=value("total_shots_hit"),
        total_rounds_played=value("total_rounds_played"),
        total_matches_played=value("total_matches_played"),
        total_matches_won=value("total_matches_won"),
        total_mvps=value("total_mvps"),
        total_contribution_score=value("total_contribution_score"),
        total_wins_pistolround=value("total_wins_pistolround"),
        last_match_kills=value("last_match_kills"),
        last_match_deaths=value("last_match_deaths"),
        last_match_mvps=value("last_match_mvps"),
        last_match_damage=value("last_match_damage"),
        last_match_rounds=value("last_match_rounds"),
        last_match_wins=value("last_match_wins"),
        last_match_max_players=value("last_match_max_players"),
        last_match_money_spent=value("last_match_money_spent"),
        last_match_favweapon_id=value("last_match_favweapon_id"),
        weapons=extract_weapon_stats(raw),
        maps=extract_map_stats(raw),
        raw=raw,
    )


def parse_owned_games(payload: Mapping[str, Any]) -> tuple[OwnedGame, ...]:
    response = payload.get("response")
    if not isinstance(response, Mapping):
        return ()
    games = response.get("games")
    if not isinstance(games, Sequence):
        return ()
    parsed: list[OwnedGame] = []
    for entry in games:
        if not isinstance(entry, Mapping):
            continue
        parsed.append(
            OwnedGame(
                appid=to_int(entry.get("appid")),
                name=str(entry.get("name", "")),
                playtime_forever_minutes=to_int(entry.get("playtime_forever")),
                playtime_2weeks_minutes=to_int(entry.get("playtime_2weeks")),
                last_played=to_int(entry.get("rtime_last_played")) or None,
            )
        )
    return tuple(parsed)


def build_account_overview(
    *,
    games: Sequence[OwnedGame],
    steam_level: int,
    friends: Sequence[Mapping[str, Any]],
    badges_count: int,
    cs2_app_id: int,
) -> AccountOverview:
    cs2_game = next((g for g in games if g.appid == cs2_app_id), None)
    total_hours = sum(g.hours for g in games)
    friend_timestamps = [
        to_int(f.get("friend_since")) for f in friends if to_int(f.get("friend_since"))
    ]
    return AccountOverview(
        steam_level=steam_level,
        games_owned=len(games),
        cs2_hours=cs2_game.hours if cs2_game else 0.0,
        cs2_hours_2weeks=(
            cs2_game.playtime_2weeks_minutes / 60.0 if cs2_game else 0.0
        ),
        cs2_last_played=cs2_game.last_played if cs2_game else None,
        friends_count=len(friends),
        friends_oldest_since=min(friend_timestamps) if friend_timestamps else None,
        badges_count=badges_count,
        total_playtime_hours=total_hours,
    )


def parse_achievements(payload: Mapping[str, Any]) -> tuple[int, int]:
    """Renvoie ``(débloqués, total)``."""
    container = payload.get("playerstats")
    if not isinstance(container, Mapping):
        return (0, 0)
    achievements = container.get("achievements")
    if not isinstance(achievements, Sequence):
        return (0, 0)
    unlocked = sum(1 for a in achievements if isinstance(a, Mapping) and to_int(a.get("achieved")))
    return (unlocked, len(achievements))


def summarize_weapon_totals(weapons: Sequence[WeaponStats]) -> dict[str, Any]:
    """Agrégat transverse utile aux détecteurs et à l'UI."""
    total_kills = sum(w.kills for w in weapons)
    total_shots = sum(w.shots_fired for w in weapons)
    total_hits = sum(w.shots_hit for w in weapons)
    by_category: dict[str, dict[str, int]] = {}
    for weapon in weapons:
        bucket = by_category.setdefault(
            weapon.category, {"kills": 0, "shots": 0, "hits": 0}
        )
        bucket["kills"] += weapon.kills
        bucket["shots"] += weapon.shots_fired
        bucket["hits"] += weapon.shots_hit
    return {
        "total_kills": total_kills,
        "total_shots": total_shots,
        "total_hits": total_hits,
        "overall_accuracy": round(safe_div(total_hits, total_shots), 4),
        "by_category": {
            name: {
                **values,
                "accuracy": round(safe_div(values["hits"], values["shots"]), 4),
            }
            for name, values in sorted(by_category.items())
        },
        "top_weapon": weapons[0].display_name if weapons else None,
    }
