"""Signaux liés au compte Steam lui-même.

Ces indicateurs sont **faibles individuellement** : un compte neuf et privé est
parfaitement légitime. Ils ne servent qu'à contextualiser des anomalies de jeu,
d'où des poids volontairement modestes.
"""

from __future__ import annotations

from cs2tracker.anticheat import baselines
from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal, SignalCategory
from cs2tracker.anticheat.weights import EngineConfig
from cs2tracker.core.utils import clamp

CATEGORY = SignalCategory.ACCOUNT

#: Un compte avec moins de jeux que ce seuil est « mono-usage ».
_MINIMAL_LIBRARY = 3
#: Nombre d'amis en dessous duquel le compte paraît isolé.
_LOW_FRIENDS = 5


def detect(features: PlayerFeatures, config: EngineConfig) -> tuple[Signal, ...]:
    return (
        _age(features, config),
        _privacy(features, config),
        _library(features, config),
        _social(features, config),
        _smurf_profile(features, config),
    )


def _age(features: PlayerFeatures, config: EngineConfig) -> Signal:
    days = features.account_age_days
    if days <= 0:
        return Signal(
            key="account.age",
            label="Anciennete du compte",
            category=CATEGORY,
            score=0.20,
            confidence=0.3,
            weight=config.weight_of("account.age"),
            explanation="Date de creation non communiquee (profil restreint).",
        )
    score = clamp(1.0 - days / (baselines.YOUNG_ACCOUNT_DAYS * 2.0))
    return Signal(
        key="account.age",
        label="Anciennete du compte",
        category=CATEGORY,
        score=score,
        confidence=1.0,
        weight=config.weight_of("account.age"),
        explanation=(
            f"Compte cree il y a {days:.0f} jours. Les comptes de contournement de ban "
            "sont recents par construction — mais un nouveau joueur l'est aussi."
            if score >= 0.25
            else f"Compte ancien ({days / 365.25:.1f} an(s)) : pas un compte jetable."
        ),
        observed=days,
        expected=float(baselines.YOUNG_ACCOUNT_DAYS),
        sample_size=1,
    )


def _privacy(features: PlayerFeatures, config: EngineConfig) -> Signal:
    is_private = not features.profile_public
    return Signal(
        key="account.privacy",
        label="Visibilite du profil",
        category=CATEGORY,
        score=0.45 if is_private else 0.0,
        confidence=0.6 if is_private else 1.0,
        weight=config.weight_of("account.privacy"),
        explanation=(
            "Profil prive : les statistiques de jeu sont inaccessibles, ce qui limite "
            "fortement l'analyse. La confidentialite est un choix legitime et frequent."
            if is_private
            else "Profil public : analyse complete possible."
        ),
        sample_size=1,
        metadata={"weak_signal": True},
    )


def _library(features: PlayerFeatures, config: EngineConfig) -> Signal:
    games = features.games_owned
    if games <= 0:
        return Signal(
            key="account.library",
            label="Bibliotheque Steam",
            category=CATEGORY,
            score=0.15,
            confidence=0.25,
            weight=config.weight_of("account.library"),
            explanation="Bibliotheque non consultable.",
            sample_size=0,
        )
    score = clamp((_MINIMAL_LIBRARY + 1 - games) / _MINIMAL_LIBRARY) if games <= _MINIMAL_LIBRARY else 0.0
    return Signal(
        key="account.library",
        label="Bibliotheque Steam",
        category=CATEGORY,
        score=score,
        confidence=0.8,
        weight=config.weight_of("account.library"),
        explanation=(
            f"Seulement {games} jeu(x) possede(s) : profil de compte cree pour un usage "
            "unique."
            if score > 0
            else f"{games} jeux possedes — compte utilise normalement."
        ),
        observed=float(games),
        expected=baselines.GAMES_OWNED.mean,
        sample_size=1,
    )


def _social(features: PlayerFeatures, config: EngineConfig) -> Signal:
    friends = features.friends_count
    level = features.steam_level
    isolation = clamp((_LOW_FRIENDS - friends) / _LOW_FRIENDS) if friends < _LOW_FRIENDS else 0.0
    low_level = clamp((3 - level) / 3.0) if level < 3 else 0.0
    score = clamp(max(isolation, low_level) * 0.8)
    return Signal(
        key="account.social",
        label="Empreinte sociale",
        category=CATEGORY,
        score=score,
        confidence=0.5,
        weight=config.weight_of("account.social"),
        explanation=(
            f"{friends} ami(s), niveau Steam {level} : empreinte sociale tres faible."
            if score >= 0.25
            else f"{friends} ami(s), niveau Steam {level} — activite Steam normale."
        ),
        observed=float(friends),
        expected=baselines.FRIENDS_COUNT.mean,
        sample_size=1,
        metadata={"weak_signal": True, "steam_level": level},
    )


def _smurf_profile(features: PlayerFeatures, config: EngineConfig) -> Signal:
    """Combinaison « compte jeune + peu d'heures + performance élevée ».

    Cette signature est **partagée** par les smurfs et par les tricheurs : elle
    est signalée comme telle, jamais présentée comme une preuve.
    """
    young = clamp(
        1.0 - features.account_age_days / (baselines.YOUNG_ACCOUNT_DAYS * 3.0)
    ) if features.account_age_days > 0 else 0.4
    inexperienced = clamp(
        1.0 - features.hours_played / baselines.LOW_EXPERIENCE_HOURS
    )
    performing = clamp(
        (features.kills_per_round - baselines.KILLS_PER_ROUND.mean)
        / (baselines.KILLS_PER_ROUND.stdev * 2.5)
    )
    score = clamp(young * 0.35 + inexperienced * 0.30 + performing * 0.35)
    confidence = 0.7 if features.has_stats else 0.25

    return Signal(
        key="account.smurf_profile",
        label="Profil compte secondaire",
        category=CATEGORY,
        score=score,
        confidence=confidence,
        weight=config.weight_of("account.smurf_profile"),
        explanation=(
            f"Compte recent ({features.account_age_days:.0f} j), peu d'heures "
            f"({features.hours_played:.0f} h) et niveau de jeu eleve "
            f"({features.kills_per_round:.2f} kill/manche). Signature typique d'un smurf "
            "**autant** que d'un tricheur : a ne jamais interpreter isolement."
            if score >= 0.3
            else "Profil de compte coherent avec le niveau de jeu observe."
        ),
        observed=features.hours_played,
        sample_size=features.total_rounds,
        metadata={"ambiguous_with_smurf": True},
    )
