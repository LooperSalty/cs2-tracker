"""Détecteurs de visée : taux de HS, précision, économie de balles.

Ce sont les marqueurs les plus discriminants accessibles hors du client de jeu.
Un aimbot déforme mécaniquement le rapport impacts/kills et la précision ; un
triggerbot gonfle le taux de HS sans toucher au reste.
"""

from __future__ import annotations

from cs2tracker.anticheat import baselines
from cs2tracker.anticheat.detectors.common import build_signal, pct
from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal, SignalCategory, neutral_signal
from cs2tracker.anticheat.weights import EngineConfig

CATEGORY = SignalCategory.AIM


def detect(features: PlayerFeatures, config: EngineConfig) -> tuple[Signal, ...]:
    if not features.has_stats:
        return (
            neutral_signal(
                "aim.headshot_rate",
                "Analyse de visee",
                CATEGORY,
                "Statistiques a vie indisponibles (profil prive ou aucune partie).",
            ),
        )

    signals: list[Signal] = [
        _headshot_rate(features, config),
        _accuracy(features, config),
        _hits_per_kill(features, config),
        _shots_per_kill(features, config),
        _damage_per_kill(features, config),
    ]
    return tuple(signals)


def _headshot_rate(features: PlayerFeatures, config: EngineConfig) -> Signal:
    observed = features.headshot_rate
    return build_signal(
        key="aim.headshot_rate",
        label="Taux de tirs a la tete",
        category=CATEGORY,
        baseline=baselines.HEADSHOT_RATE,
        observed=observed,
        confidence=features.kill_confidence,
        sample_size=features.total_kills,
        config=config,
        explanation_high=(
            f"{pct(observed)} des eliminations sont des headshots, contre "
            f"{pct(baselines.HEADSHOT_RATE.mean)} en moyenne. Un ecart soutenu sur "
            f"{features.total_kills} kills est le marqueur classique d'une aide a la visee."
        ),
        explanation_normal=(
            f"{pct(observed)} de headshots — dans la plage attendue "
            f"(reference {pct(baselines.HEADSHOT_RATE.mean)})."
        ),
    )


def _accuracy(features: PlayerFeatures, config: EngineConfig) -> Signal:
    observed = features.accuracy
    return build_signal(
        key="aim.accuracy",
        label="Precision globale",
        category=CATEGORY,
        baseline=baselines.ACCURACY,
        observed=observed,
        confidence=features.shot_confidence,
        sample_size=features.total_shots,
        config=config,
        explanation_high=(
            f"{pct(observed)} des balles touchent, contre {pct(baselines.ACCURACY.mean)} "
            f"en moyenne sur {features.total_shots:,} tirs. Une precision aussi elevee "
            "resiste mal au recul des armes automatiques."
        ).replace(",", " "),
        explanation_normal=(
            f"Precision de {pct(observed)}, coherente avec la population "
            f"(reference {pct(baselines.ACCURACY.mean)})."
        ),
    )


def _hits_per_kill(features: PlayerFeatures, config: EngineConfig) -> Signal:
    observed = features.hits_per_kill
    return build_signal(
        key="aim.hits_per_kill",
        label="Impacts par elimination",
        category=CATEGORY,
        baseline=baselines.HITS_PER_KILL,
        observed=observed,
        confidence=min(features.kill_confidence, features.shot_confidence),
        sample_size=features.total_kills,
        config=config,
        inverted=True,
        explanation_high=(
            f"{observed:.2f} impact(s) suffisent en moyenne pour tuer, contre "
            f"{baselines.HITS_PER_KILL.mean:.2f} attendus. Cela traduit une "
            "concentration anormale des tirs sur les zones letales."
        ),
        explanation_normal=(
            f"{observed:.2f} impacts par kill — repartition des degats normale."
        ),
    )


def _shots_per_kill(features: PlayerFeatures, config: EngineConfig) -> Signal:
    observed = features.shots_per_kill
    return build_signal(
        key="aim.shots_per_kill",
        label="Balles tirees par elimination",
        category=CATEGORY,
        baseline=baselines.SHOTS_PER_KILL,
        observed=observed,
        confidence=features.shot_confidence,
        sample_size=features.total_shots,
        config=config,
        inverted=True,
        explanation_high=(
            f"{observed:.1f} balles par kill contre {baselines.SHOTS_PER_KILL.mean:.1f} "
            "attendues : economie de munitions incompatible avec des duels disputes."
        ),
        explanation_normal=f"{observed:.1f} balles par kill — consommation habituelle.",
    )


def _damage_per_kill(features: PlayerFeatures, config: EngineConfig) -> Signal:
    observed = features.damage_per_kill
    return build_signal(
        key="aim.damage_per_kill",
        label="Degats infliges par elimination",
        category=CATEGORY,
        baseline=baselines.DAMAGE_PER_KILL,
        observed=observed,
        confidence=features.kill_confidence,
        sample_size=features.total_kills,
        config=config,
        inverted=True,
        explanation_high=(
            f"{observed:.0f} degats par kill contre {baselines.DAMAGE_PER_KILL.mean:.0f} "
            "attendus : tres peu de degats « perdus » sur des adversaires survivants."
        ),
        explanation_normal=f"{observed:.0f} degats par kill — ratio classique.",
    )
