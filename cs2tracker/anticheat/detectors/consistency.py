"""Détecteurs de cohérence interne.

Deux angles complémentaires :
  1. **Régularité intra-partie** : les dégâts d'un humain varient beaucoup d'une
     manche à l'autre. Une variance trop faible trahit un plancher de
     performance artificiel.
  2. **Cohérence historique / temps réel** : un joueur dont les statistiques à
     vie sont médiocres mais qui domine en direct vient soit de progresser, soit
     d'activer quelque chose.
"""

from __future__ import annotations

from cs2tracker.anticheat import baselines
from cs2tracker.anticheat.detectors.common import build_signal, score_from_z
from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal, SignalCategory, neutral_signal
from cs2tracker.anticheat.weights import EngineConfig
from cs2tracker.core.utils import clamp, sample_confidence

CATEGORY = SignalCategory.CONSISTENCY

_MIN_ROUNDS_FOR_VARIANCE = 8


def detect(features: PlayerFeatures, config: EngineConfig) -> tuple[Signal, ...]:
    return (
        _adr_variability(features, config),
        _stats_versus_live(features, config),
    )


def _adr_variability(features: PlayerFeatures, config: EngineConfig) -> Signal:
    if not features.has_live or features.live_rounds < _MIN_ROUNDS_FOR_VARIANCE:
        return neutral_signal(
            "consistency.adr_variability",
            "Irregularite des performances",
            CATEGORY,
            f"Moins de {_MIN_ROUNDS_FOR_VARIANCE} manches observees en direct.",
            weight=config.weight_of("consistency.adr_variability"),
        )

    return build_signal(
        key="consistency.adr_variability",
        label="Irregularite des performances",
        category=CATEGORY,
        baseline=baselines.ADR_VARIABILITY,
        observed=features.live_adr_variability,
        confidence=sample_confidence(features.live_rounds, 40, _MIN_ROUNDS_FOR_VARIANCE),
        sample_size=features.live_rounds,
        config=config,
        inverted=True,
        explanation_high=(
            f"Les degats par manche ne varient que de "
            f"{features.live_adr_variability:.2f} (coefficient de variation), contre "
            f"{baselines.ADR_VARIABILITY.mean:.2f} attendus. Les manches faibles, "
            "normales chez un humain, ont pratiquement disparu."
        ),
        explanation_normal=(
            f"Variabilite des degats de {features.live_adr_variability:.2f} — "
            "alternance de bonnes et de mauvaises manches typique."
        ),
    )


def _stats_versus_live(features: PlayerFeatures, config: EngineConfig) -> Signal:
    """Écart entre le niveau historique et le niveau observé maintenant."""
    if not (features.has_live and features.has_stats):
        return neutral_signal(
            "consistency.stats_vs_live",
            "Coherence historique / temps reel",
            CATEGORY,
            "Necessite a la fois des statistiques a vie et des manches observees.",
            weight=config.weight_of("consistency.stats_vs_live"),
        )
    if features.live_rounds < _MIN_ROUNDS_FOR_VARIANCE:
        return neutral_signal(
            "consistency.stats_vs_live",
            "Coherence historique / temps reel",
            CATEGORY,
            f"Moins de {_MIN_ROUNDS_FOR_VARIANCE} manches observees.",
            weight=config.weight_of("consistency.stats_vs_live"),
        )

    # On compare les kills par manche à vie et en direct, ainsi que les taux de HS.
    kpr_gap = features.live_kills_per_round - features.kills_per_round
    hs_gap = features.live_headshot_rate - features.headshot_rate

    kpr_z = kpr_gap / max(baselines.KILLS_PER_ROUND.stdev, 1e-6)
    hs_z = hs_gap / max(baselines.HEADSHOT_RATE.stdev, 1e-6)
    combined_z = max(kpr_z, hs_z)

    score = clamp(score_from_z(combined_z) * 0.9)
    confidence = min(
        sample_confidence(features.live_rounds, 40, _MIN_ROUNDS_FOR_VARIANCE),
        features.round_confidence,
    )

    return Signal(
        key="consistency.stats_vs_live",
        label="Coherence historique / temps reel",
        category=CATEGORY,
        score=score,
        confidence=confidence,
        weight=config.weight_of("consistency.stats_vs_live"),
        explanation=(
            f"Niveau actuel nettement superieur a l'historique du compte : "
            f"{features.live_kills_per_round:.2f} kill/manche en direct contre "
            f"{features.kills_per_round:.2f} a vie, HS a "
            f"{features.live_headshot_rate * 100:.0f} % contre "
            f"{features.headshot_rate * 100:.0f} %. Une rupture aussi nette merite "
            "verification — elle peut aussi refleter un adversaire plus faible."
            if score >= 0.25
            else (
                "Performance actuelle alignee sur l'historique du compte "
                f"({features.live_kills_per_round:.2f} vs {features.kills_per_round:.2f} "
                "kill/manche)."
            )
        ),
        observed=features.live_kills_per_round,
        expected=features.kills_per_round,
        z_score=combined_z,
        sample_size=features.live_rounds,
        metadata={
            "kpr_gap": round(kpr_gap, 3),
            "headshot_gap": round(hs_gap, 3),
        },
    )
