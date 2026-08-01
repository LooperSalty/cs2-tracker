"""Moteur d'agrégation : transforme des signaux en score et en verdict.

Principes de conception, volontairement conservateurs :

1. **Aucune preuve n'est produite.** La sortie est un *score de suspicion*
   probabiliste, destiné à orienter un signalement humain — jamais à conclure.
2. **La confiance module tout.** Un signal fort mesuré sur un échantillon
   minuscule ne peut pas faire monter le score.
3. **La corroboration prime sur l'intensité.** Un seul indicateur extrême pèse
   moins que trois indicateurs indépendants concordants, car les faux positifs
   isolés sont fréquents (smurf, joueur pro, style de jeu atypique).
4. **Les sanctions Valve sont factuelles** et court-circuitent le modèle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from cs2tracker.anticheat.detectors import ALL_DETECTORS, bans as bans_detector
from cs2tracker.anticheat.features import PlayerFeatures, build_features
from cs2tracker.anticheat.signals import Severity, Signal, SignalCategory, top_signals
from cs2tracker.anticheat.weights import DEFAULT_CONFIG, EngineConfig
from cs2tracker.constants import SUSPICION_MAX, VERDICT_BANDS
from cs2tracker.core.models import PlayerProfile
from cs2tracker.core.utils import clamp, now_iso, safe_div
from cs2tracker.gsi.tracker import LivePlayerMetrics

#: Avertissement systématiquement joint à chaque rapport.
DISCLAIMER = (
    "Ce score est une estimation statistique produite a partir de donnees publiques "
    "Steam et du Game State Integration officiel de CS2. Il ne constitue ni une preuve "
    "ni une accusation : seul Valve dispose des elements (memoire client, telemetrie "
    "serveur) permettant de conclure. Les faux positifs connus incluent les comptes "
    "secondaires (smurfs), les joueurs de niveau competitif et les styles de jeu "
    "atypiques. En cas de doute, utilise le signalement en jeu."
)


@dataclass(frozen=True, slots=True)
class CategoryScore:
    category: str
    score: float
    confidence: float
    signal_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "score": round(self.score * 100, 1),
            "confidence": round(self.confidence, 3),
            "signals": self.signal_count,
        }


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Rapport d'analyse complet et immuable."""

    steamid: str
    name: str
    suspicion_score: float
    verdict: str
    verdict_label: str
    global_confidence: float
    signals: tuple[Signal, ...]
    categories: tuple[CategoryScore, ...]
    highlights: tuple[Signal, ...]
    has_confirmed_ban: bool
    data_sources: dict[str, bool]
    features: PlayerFeatures
    analysed_at: str = field(default_factory=now_iso)

    @property
    def is_inconclusive(self) -> bool:
        return self.verdict == "INDETERMINE"

    def as_dict(self, *, include_features: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "steamid": self.steamid,
            "name": self.name,
            "suspicion_score": round(self.suspicion_score, 1),
            "verdict": self.verdict,
            "verdict_label": self.verdict_label,
            "global_confidence": round(self.global_confidence, 3),
            "has_confirmed_ban": self.has_confirmed_ban,
            "analysed_at": self.analysed_at,
            "data_sources": dict(self.data_sources),
            "categories": [c.as_dict() for c in self.categories],
            "highlights": [s.as_dict() for s in self.highlights],
            "signals": [s.as_dict() for s in self.signals],
            "disclaimer": DISCLAIMER,
        }
        if include_features:
            payload["features"] = self.features.as_dict()
        return payload


def _verdict_for(score: float, confidence: float, config: EngineConfig) -> tuple[str, str]:
    if confidence < config.min_global_confidence:
        return ("INDETERMINE", "Donnees insuffisantes pour se prononcer")
    for threshold, name, label in VERDICT_BANDS:
        if score >= threshold:
            return (name, label)
    return ("CLEAN", "Rien d'anormal detecte")


def _category_scores(signals: Sequence[Signal]) -> tuple[CategoryScore, ...]:
    buckets: dict[SignalCategory, list[Signal]] = {}
    for signal in signals:
        buckets.setdefault(signal.category, []).append(signal)

    results: list[CategoryScore] = []
    for category, group in buckets.items():
        total_weight = sum(s.effective_weight for s in group)
        score = safe_div(sum(s.contribution for s in group), total_weight)
        confidence = safe_div(
            sum(s.confidence * s.weight for s in group),
            sum(s.weight for s in group),
        )
        results.append(
            CategoryScore(
                category=category.value,
                score=clamp(score),
                confidence=clamp(confidence),
                signal_count=len(group),
            )
        )
    return tuple(sorted(results, key=lambda c: c.score, reverse=True))


#: Part de confiance apportée par chaque source de données. Une analyse sans
#: statistiques de jeu ne peut pas prétendre à une confiance élevée, même si
#: chaque signal disponible (âge du compte, sanctions…) est en soi certain.
_SOURCE_COVERAGE_WEIGHTS: dict[str, float] = {
    "lifetime_stats": 0.55,
    "live_gsi": 0.25,
    "ban_records": 0.20,
}


def _coverage_factor(features: PlayerFeatures) -> float:
    """Proportion des sources d'analyse réellement disponibles."""
    available = {
        "lifetime_stats": features.has_stats,
        "live_gsi": features.has_live,
        # Les sanctions Valve sont toujours consultables, meme sur profil prive.
        "ban_records": True,
    }
    return sum(
        weight for source, weight in _SOURCE_COVERAGE_WEIGHTS.items() if available[source]
    )


def _corroboration_factor(signals: Sequence[Signal], config: EngineConfig) -> float:
    """Bonus si plusieurs *catégories* différentes concordent.

    Trois signaux forts issus d'une même famille (visée) peuvent partager la même
    cause ; trois signaux forts issus de familles distinctes sont bien plus
    difficiles à expliquer autrement.
    """
    strong_categories = {
        s.category
        for s in signals
        if s.severity in {Severity.HIGH, Severity.CRITICAL}
        and s.category != SignalCategory.BAN
    }
    if len(strong_categories) < config.corroboration_threshold:
        return 1.0
    extra = len(strong_categories) - config.corroboration_threshold
    return min(config.corroboration_multiplier + 0.04 * extra, 1.35)


def analyse(
    profile: PlayerProfile,
    live: LivePlayerMetrics | None = None,
    config: EngineConfig = DEFAULT_CONFIG,
    drift: Mapping[str, Any] | None = None,
) -> AnalysisResult:
    """Exécute tous les détecteurs et agrège leurs signaux en un verdict.

    ``drift`` est le différentiel entre deux relevés de statistiques (voir
    ``SnapshotRepository.drift``) : il permet de mesurer une rupture de niveau
    récente, invisible dans les statistiques à vie.
    """
    features = build_features(profile, live, drift)

    signals: list[Signal] = []
    for _name, detector in ALL_DETECTORS:
        signals.extend(detector(features, config))

    scoring_signals = [
        s for s in signals if s.confidence >= config.min_confidence and s.weight > 0
    ]

    total_effective_weight = sum(s.effective_weight for s in scoring_signals)
    raw_score = safe_div(
        sum(s.contribution for s in scoring_signals), total_effective_weight
    )

    # Exposant > 1 : il faut plusieurs anomalies marquées pour approcher du haut
    # de l'échelle, un seul écart moyen ne suffit pas.
    shaped = clamp(raw_score) ** config.aggregation_exponent
    shaped = clamp(shaped * _corroboration_factor(scoring_signals, config))
    score = shaped * SUSPICION_MAX

    # Confiance globale : moyenne des confiances pondérée par l'importance,
    # puis rabattue par la couverture réelle des sources de données.
    total_weight = sum(s.weight for s in scoring_signals)
    signal_confidence = safe_div(
        sum(s.confidence * s.weight for s in scoring_signals), total_weight
    )
    global_confidence = clamp(signal_confidence * _coverage_factor(features))

    has_ban = bans_detector.has_confirmed_ban(features)
    if has_ban:
        score = max(score, config.confirmed_ban_floor)
        global_confidence = max(global_confidence, 0.9)
    elif (
        global_confidence >= config.min_global_confidence
        and any(s.severity is Severity.CRITICAL for s in scoring_signals)
    ):
        # Un signal extreme ne remonte le score que si l'analyse repose sur
        # des sources suffisantes ; sinon il reste un simple indicateur.
        score = max(score, config.critical_signal_floor)

    score = clamp(score, 0.0, SUSPICION_MAX)
    verdict, verdict_label = _verdict_for(score, global_confidence, config)

    return AnalysisResult(
        steamid=features.steamid,
        name=features.name,
        suspicion_score=score,
        verdict=verdict,
        verdict_label=verdict_label,
        global_confidence=global_confidence,
        signals=tuple(signals),
        categories=_category_scores(scoring_signals),
        highlights=top_signals(scoring_signals, limit=5),
        has_confirmed_ban=has_ban,
        data_sources={
            "lifetime_stats": features.has_stats,
            "live_gsi": features.has_live,
            "public_profile": features.profile_public,
            "ban_records": True,
        },
        features=features,
    )


def analyse_many(
    profiles: Sequence[PlayerProfile],
    live_metrics: dict[str, LivePlayerMetrics] | None = None,
    config: EngineConfig = DEFAULT_CONFIG,
) -> tuple[AnalysisResult, ...]:
    """Analyse un lobby entier, du plus suspect au moins suspect."""
    metrics = live_metrics or {}
    results = [
        analyse(profile, metrics.get(str(profile.identity.get("steamid64", ""))), config)
        for profile in profiles
    ]
    return tuple(sorted(results, key=lambda r: r.suspicion_score, reverse=True))
