"""Tests de conversion des payloads Steam."""

from __future__ import annotations

from cs2tracker.steam.parsers import (
    build_account_overview,
    extract_map_stats,
    extract_weapon_stats,
    parse_ban_status,
    parse_cs2_stats,
    parse_owned_games,
    parse_player_summary,
    stats_list_to_map,
    summarize_weapon_totals,
)


def stats_payload() -> dict:
    return {
        "playerstats": {
            "steamID": "76561198000000001",
            "gameName": "ValveTestApp260",
            "stats": [
                {"name": "total_kills", "value": 12_345},
                {"name": "total_deaths", "value": 11_000},
                {"name": "total_time_played", "value": 3_600_000},
                {"name": "total_kills_headshot", "value": 5_800},
                {"name": "total_shots_fired", "value": 90_000},
                {"name": "total_shots_hit", "value": 19_000},
                {"name": "total_rounds_played", "value": 20_000},
                {"name": "total_damage_done", "value": 1_500_000},
                {"name": "total_mvps", "value": 2_100},
                {"name": "total_wins", "value": 10_100},
                {"name": "total_kills_ak47", "value": 4_000},
                {"name": "total_shots_ak47", "value": 30_000},
                {"name": "total_hits_ak47", "value": 6_600},
                {"name": "total_kills_awp", "value": 900},
                {"name": "total_shots_awp", "value": 2_400},
                {"name": "total_hits_awp", "value": 1_050},
                {"name": "total_kills_knife", "value": 45},
                {"name": "total_wins_map_de_dust2", "value": 3_000},
                {"name": "total_rounds_map_de_dust2", "value": 6_100},
                {"name": "total_wins_map_de_mirage", "value": 2_000},
                {"name": "total_rounds_map_de_mirage", "value": 4_050},
                {"name": "last_match_kills", "value": 22},
                {"name": "last_match_deaths", "value": 17},
                {"name": "last_match_damage", "value": 2_400},
                {"name": "last_match_rounds", "value": 26},
                {"name": "last_match_favweapon_id", "value": 7},
            ],
        }
    }


def test_stats_list_to_map():
    mapped = stats_list_to_map(stats_payload()["playerstats"]["stats"])
    assert mapped["total_kills"] == 12_345
    assert mapped["total_kills_ak47"] == 4_000


def test_parse_cs2_stats_core_ratios():
    stats = parse_cs2_stats("76561198000000001", stats_payload())
    assert stats is not None
    assert stats.total_kills == 12_345
    assert stats.kd_ratio == round(12_345 / 11_000, 10) or stats.kd_ratio > 1.1
    assert 0.46 < stats.headshot_rate < 0.48
    assert 0.20 < stats.accuracy < 0.22
    assert stats.hours_played == 1_000.0
    assert stats.has_meaningful_sample


def test_parse_cs2_stats_returns_none_when_empty():
    assert parse_cs2_stats("1", {}) is None
    assert parse_cs2_stats("1", {"playerstats": {}}) is None
    assert parse_cs2_stats("1", {"playerstats": {"stats": []}}) is None


def test_weapon_extraction_orders_by_kills():
    raw = stats_list_to_map(stats_payload()["playerstats"]["stats"])
    weapons = extract_weapon_stats(raw)
    keys = [w.key for w in weapons]
    assert keys[0] == "ak47"
    assert "awp" in keys
    assert "knife" in keys
    ak = next(w for w in weapons if w.key == "ak47")
    assert ak.display_name == "AK-47"
    assert ak.category == "Fusil"
    assert 0.21 < ak.accuracy < 0.23


def test_weapon_extraction_skips_headshot_suffix():
    weapons = extract_weapon_stats({"total_kills_headshot": 500})
    assert weapons == ()


def test_map_extraction():
    raw = stats_list_to_map(stats_payload()["playerstats"]["stats"])
    maps = extract_map_stats(raw)
    assert len(maps) == 2
    dust = next(m for m in maps if m.key == "de_dust2")
    assert dust.display_name == "Dust II"
    assert 0.48 < dust.win_rate < 0.50


def test_summarize_weapon_totals():
    raw = stats_list_to_map(stats_payload()["playerstats"]["stats"])
    aggregate = summarize_weapon_totals(extract_weapon_stats(raw))
    assert aggregate["total_kills"] > 0
    assert "Fusil" in aggregate["by_category"]
    assert aggregate["top_weapon"] == "AK-47"


def test_parse_player_summary_visibility():
    public = parse_player_summary(
        {
            "steamid": "76561198000000001",
            "personaname": "Joueur",
            "communityvisibilitystate": 3,
            "profileurl": "https://x",
            "timecreated": 1_300_000_000,
            "gameid": "730",
        }
    )
    assert public.is_public
    assert public.is_playing_cs2

    private = parse_player_summary(
        {"steamid": "1", "personaname": "X", "communityvisibilitystate": 1}
    )
    assert not private.is_public
    assert not private.is_in_game


def test_parse_ban_status():
    banned = parse_ban_status(
        {
            "SteamId": "76561198000000001",
            "CommunityBanned": False,
            "VACBanned": True,
            "NumberOfVACBans": 2,
            "DaysSinceLastBan": 400,
            "NumberOfGameBans": 1,
            "EconomyBan": "none",
        }
    )
    assert banned.has_any_ban
    assert banned.total_bans == 3

    clean = parse_ban_status({"SteamId": "1", "EconomyBan": "none"})
    assert not clean.has_any_ban


def test_parse_owned_games_and_overview():
    games = parse_owned_games(
        {
            "response": {
                "games": [
                    {"appid": 730, "name": "CS2", "playtime_forever": 60_000,
                     "playtime_2weeks": 600, "rtime_last_played": 1_700_000_000},
                    {"appid": 570, "name": "Dota 2", "playtime_forever": 6_000},
                ]
            }
        }
    )
    assert len(games) == 2
    overview = build_account_overview(
        games=games, steam_level=20, friends=[{"friend_since": 1}], badges_count=5,
        cs2_app_id=730,
    )
    assert overview.cs2_hours == 1_000.0
    assert overview.games_owned == 2
    assert 0.9 < overview.cs2_share_of_playtime < 1.0


def test_group_raw_stats_keeps_everything():
    """Aucune statistique ne doit disparaitre du regroupement."""
    from cs2tracker.steam.parsers import group_raw_stats

    raw = stats_list_to_map(stats_payload()["playerstats"]["stats"])
    groups = group_raw_stats(raw)

    regrouped = {
        entry["name"] for group in groups for entry in group["stats"]
    }
    assert regrouped == set(raw)
    assert sum(group["count"] for group in groups) == len(raw)


def test_group_raw_stats_labels_are_meaningful():
    from cs2tracker.steam.parsers import group_raw_stats

    raw = stats_list_to_map(stats_payload()["playerstats"]["stats"])
    labels = {group["key"] for group in group_raw_stats(raw)}
    assert "combat" in labels
    assert "armes" in labels
    assert "cartes" in labels


def test_group_raw_stats_on_empty_input():
    from cs2tracker.steam.parsers import group_raw_stats

    assert group_raw_stats({}) == []


def test_parse_owned_games_handles_private_response():
    assert parse_owned_games({}) == ()
    assert parse_owned_games({"response": {}}) == ()
