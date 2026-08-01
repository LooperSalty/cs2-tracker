"""Cohérence entre performance et expérience accumulée.

Le principe : la courbe de progression d'un joueur est lente. Une performance
de très haut niveau atteinte avec très peu d'heures est le signal le plus
robuste après la visée — tout en restant, seul, insuffisant (les smurfs
produisent exactement la même signature).
"""

from __future__ import annotations

from cs2tracker.anticheat import baselines
from cs2tracker.anticheat.detectors.common import build_signal, score_from_z
from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal, SignalCategory, neutral_signal
from cs2tracker.anticheat.weights import EngineConfig
from cs2tracker.core.utils import clamp, sample_confidence

CATEGORY = SignalCategory.PROGRESSION


def detect(features: PlayerFeatures, config: EngineConfig) -> tuple[Signal, ...]:
    if not features.has_stats:
        return (
            neutral_signal(
                "progression.performance_vs_hours",
                "Progression",
                CATEGORY,
                "Statistiques a vie indisponibles.",
            ),
        )
    return (
        _performance_vs_hours(features, config),
        _kills_per_hour(features, config),
        _kd(features, config),
        _round_win_rate(features, config),
        _mvp_rate(features, config),
    )


def _expected_performance_for_hours(hours: float) -> float:
    """Kills par manche attendus pour un volume d'heures donné.

    Modèle logarithmique saturant : forte progression au début, plateau ensuite.
    """
    if hours <= 0:
        return baselines.KILLS_PER_ROUND.mean
    floor = 0.48
    ceiling = 0.82
    progress = clamp(
        (hours / baselines.HIGH_EXPERIENCE_HOURS) ** 0.45, 0.0, 1.0
    )
    return floor + (ceiling - floor) * progress


def _performance_vs_hours(features: PlayerFeatures, config: EngineConfig) -> Signal:
    hours = features.hours_played
    observed = features.kills_per_round
    expected = _expected_performance_for_hours(hours)
    gap = observed - expected
    z = gap / max(baselines.KILLS_PER_ROUND.stdev, 1e-6)

    # Moins il y a d'heures, plus l'écart est parlant — mais l'échantillon de
    # manches doit rester suffisant pour que la mesure ait un sens.
    inexperience = clamp(
        1.0 - hours / baselines.HIGH_EXPERIENCE_HOURS, 0.15, 1.0
    )
    score = clamp(score_from_z(z) * (0.55 + 0.45 * inexperience))
    confidence = features.round_confidence

    return Signal(
        key="progression.performance_vs_hours",
        label="Performance rapportee a l'experience",
        category=CATEGORY,
        score=score,
        confidence=confidence,
        weight=config.weight_of("progression.performance_vs_hours"),
        explanation=(
            f"{observed:.2f} kill(s) par manche pour {hours:.0f} h de jeu, alors que "
            f"{expected:.2f} sont attendus a ce niveau d'experience. "
            "Un tel ecart s'explique aussi par un compte secondaire (smurf) : ce signal "
            "ne vaut qu'accompagne d'anomalies de visee."
            if score >= 0.25
            else (
                f"{observed:.2f} kill(s) par manche pour {hours:.0f} h — "
                f"coherent avec la courbe attendue ({expected:.2f})."
            )
        ),
        observed=observed,
        expected=expected,
        z_score=z,
        sample_size=features.total_rounds,
        metadata={"hours": round(hours, 1), "smurf_ambiguity": True},
    )


def _kills_per_hour(features: PlayerFeatures, config: EngineConfig) -> Signal:
    return build_signal(
        key="progression.kills_per_hour",
        label="Rythme d'eliminations",
        category=CATEGORY,
        baseline=baselines.KILLS_PER_HOUR,
        observed=features.kills_per_hour,
        confidence=min(
            features.kill_confidence,
            sample_confidence(features.hours_played, 2_000, 20),
        ),
        sample_size=features.total_kills,
        config=config,
        explanation_high=(
            f"{features.kills_per_hour:.0f} eliminations par heure contre "
            f"{baselines.KILLS_PER_HOUR.mean:.0f} en moyenne — cadence tres soutenue."
        ),
        explanation_normal=(
            f"{features.kills_per_hour:.0f} eliminations par heure — cadence usuelle."
        ),
    )


def _kd(features: PlayerFeatures, config: EngineConfig) -> Signal:
    return build_signal(
        key="progression.kd",
        label="Ratio eliminations / morts",
        category=CATEGORY,
        baseline=baselines.KD_RATIO,
        observed=features.kd_ratio,
        confidence=features.kill_confidence,
        sample_size=features.total_kills,
        config=config,
        explanation_high=(
            f"K/D de {features.kd_ratio:.2f} contre {baselines.KD_RATIO.mean:.2f} en "
            "moyenne, maintenu sur toute la duree de vie du compte."
        ),
        explanation_normal=f"K/D de {features.kd_ratio:.2f} — dans la norme.",
    )


def _round_win_rate(features: PlayerFeatures, config: EngineConfig) -> Signal:
    return build_signal(
        key="progression.round_win_rate",
        label="Taux de manches gagnees",
        category=CATEGORY,
        baseline=baselines.ROUND_WIN_RATE,
        observed=features.round_win_rate,
        confidence=features.round_confidence,
        sample_size=features.total_rounds,
        config=config,
        explanation_high=(
            f"{features.round_win_rate * 100:.1f} % de manches gagnees. Le matchmaking "
            "ramene normalement ce taux vers 50 % : un ecart durable signale un "
            "avantage systematique."
        ),
        explanation_normal=(
            f"{features.round_win_rate * 100:.1f} % de manches gagnees — "
            "equilibrage normal du matchmaking."
        ),
    )


def _mvp_rate(features: PlayerFeatures, config: EngineConfig) -> Signal:
    return build_signal(
        key="progression.mvp_rate",
        label="Taux de MVP",
        category=CATEGORY,
        baseline=baselines.MVP_RATE,
        observed=features.mvp_rate,
        confidence=features.round_confidence,
        sample_size=features.total_rounds,
        config=config,
        explanation_high=(
            f"{features.mvp_rate * 100:.1f} % des manches remportees avec le titre de MVP "
            f"(reference {baselines.MVP_RATE.mean * 100:.1f} %) : domination tres marquee "
            "au sein de l'equipe."
        ),
        explanation_normal=f"{features.mvp_rate * 100:.1f} % de MVP — repartition normale.",
    )
