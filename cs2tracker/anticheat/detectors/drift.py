"""Détection de rupture de niveau entre deux relevés de statistiques.

**Pourquoi ce détecteur existe.** Les statistiques à vie sont un très mauvais
révélateur de changement : un joueur avec 80 000 manches au compteur peut
doubler son taux de headshots sur ses 500 manches suivantes sans que sa moyenne
globale bouge de plus d'un point. Le tricheur occasionnel est donc invisible aux
détecteurs `aim.*`, qui mesurent l'ensemble du compte.

Le différentiel entre deux relevés isole au contraire la **seule période écoulée
entre eux**. C'est là qu'une activation récente se voit — et c'est le signal le
plus spécifique du moteur, parce qu'un smurf ou un joueur pro sont bons *depuis
le début*, pas depuis mardi.
"""

from __future__ import annotations

from typing import Any, Mapping

from cs2tracker.anticheat import baselines
from cs2tracker.anticheat.detectors.common import pct, score_from_z
from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal, SignalCategory, neutral_signal
from cs2tracker.anticheat.weights import EngineConfig
from cs2tracker.core.utils import clamp, sample_confidence

CATEGORY = SignalCategory.DRIFT

#: Manches minimales sur la période récente pour que la mesure ait un sens.
_MIN_RECENT_ROUNDS = 60
#: Manches à partir desquelles la période récente est pleinement fiable.
_FULL_RECENT_ROUNDS = 800


def detect(features: PlayerFeatures, config: EngineConfig) -> tuple[Signal, ...]:
    drift = features.drift
    if not drift:
        return (
            neutral_signal(
                "drift.headshot_rate",
                "Evolution recente",
                CATEGORY,
                (
                    "Un seul releve disponible. Consulte ce profil a nouveau plus tard "
                    "pour comparer deux periodes."
                ),
            ),
        )

    recent = drift.get("recent") or {}
    rounds = int(recent.get("rounds") or 0)
    if rounds < _MIN_RECENT_ROUNDS:
        return (
            neutral_signal(
                "drift.headshot_rate",
                "Evolution recente",
                CATEGORY,
                f"Seulement {rounds} manche(s) jouees depuis le releve precedent "
                f"({_MIN_RECENT_ROUNDS} minimum).",
            ),
        )

    confidence = sample_confidence(rounds, _FULL_RECENT_ROUNDS, _MIN_RECENT_ROUNDS)
    return (
        _drift_signal(
            key="drift.headshot_rate",
            label="Bond du taux de headshots",
            drift=drift,
            metric="headshot_rate",
            stdev=baselines.HEADSHOT_RATE.stdev,
            rounds=rounds,
            confidence=confidence,
            config=config,
            describe=lambda recent_value, before, gap: (
                f"Le taux de headshots est passe de {pct(before)} a {pct(recent_value)} "
                f"sur les {rounds} dernieres manches, soit un bond de "
                f"{gap * 100:+.1f} points. Un joueur progresse rarement aussi vite "
                "aussi tard."
            ),
            describe_normal=lambda recent_value, before, _gap: (
                f"Taux de headshots stable ({pct(before)} → {pct(recent_value)})."
            ),
        ),
        _drift_signal(
            key="drift.accuracy",
            label="Bond de la precision",
            drift=drift,
            metric="accuracy",
            stdev=baselines.ACCURACY.stdev,
            rounds=rounds,
            confidence=confidence,
            config=config,
            describe=lambda recent_value, before, gap: (
                f"La precision est passee de {pct(before)} a {pct(recent_value)} "
                f"({gap * 100:+.1f} points) sur la periode recente."
            ),
            describe_normal=lambda recent_value, before, _gap: (
                f"Precision stable ({pct(before)} → {pct(recent_value)})."
            ),
        ),
        _drift_signal(
            key="drift.kills_per_round",
            label="Bond du rendement par manche",
            drift=drift,
            metric="kills_per_round",
            stdev=baselines.KILLS_PER_ROUND.stdev,
            rounds=rounds,
            confidence=confidence,
            config=config,
            describe=lambda recent_value, before, gap: (
                f"Le rendement est passe de {before:.2f} a {recent_value:.2f} "
                f"kill(s) par manche ({gap:+.2f}) sur la periode recente."
            ),
            describe_normal=lambda recent_value, before, _gap: (
                f"Rendement stable ({before:.2f} → {recent_value:.2f} kill/manche)."
            ),
        ),
    )


def _drift_signal(
    *,
    key: str,
    label: str,
    drift: Mapping[str, Any],
    metric: str,
    stdev: float,
    rounds: int,
    confidence: float,
    config: EngineConfig,
    describe,
    describe_normal,
) -> Signal:
    recent_value = (drift.get("recent") or {}).get(metric)
    before = (drift.get("lifetime_at_start") or {}).get(metric)
    gap = (drift.get("delta") or {}).get(metric)

    if recent_value is None or before is None or gap is None:
        return neutral_signal(
            key, label, CATEGORY, "Mesure indisponible sur la periode.",
            weight=config.weight_of(key),
        )

    z = gap / max(stdev, 1e-6)
    score = clamp(score_from_z(z))
    explanation = (
        describe(recent_value, before, gap)
        if score >= 0.25
        else describe_normal(recent_value, before, gap)
    )

    return Signal(
        key=key,
        label=label,
        category=CATEGORY,
        score=score,
        confidence=confidence,
        weight=config.weight_of(key),
        explanation=explanation,
        observed=recent_value,
        expected=before,
        z_score=z,
        sample_size=rounds,
        metadata={
            "period_from": drift.get("from"),
            "period_to": drift.get("to"),
            "snapshots_used": drift.get("snapshots_used"),
            # Contrairement aux detecteurs `aim.*`, une derive ne s'explique pas
            # par un compte secondaire : un smurf est bon des le premier releve.
            "explains_away_smurf": True,
        },
    )
