"""Analyse par arme et par catégorie.

Trois idées :
  1. la précision au *spray* (armes automatiques) est la plus difficile à
     truquer manuellement — un score élevé y est très discriminant ;
  2. le taux de HS doit être comparé par catégorie, un HS à l'AWP n'ayant pas
     la même signification qu'à l'AK-47 ;
  3. un joueur légitime a un profil **hétérogène** : très bon à une arme, moyen
     à une autre. Une performance uniformément excellente est atypique.
"""

from __future__ import annotations

from cs2tracker.anticheat import baselines
from cs2tracker.anticheat.detectors.common import build_signal, pct, score_from_z
from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal, SignalCategory, neutral_signal
from cs2tracker.anticheat.weights import EngineConfig
from cs2tracker.core.utils import clamp, mean, sample_confidence, stdev

CATEGORY = SignalCategory.WEAPON

#: Nombre minimal de catégories renseignées pour juger de l'uniformité.
_MIN_CATEGORIES = 3
#: Tirs minimaux pour que la précision au spray soit exploitable.
_MIN_SPRAY_SHOTS = 5_000


def detect(features: PlayerFeatures, config: EngineConfig) -> tuple[Signal, ...]:
    if not features.has_stats or not features.category_aim:
        return (
            neutral_signal(
                "weapon.spray_accuracy",
                "Analyse par arme",
                CATEGORY,
                "Statistiques par arme indisponibles.",
            ),
        )
    return (
        _spray_accuracy(features, config),
        _category_accuracy_profile(features, config),
        _uniformity(features, config),
    )


def _spray_accuracy(features: PlayerFeatures, config: EngineConfig) -> Signal:
    if features.spray_shots < _MIN_SPRAY_SHOTS:
        return neutral_signal(
            "weapon.spray_accuracy",
            "Precision aux armes automatiques",
            CATEGORY,
            f"Seulement {features.spray_shots} tirs recenses aux armes automatiques.",
            weight=config.weight_of("weapon.spray_accuracy"),
        )

    observed = features.spray_accuracy
    confidence = sample_confidence(features.spray_shots, 150_000, _MIN_SPRAY_SHOTS)
    return build_signal(
        key="weapon.spray_accuracy",
        label="Precision aux armes automatiques",
        category=CATEGORY,
        baseline=baselines.ACCURACY,
        observed=observed,
        confidence=confidence,
        sample_size=features.spray_shots,
        config=config,
        explanation_high=(
            f"{pct(observed)} de precision sur {features.spray_shots} tirs d'armes "
            "automatiques. Le recul de ces armes plafonne naturellement ce taux : "
            "un score aussi haut suppose une compensation non manuelle."
        ),
        explanation_normal=(
            f"{pct(observed)} de precision au spray — compatible avec le recul des armes."
        ),
    )


def _category_accuracy_profile(
    features: PlayerFeatures, config: EngineConfig
) -> Signal:
    """Compare chaque catégorie à sa propre référence et retient la pire dérive."""
    worst_z = 0.0
    worst_category = ""
    worst_value = 0.0
    total_shots = 0
    details: dict[str, float] = {}

    for category, aim in features.category_aim.items():
        reference = baselines.WEAPON_CATEGORY_BASELINES.get(category)
        if reference is None or not aim.has_sample:
            continue
        total_shots += aim.shots
        z = (aim.accuracy - reference.accuracy_mean) / max(reference.accuracy_stdev, 1e-6)
        details[category] = round(aim.accuracy, 4)
        if z > worst_z:
            worst_z, worst_category, worst_value = z, category, aim.accuracy

    if not worst_category:
        return neutral_signal(
            "weapon.category_headshots",
            "Profil de precision par categorie",
            CATEGORY,
            "Echantillon insuffisant par categorie d'arme.",
            weight=config.weight_of("weapon.category_headshots"),
        )

    confidence = sample_confidence(total_shots, 200_000, 10_000)
    score = score_from_z(worst_z)
    return Signal(
        key="weapon.category_headshots",
        label="Profil de precision par categorie",
        category=CATEGORY,
        score=score,
        confidence=confidence,
        weight=config.weight_of("weapon.category_headshots"),
        explanation=(
            f"Categorie la plus atypique : {worst_category} a {pct(worst_value)} de "
            f"precision (z = {worst_z:+.1f}). Chaque categorie est comparee a sa propre "
            "reference, un sniper n'etant pas jugeable comme un fusil d'assaut."
            if score >= 0.25
            else "Aucune categorie d'arme ne se detache anormalement."
        ),
        observed=worst_value,
        z_score=worst_z,
        sample_size=total_shots,
        metadata={"per_category_accuracy": details},
    )


def _uniformity(features: PlayerFeatures, config: EngineConfig) -> Signal:
    """Un joueur humain est irrégulier d'une arme à l'autre."""
    usable = [
        aim for aim in features.category_aim.values()
        if aim.has_sample and aim.category in baselines.WEAPON_CATEGORY_BASELINES
    ]
    if len(usable) < _MIN_CATEGORIES:
        return neutral_signal(
            "weapon.uniformity",
            "Homogeneite entre armes",
            CATEGORY,
            "Pas assez de categories d'armes renseignees.",
            weight=config.weight_of("weapon.uniformity"),
        )

    z_scores = []
    for aim in usable:
        reference = baselines.WEAPON_CATEGORY_BASELINES[aim.category]
        z_scores.append(
            (aim.accuracy - reference.accuracy_mean) / max(reference.accuracy_stdev, 1e-6)
        )

    average_z = mean(z_scores)
    dispersion = stdev(z_scores)
    total_shots = sum(aim.shots for aim in usable)

    # Excellence *uniforme* : moyenne haute ET dispersion faible.
    excellence = clamp((average_z - 1.0) / 2.5)
    homogeneity = clamp(1.0 - dispersion / 1.5)
    score = clamp(excellence * homogeneity)

    return Signal(
        key="weapon.uniformity",
        label="Homogeneite entre armes",
        category=CATEGORY,
        score=score,
        confidence=sample_confidence(total_shots, 250_000, 20_000),
        weight=config.weight_of("weapon.uniformity"),
        explanation=(
            f"Performance elevee et tres homogene sur {len(usable)} categories d'armes "
            f"(z moyen {average_z:+.1f}, dispersion {dispersion:.2f}). Les joueurs "
            "legitimes presentent normalement des forces et des faiblesses marquees."
            if score >= 0.25
            else (
                f"Profil contraste entre armes (dispersion {dispersion:.2f}) — "
                "signature humaine habituelle."
            )
        ),
        observed=average_z,
        sample_size=total_shots,
        metadata={
            "categories": len(usable),
            "z_dispersion": round(dispersion, 3),
        },
    )
