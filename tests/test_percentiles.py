"""Tests du classement dans la population et de l'extraction d'identifiants."""

from __future__ import annotations

import pytest

from cs2tracker.anticheat.percentiles import (
    normal_cdf,
    rank_metric,
    rank_player,
    rank_weapon_accuracy,
    tier_for,
)
from cs2tracker.anticheat import baselines
from cs2tracker.core.steamid import extract_all
from tests.conftest import make_stats

STATUS_CS2 = """
hostname: Valve Counter-Strike 2 EU West Server
version : 1.40.9.9/14000 9876 secure
map     : de_mirage
players : 10 humans, 0 bots

 id   name                steamid
 2    "Joueur Un"         [U:1:123456789]
 3    "Joueur Deux"       [U:1:987654321]
 4    "Ancien Format"     STEAM_1:0:11101
 5    "Direct 64"         76561198043717815
"""


# --- Loi normale --------------------------------------------------------------
def test_normal_cdf_reference_points():
    assert normal_cdf(0.0) == pytest.approx(0.5, abs=1e-6)
    assert normal_cdf(1.0) == pytest.approx(0.8413, abs=1e-3)
    assert normal_cdf(-1.0) == pytest.approx(0.1587, abs=1e-3)
    assert normal_cdf(2.0) == pytest.approx(0.9772, abs=1e-3)


def test_tiers_are_ordered():
    assert tier_for(0.995)[0] == "elite"
    assert tier_for(0.92)[0] == "excellent"
    assert tier_for(0.80)[0] == "bon"
    assert tier_for(0.50)[0] == "moyen"
    assert tier_for(0.20)[0] == "faible"
    assert tier_for(0.02)[0] == "debutant"


# --- Classement d'une metrique ------------------------------------------------
def test_average_value_lands_at_median():
    ranked = rank_metric(
        "hs", "Headshots", baselines.HEADSHOT_RATE.mean, baselines.HEADSHOT_RATE
    )
    assert ranked.percentile == pytest.approx(0.5, abs=1e-6)
    assert ranked.top_percent == pytest.approx(50.0, abs=0.1)


def test_high_value_ranks_high():
    ranked = rank_metric("hs", "Headshots", 0.70, baselines.HEADSHOT_RATE)
    assert ranked.percentile > 0.99
    assert ranked.tier[0] == "elite"


def test_lower_is_better_inverts_the_ranking():
    """Moins de balles par kill est *meilleur* : le percentile doit monter."""
    efficient = rank_metric(
        "spk", "Balles/kill", 10.0, baselines.SHOTS_PER_KILL, lower_is_better=True
    )
    wasteful = rank_metric(
        "spk", "Balles/kill", 30.0, baselines.SHOTS_PER_KILL, lower_is_better=True
    )
    assert efficient.percentile > 0.9
    assert wasteful.percentile < 0.1


def test_percentile_is_bounded():
    extreme = rank_metric("hs", "Headshots", 0.99, baselines.HEADSHOT_RATE)
    assert 0.0 < extreme.percentile < 1.0


# --- Classement complet -------------------------------------------------------
def test_rank_player_on_average_profile():
    ranking = rank_player(make_stats())
    assert ranking["available"] is True
    assert 35 <= ranking["overall_percentile"] <= 65
    assert len(ranking["metrics"]) == 10
    assert ranking["sample"]["reliable"] is True


def test_rank_player_on_strong_profile():
    strong = make_stats(kills=70_000, deaths=35_000, headshot_kills=42_000)
    ranking = rank_player(strong)
    assert ranking["overall_percentile"] > 60


def test_rank_player_without_stats():
    ranking = rank_player(None)
    assert ranking["available"] is False
    assert ranking["metrics"] == []


def test_every_metric_is_serialisable():
    for metric in rank_player(make_stats())["metrics"]:
        assert set(metric) >= {"key", "label", "value", "percentile", "tier", "top_percent"}
        assert 0 <= metric["percentile"] <= 100


def test_weapon_ranking_uses_category_reference():
    """Une AWP a 34 % de precision est moyenne ; un AK a 34 % est exceptionnel."""
    awp = rank_weapon_accuracy("awp", 0.34, "Sniper")
    rifle = rank_weapon_accuracy("ak47", 0.34, "Fusil")
    assert awp is not None and rifle is not None
    assert rifle["percentile"] > awp["percentile"]


def test_weapon_ranking_unknown_category():
    assert rank_weapon_accuracy("knife", 0.0, "Corps a corps") is None


# --- Extraction d'identifiants ------------------------------------------------
def test_extract_all_from_cs2_status():
    found = extract_all(STATUS_CS2)
    assert len(found) == 4
    assert str(found[0].steamid64) == "76561198083722517"
    assert found[3].steamid64 == 76561198043717815


def test_extract_all_deduplicates_preserving_order():
    text = "[U:1:111] [U:1:222] [U:1:111]"
    found = extract_all(text)
    assert len(found) == 2
    assert found[0].account_id == 111
    assert found[1].account_id == 222


def test_extract_all_ignores_noise():
    assert extract_all("aucun identifiant ici, juste 42 et 1234") == ()
    assert extract_all("") == ()


def test_extract_all_respects_limit():
    text = " ".join(f"[U:1:{i}]" for i in range(1, 40))
    assert len(extract_all(text, limit=10)) == 10


def test_extract_all_handles_mixed_formats():
    found = extract_all("STEAM_1:1:20 et [U:1:99] et 76561198043717815")
    assert len(found) == 3
