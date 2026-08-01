"""Briques partagées par les détecteurs.

Toutes les conversions « écart statistique → score de suspicion » passent par
ici, ce qui garantit un comportement homogène et une calibration unique.
"""

from __future__ import annotations

from cs2tracker.anticheat.baselines import Baseline
from cs2tracker.anticheat.signals import Signal, SignalCategory
from cs2tracker.anticheat.weights import EngineConfig
from cs2tracker.core.utils import clamp, logistic

#: Un z-score de +2 correspond à ~0.5 de suspicion, +4 à ~0.9.
_LOGISTIC_MIDPOINT = 2.0
_LOGISTIC_STEEPNESS = 1.05


def score_from_z(z: float) -> float:
    """Convertit un z-score positif en suspicion 0..1 (sigmoïde calibrée)."""
    if z <= 0:
        return 0.0
    return clamp(
        (logistic(z, _LOGISTIC_MIDPOINT, _LOGISTIC_STEEPNESS) - logistic(0.0, _LOGISTIC_MIDPOINT, _LOGISTIC_STEEPNESS))
        / (1.0 - logistic(0.0, _LOGISTIC_MIDPOINT, _LOGISTIC_STEEPNESS))
    )


def ceiling_bonus(value: float, ceiling: float) -> float:
    """Bonus appliqué quand une valeur dépasse le plafond « physique »."""
    if ceiling == float("inf") or value <= ceiling:
        return 0.0
    return clamp((value - ceiling) / max(ceiling * 0.25, 1e-6), 0.0, 1.0)


def floor_bonus(value: float, floor: float) -> float:
    """Équivalent du bonus plafond pour les métriques inversées."""
    if floor == float("-inf") or value >= floor:
        return 0.0
    return clamp((floor - value) / max(abs(floor) * 0.5, 1e-6), 0.0, 1.0)


def build_signal(
    *,
    key: str,
    label: str,
    category: SignalCategory,
    baseline: Baseline,
    observed: float,
    confidence: float,
    sample_size: int,
    config: EngineConfig,
    inverted: bool = False,
    explanation_high: str,
    explanation_normal: str,
) -> Signal:
    """Crée un signal à partir d'un écart à une distribution de référence.

    ``inverted=True`` désigne une métrique où c'est une valeur **basse** qui
    interpelle (régularité mécanique, dispersion nulle…).
    """
    z = baseline.z(observed)
    if inverted:
        z = -z
        extra = floor_bonus(observed, baseline.hard_floor)
    else:
        extra = ceiling_bonus(observed, baseline.hard_ceiling)

    score = clamp(score_from_z(z) + extra * 0.35)
    explanation = explanation_high if score >= 0.25 else explanation_normal

    return Signal(
        key=key,
        label=label,
        category=category,
        score=score,
        confidence=confidence,
        weight=config.weight_of(key),
        explanation=explanation,
        observed=observed,
        expected=baseline.mean,
        z_score=z,
        sample_size=sample_size,
        metadata={
            "baseline_stdev": baseline.stdev,
            "inverted": inverted,
            "exceeds_hard_limit": extra > 0,
        },
    )


def pct(value: float) -> str:
    return f"{value * 100:.1f} %"
