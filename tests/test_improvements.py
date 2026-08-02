"""Tests des dix améliorations majeures."""

from __future__ import annotations

import pytest

from cs2tracker.anticheat.calibration import (
    LabelledProfile,
    blind_config,
    evaluate,
    recommend_threshold,
)
from cs2tracker.anticheat.compare import compare
from cs2tracker.anticheat.tiers import (
    DEFAULT_TIER,
    TIERS,
    assign_tier,
    tier_from_faceit,
)
from cs2tracker.demos.analysis import (
    AimSample,
    angle_delta,
    detect_recoil_perfection,
    detect_snaps,
    summarise_hitzones,
    view_speed,
)
from cs2tracker.storage.audit import AuditRepository, bucket_for
from cs2tracker.storage.db import Database
from cs2tracker.storage.matches_history import (
    MatchRecord,
    PlayerMatchRepository,
    TeammateRepository,
)
from tests.conftest import make_bans, make_profile, make_stats


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.connect()
    yield database
    database.close()


# =========================================================== 7. Journal d'audit
def test_audit_records_and_measures(db):
    audit = AuditRepository(db)
    audit.record("76561198000000001", analysed_at="2026-01-01T00:00:00Z",
                 score=88.0, verdict="CRITICAL", bans_at_verdict=0)

    summary = audit.summary()
    assert summary["verdicts_tracked"] == 1
    assert summary["confirmed_banned"] == 0
    # Un seul verdict ne permet aucune conclusion statistique.
    assert summary["statistically_usable"] is False


def test_audit_only_counts_bans_after_the_verdict(db):
    """Un compte deja banni au moment de l'analyse ne valide rien."""
    audit = AuditRepository(db)
    audit.record("76561198000000001", analysed_at="2026-01-01T00:00:00Z",
                 score=90.0, verdict="CRITICAL", bans_at_verdict=2)

    # Toujours deux sanctions : rien de nouveau.
    assert audit.apply_check("76561198000000001", total_bans=2) is False
    assert audit.summary()["confirmed_banned"] == 0

    # Une sanction supplementaire, elle, confirme le verdict.
    assert audit.apply_check("76561198000000001", total_bans=3) is True
    assert audit.summary()["confirmed_banned"] == 1


def test_audit_recheck_queue_skips_confirmed(db):
    audit = AuditRepository(db)
    audit.record("76561198000000001", analysed_at="2026-01-01T00:00:00Z",
                 score=80.0, verdict="HIGH", bans_at_verdict=0)
    assert "76561198000000001" in audit.due_for_recheck()

    audit.apply_check("76561198000000001", total_bans=1)
    # Une fois le bannissement constate, inutile de continuer a interroger.
    assert "76561198000000001" not in audit.due_for_recheck()


def test_calibration_buckets_cover_the_scale(db):
    audit = AuditRepository(db)
    for index, score in enumerate([10.0, 40.0, 60.0, 75.0, 95.0]):
        audit.record(f"7656119800000000{index}", analysed_at=f"2026-01-0{index + 1}T00:00:00Z",
                     score=score, verdict="X", bans_at_verdict=0)

    buckets = audit.calibration()
    assert len(buckets) == 5
    assert sum(b["verdicts"] for b in buckets) == 5


def test_bucket_for_boundaries():
    assert bucket_for(0.0) == "0-29"
    assert bucket_for(29.9) == "0-29"
    assert bucket_for(30.0) == "30-49"
    assert bucket_for(100.0) == "85-100"


# ==================================================== 5. Analyse match par match
def _match(index: int, kills: int, rounds: int = 24) -> MatchRecord:
    return MatchRecord(
        steamid64="76561198000000001",
        played_at=f"2026-01-{index + 1:02d}T12:00:00Z",
        source="test", external_id=f"m{index}",
        map_name="de_dust2", rounds=rounds, kills=kills, deaths=15,
        assists=4, headshots=kills // 2, damage=rounds * 78, mvps=2, won=index % 2 == 0,
    )


def test_match_distribution_needs_a_sample(db):
    repo = PlayerMatchRepository(db)
    repo.save(_match(0, 20))
    assert repo.distribution("76561198000000001") is None


def test_match_distribution_describes_spread(db):
    repo = PlayerMatchRepository(db)
    for index, kills in enumerate([12, 18, 22, 15, 30, 9, 25]):
        repo.save(_match(index, kills))

    distribution = repo.distribution("76561198000000001")
    assert distribution is not None
    assert distribution["matches"] == 7
    kpr = distribution["kills_per_round"]
    assert kpr["min"] < kpr["median"] < kpr["max"]
    assert distribution["consistency"]["kpr_variation"] > 0


def test_match_outliers_flag_the_extreme_game(db):
    repo = PlayerMatchRepository(db)
    # Six matchs ordinaires, un match aberrant.
    for index, kills in enumerate([14, 15, 13, 16, 14, 15]):
        repo.save(_match(index, kills))
    repo.save(_match(6, 48))

    outliers = repo.outliers("76561198000000001")
    assert outliers
    assert outliers[0]["kills"] == 48
    assert outliers[0]["z_score"] >= 2.0


def test_match_save_is_idempotent(db):
    repo = PlayerMatchRepository(db)
    repo.save(_match(0, 20))
    repo.save(_match(0, 25))
    matches = repo.list_for("76561198000000001")
    assert len(matches) == 1
    assert matches[0]["kills"] == 25


# ======================================================= 6. Detection de groupe
def test_teammates_graph_is_symmetric(db):
    repo = TeammateRepository(db)
    repo.record_lobby([("111", "CT"), ("222", "CT"), ("333", "T")])

    assert len(repo.companions("111", min_matches=1)) == 2
    assert len(repo.companions("333", min_matches=1)) == 2


def test_teammates_distinguishes_same_team(db):
    repo = TeammateRepository(db)
    repo.record_lobby([("111", "CT"), ("222", "CT"), ("333", "T")])

    companions = {c["teammate_id"]: c for c in repo.companions("111", min_matches=1)}
    assert companions["222"]["same_team"] == 1
    assert companions["333"]["same_team"] == 0


def test_group_risk_without_analysis_is_honest(db):
    repo = TeammateRepository(db)
    repo.record_lobby([("111", "CT"), ("222", "CT")])
    risk = repo.group_risk("111", min_matches=1)
    assert risk["available"] is False
    assert "analyse" in risk["reason"].lower()


def test_clusters_need_suspicious_members(db):
    repo = TeammateRepository(db)
    for _ in range(3):
        repo.record_lobby([("111", "CT"), ("222", "CT")])
    # Aucun des deux n'a de score enregistre : pas de groupe.
    assert repo.clusters(min_matches=1, min_score=60.0) == []


# ===================================================== 3. References par rang
def test_faceit_level_maps_to_tier():
    assert tier_from_faceit(1).key == "debutant"
    assert tier_from_faceit(5).key == "intermediaire"
    assert tier_from_faceit(8).key == "avance"
    assert tier_from_faceit(10).key == "elite"


def test_tiers_are_ordered_by_difficulty():
    """Chaque palier doit exiger davantage que le precedent."""
    for lower, higher in zip(TIERS, TIERS[1:]):
        assert higher.headshot_rate.mean > lower.headshot_rate.mean
        assert higher.accuracy.mean > lower.accuracy.mean
        assert higher.kills_per_round.mean > lower.kills_per_round.mean


def test_faceit_level_takes_priority():
    assignment = assign_tier(faceit_level=10, hours_played=20.0, rounds_played=100)
    assert assignment.tier.key == "elite"
    assert assignment.confident is True


def test_small_sample_falls_back_to_median_tier():
    assignment = assign_tier(hours_played=3000.0, kills_per_round=1.2, rounds_played=50)
    assert assignment.tier is DEFAULT_TIER
    assert assignment.confident is False


def test_estimated_tier_reflects_output():
    weak = assign_tier(hours_played=100.0, kills_per_round=0.45, rounds_played=2000)
    strong = assign_tier(hours_played=3000.0, kills_per_round=0.95, rounds_played=20000)
    order = [tier.key for tier in TIERS]
    assert order.index(strong.tier.key) > order.index(weak.tier.key)


# ================================================== 2. Calibration adverse
def test_blind_config_neutralises_ban_detectors():
    """Sans cela, le moteur reconnaitrait les tricheurs a leur bannissement."""
    config = blind_config()
    assert all(
        weight == 0.0 for key, weight in config.weights.items() if key.startswith("ban.")
    )
    assert config.confirmed_ban_floor == 0.0
    # Les autres detecteurs restent intacts.
    assert config.weights["aim.headshot_rate"] > 0


def test_evaluate_separates_populations():
    blatant = make_profile(
        stats=make_stats(kills=60_000, deaths=12_000, headshot_kills=52_000,
                         shots_fired=190_000, shots_hit=96_000, rounds=40_000,
                         hours=210.0, damage=7_400_000),
        bans=make_bans(vac=1, days_since=30),
    )
    corpus = [
        LabelledProfile(profile=blatant, is_cheater=True),
        LabelledProfile(profile=make_profile(), is_cheater=False),
    ]
    report = evaluate(corpus, threshold=70.0)
    assert report.separation > 0
    # Deux profils ne suffisent evidemment pas a conclure.
    assert report.as_dict()["usable"] is False


def test_recommend_threshold_reports_impossibility():
    """Un corpus ou aucun seuil ne tient doit le dire, pas inventer un chiffre."""
    corpus = [LabelledProfile(profile=make_profile(), is_cheater=True)]
    recommendation = recommend_threshold(corpus, max_false_positive_rate=0.0)
    assert "sweep" in recommendation


# ============================================== 8. Comparaison entre joueurs
def test_compare_designates_a_winner_per_metric():
    strong = make_profile(stats=make_stats(kills=70_000, deaths=35_000))
    average = make_profile()
    result = compare(strong, average)

    assert result["comparable"] is True
    assert len(result["metrics"]) == 10
    kd = next(m for m in result["metrics"] if m["key"] == "kd")
    assert kd["winner"] == "left"


def test_compare_handles_private_profile():
    result = compare(make_profile(), make_profile(stats=None))
    assert result["comparable"] is False
    assert "indisponibles" in result["reason"]


def test_compare_warns_on_uneven_samples():
    big = make_profile(stats=make_stats(rounds=80_000))
    small = make_profile(stats=make_stats(rounds=300))
    assert "inegaux" in compare(big, small)["sample_warning"]


def test_compare_respects_lower_is_better():
    """Moins de balles par kill est meilleur : le vainqueur doit s'inverser."""
    efficient = make_profile(stats=make_stats(shots_fired=400_000))
    wasteful = make_profile(stats=make_stats(shots_fired=1_600_000))
    result = compare(efficient, wasteful)
    duel = next(m for m in result["metrics"] if m["key"] == "shots_per_kill")
    assert duel["lower_is_better"] is True
    assert duel["winner"] == "left"


# ==================================================== 1. Analyse des demos
def test_angle_delta_wraps_around():
    """359° vers 1° est un ecart de 2°, pas de 358°."""
    assert angle_delta(359.0, 1.0) == pytest.approx(2.0)
    assert angle_delta(1.0, 359.0) == pytest.approx(2.0)
    assert angle_delta(10.0, 20.0) == pytest.approx(10.0)


def test_view_speed_combines_axes():
    speeds = view_speed([0.0, 3.0], [0.0, 4.0])
    assert speeds == pytest.approx([5.0])


def test_snap_detector_needs_a_sample():
    finding = detect_snaps([])
    assert finding.confidence == 0.0
    assert finding.score == 0.0


def test_snap_detector_flags_instant_acquisition():
    smooth = [AimSample(i, "1", "ak47", (2.0, 3.0, 4.0, 3.0)) for i in range(60)]
    snappy = [AimSample(i, "1", "ak47", (1.0, 2.0, 45.0, 1.0)) for i in range(60)]

    assert detect_snaps(smooth).score < 0.2
    assert detect_snaps(snappy).score > 0.8


def test_recoil_detector_is_inverted():
    """C'est la regularite, pas l'amplitude, qui interpelle."""
    human = [3.0 + (index % 7) for index in range(100)]
    scripted = [3.0 + (index % 2) * 0.01 for index in range(100)]

    assert detect_recoil_perfection(human).score < 0.4
    assert detect_recoil_perfection(scripted).score > 0.6


def test_hitzones_summary():
    summary = summarise_hitzones({"tete": 30, "poitrine": 50, "jambe gauche": 20})
    assert summary["available"] is True
    assert summary["total_hits"] == 100
    assert summary["zones"]["poitrine"]["share"] == pytest.approx(0.5)


def test_hitzones_empty():
    assert summarise_hitzones({})["available"] is False
