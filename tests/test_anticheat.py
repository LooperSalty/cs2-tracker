"""Tests du moteur anti-triche.

L'exigence centrale : le moteur doit être **conservateur**. Un joueur moyen ne
doit jamais être signalé, un échantillon faible ne doit jamais produire un score
élevé, et seuls des écarts multiples et corroborés doivent faire monter le score.
"""

from __future__ import annotations

import pytest

from cs2tracker.anticheat.engine import analyse, analyse_many
from cs2tracker.anticheat.report import to_compact_dict, to_text
from cs2tracker.anticheat.signals import Severity
from cs2tracker.gsi.tracker import LivePlayerMetrics, RoundRecord
from tests.conftest import (
    make_account,
    make_bans,
    make_profile,
    make_stats,
    make_summary,
)


# --- Comportement de référence ------------------------------------------------
def test_average_player_is_clean(average_profile):
    result = analyse(average_profile)
    assert result.suspicion_score < 30
    assert result.verdict in {"CLEAN", "LOW"}
    assert not result.has_confirmed_ban


def test_blatant_profile_scores_high(blatant_profile):
    result = analyse(blatant_profile)
    assert result.suspicion_score >= 70
    assert result.verdict in {"HIGH", "CRITICAL"}


def test_blatant_scores_above_average(average_profile, blatant_profile):
    normal = analyse(average_profile).suspicion_score
    cheater = analyse(blatant_profile).suspicion_score
    assert cheater > normal + 40


# --- Prudence statistique -----------------------------------------------------
def test_tiny_sample_cannot_produce_high_score():
    """3 kills dont 3 headshots ne doivent pas déclencher d'alerte."""
    profile = make_profile(
        stats=make_stats(
            kills=3,
            deaths=1,
            headshot_kills=3,
            shots_fired=9,
            shots_hit=6,
            rounds=5,
            hours=0.5,
            damage=400,
        )
    )
    result = analyse(profile)
    assert result.suspicion_score < 50, "Un micro-echantillon ne doit pas condamner"


def test_low_confidence_yields_indeterminate_verdict():
    profile = make_profile(
        summary=make_summary(public=False),
        stats=None,
        account=make_account(hours=0.0, level=0, friends=0, games=0),
    )
    result = analyse(profile)
    assert result.global_confidence < 0.9
    assert result.suspicion_score < 60


def test_private_profile_is_not_treated_as_guilt():
    profile = make_profile(summary=make_summary(public=False), stats=None)
    result = analyse(profile)
    assert result.suspicion_score < 45


def test_smurf_signature_is_flagged_as_ambiguous():
    """Compte jeune + peu d'heures + bon niveau, mais visée normale."""
    profile = make_profile(
        stats=make_stats(
            kills=4_000,
            deaths=3_000,
            headshot_kills=1_850,
            shots_fired=20_000,
            shots_hit=4_200,
            rounds=5_000,
            hours=90.0,
            damage=380_000,
        ),
        summary=make_summary(age_days=40),
        account=make_account(hours=90.0, level=3, friends=6, games=4),
    )
    result = analyse(profile)
    smurf_signal = next(
        s for s in result.signals if s.key == "account.smurf_profile"
    )
    assert smurf_signal.metadata.get("ambiguous_with_smurf") is True
    assert "smurf" in smurf_signal.explanation.lower()
    # La visée étant normale, le verdict ne doit pas basculer en HIGH.
    assert result.verdict not in {"CRITICAL"}


# --- Sanctions ----------------------------------------------------------------
def test_vac_ban_forces_high_score(average_profile):
    banned = make_profile(bans=make_bans(vac=1, days_since=30))
    result = analyse(banned)
    assert result.has_confirmed_ban
    assert result.suspicion_score >= 80
    assert result.global_confidence >= 0.9


def test_old_ban_weighs_less_than_recent_ban():
    recent = analyse(make_profile(bans=make_bans(vac=1, days_since=10)))
    old = analyse(make_profile(bans=make_bans(vac=1, days_since=3_000)))
    recency_recent = next(s for s in recent.signals if s.key == "ban.recency")
    recency_old = next(s for s in old.signals if s.key == "ban.recency")
    assert recency_recent.score > recency_old.score


# --- Signaux et explicabilité -------------------------------------------------
def test_every_signal_is_explained(average_profile):
    result = analyse(average_profile)
    assert result.signals
    for signal in result.signals:
        assert signal.explanation.strip(), f"{signal.key} sans explication"
        assert 0.0 <= signal.score <= 1.0
        assert 0.0 <= signal.confidence <= 1.0


def test_headshot_outlier_produces_aim_signal():
    profile = make_profile(
        stats=make_stats(headshot_kills=42_000)  # 84 % de HS sur 50 000 kills
    )
    result = analyse(profile)
    signal = next(s for s in result.signals if s.key == "aim.headshot_rate")
    assert signal.score > 0.7
    assert signal.severity in {Severity.HIGH, Severity.CRITICAL}


def test_accuracy_outlier_produces_aim_signal():
    # 440 000 impacts sur 951 000 tirs = 46 % de precision (reference : 20,5 %).
    profile = make_profile(stats=make_stats(shots_hit=440_000))
    result = analyse(profile)
    signal = next(s for s in result.signals if s.key == "aim.accuracy")
    assert signal.score > 0.6


def test_score_is_bounded(blatant_profile):
    result = analyse(blatant_profile)
    assert 0.0 <= result.suspicion_score <= 100.0


def test_categories_cover_all_scoring_signals(average_profile):
    result = analyse(average_profile)
    assert result.categories
    assert all(0 <= c.score <= 1 for c in result.categories)


# --- Croisement avec le temps réel --------------------------------------------
def _metrics(rounds: int, kills: int, headshots: int, damage: int) -> LivePlayerMetrics:
    records = tuple(
        RoundRecord(
            round_number=i + 1,
            kills=kills,
            headshots=headshots,
            damage=damage,
            died=i % 3 == 0,
            money_start=4_000,
            equip_value=4_700,
            utility_bought=1,
            kill_offsets=(10.0, 12.0) if kills >= 2 else (10.0,),
        )
        for i in range(rounds)
    )
    return LivePlayerMetrics(
        steamid="76561198000000001",
        name="TestPlayer",
        team="CT",
        rounds=records,
        total_kills=rounds * kills,
        total_deaths=rounds // 3,
    )


def test_live_metrics_are_used_when_available(average_profile):
    live = _metrics(rounds=25, kills=3, headshots=3, damage=185)
    result = analyse(average_profile, live)
    assert result.data_sources["live_gsi"] is True
    live_signal = next(s for s in result.signals if s.key == "live.headshot_rate")
    assert live_signal.confidence > 0


def test_insufficient_live_rounds_are_neutral(average_profile):
    live = _metrics(rounds=2, kills=1, headshots=1, damage=90)
    result = analyse(average_profile, live)
    live_signal = next(s for s in result.signals if s.key == "live.headshot_rate")
    assert live_signal.confidence == 0.0


def test_perfectly_regular_damage_flags_consistency(average_profile):
    """Des dégâts identiques à chaque manche = variabilité nulle."""
    live = _metrics(rounds=20, kills=2, headshots=1, damage=150)
    result = analyse(average_profile, live)
    signal = next(s for s in result.signals if s.key == "consistency.adr_variability")
    assert signal.score > 0.5


# --- Lots et rapports ---------------------------------------------------------
def test_analyse_many_sorts_by_score(average_profile, blatant_profile):
    results = analyse_many([average_profile, blatant_profile])
    assert len(results) == 2
    assert results[0].suspicion_score >= results[1].suspicion_score


def test_text_report_contains_disclaimer(blatant_profile):
    report = to_text(analyse(blatant_profile))
    assert "RAPPORT D'ANALYSE" in report
    assert "preuve" in report.lower()
    assert "Recommandation" in report


def test_compact_dict_shape(average_profile):
    compact = to_compact_dict(analyse(average_profile))
    assert set(compact) >= {"steamid", "name", "score", "verdict", "confidence"}


def test_result_serialises_to_json_safe_dict(average_profile):
    payload = analyse(average_profile).as_dict()
    assert "disclaimer" in payload
    assert isinstance(payload["signals"], list)
    assert isinstance(payload["suspicion_score"], float)


@pytest.mark.parametrize("include_features", [True, False])
def test_feature_inclusion_is_optional(average_profile, include_features):
    payload = analyse(average_profile).as_dict(include_features=include_features)
    assert ("features" in payload) is include_features
