"""Unité élémentaire de l'analyse : le *signal*.

Un signal porte trois grandeurs distinctes, jamais confondues :
  - ``score``      : intensité de l'anomalie (0 = normal, 1 = extrême) ;
  - ``confidence`` : fiabilité de la mesure (taille d'échantillon, données
    disponibles) — un signal fort sur 3 kills ne pèse presque rien ;
  - ``weight``     : importance intrinsèque du détecteur dans le verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from cs2tracker.core.utils import clamp


class SignalCategory(str, Enum):
    ACCOUNT = "compte"
    AIM = "visee"
    WEAPON = "armes"
    PROGRESSION = "progression"
    LIVE = "temps_reel"
    CONSISTENCY = "regularite"
    BAN = "sanctions"


class Severity(str, Enum):
    INFO = "info"
    LOW = "faible"
    MEDIUM = "moyen"
    HIGH = "eleve"
    CRITICAL = "critique"


def severity_for(score: float, confidence: float) -> Severity:
    """Gravité effective = intensité pondérée par la fiabilité."""
    effective = score * confidence
    if effective >= 0.75:
        return Severity.CRITICAL
    if effective >= 0.55:
        return Severity.HIGH
    if effective >= 0.32:
        return Severity.MEDIUM
    if effective >= 0.12:
        return Severity.LOW
    return Severity.INFO


@dataclass(frozen=True, slots=True)
class Signal:
    """Résultat immuable d'un détecteur."""

    key: str
    label: str
    category: SignalCategory
    score: float
    confidence: float
    weight: float
    explanation: str
    observed: float | None = None
    expected: float | None = None
    z_score: float | None = None
    sample_size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Les dataclasses gelées exigent object.__setattr__ pour normaliser.
        object.__setattr__(self, "score", clamp(self.score))
        object.__setattr__(self, "confidence", clamp(self.confidence))
        object.__setattr__(self, "weight", max(0.0, self.weight))

    @property
    def severity(self) -> Severity:
        return severity_for(self.score, self.confidence)

    @property
    def effective_weight(self) -> float:
        return self.weight * self.confidence

    @property
    def contribution(self) -> float:
        return self.score * self.effective_weight

    @property
    def is_actionable(self) -> bool:
        return self.severity in {Severity.HIGH, Severity.CRITICAL}

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "category": self.category.value,
            "score": round(self.score, 4),
            "confidence": round(self.confidence, 3),
            "weight": round(self.weight, 3),
            "severity": self.severity.value,
            "explanation": self.explanation,
            "observed": round(self.observed, 4) if self.observed is not None else None,
            "expected": round(self.expected, 4) if self.expected is not None else None,
            "z_score": round(self.z_score, 2) if self.z_score is not None else None,
            "sample_size": self.sample_size,
            "contribution": round(self.contribution, 4),
            "metadata": dict(self.metadata),
        }


def neutral_signal(
    key: str,
    label: str,
    category: SignalCategory,
    reason: str,
    weight: float = 0.0,
) -> Signal:
    """Signal explicitement non concluant (données manquantes)."""
    return Signal(
        key=key,
        label=label,
        category=category,
        score=0.0,
        confidence=0.0,
        weight=weight,
        explanation=reason,
    )


def top_signals(signals: Sequence[Signal], limit: int = 5) -> tuple[Signal, ...]:
    return tuple(sorted(signals, key=lambda s: s.contribution, reverse=True)[:limit])
