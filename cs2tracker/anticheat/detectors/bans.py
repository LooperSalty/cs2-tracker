"""Détecteur de sanctions Valve (VAC, game bans, communauté, économie).

C'est le seul détecteur *factuel* : il ne fait pas d'inférence statistique, il
constate une décision déjà prise par Valve.
"""

from __future__ import annotations

from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal, SignalCategory
from cs2tracker.anticheat.weights import EngineConfig
from cs2tracker.core.utils import clamp

#: Au-delà de cette ancienneté, un ban ancien pèse nettement moins.
_BAN_DECAY_DAYS = 1_460.0  # ~4 ans


def detect(features: PlayerFeatures, config: EngineConfig) -> tuple[Signal, ...]:
    signals: list[Signal] = []

    if features.vac_bans > 0:
        signals.append(
            Signal(
                key="ban.vac",
                label="Bannissement VAC",
                category=SignalCategory.BAN,
                score=1.0,
                confidence=1.0,
                weight=config.weight_of("ban.vac"),
                explanation=(
                    f"{features.vac_bans} bannissement(s) VAC enregistre(s) sur ce compte. "
                    "Attention : VAC couvre l'ensemble des jeux Steam, pas uniquement CS2."
                ),
                observed=float(features.vac_bans),
                sample_size=1,
                metadata={"factual": True},
            )
        )

    if features.game_bans > 0:
        signals.append(
            Signal(
                key="ban.game",
                label="Bannissement editeur",
                category=SignalCategory.BAN,
                score=1.0,
                confidence=1.0,
                weight=config.weight_of("ban.game"),
                explanation=(
                    f"{features.game_bans} bannissement(s) applique(s) par un editeur "
                    "(Overwatch, anti-triche tiers…)."
                ),
                observed=float(features.game_bans),
                sample_size=1,
                metadata={"factual": True},
            )
        )

    total_bans = features.vac_bans + features.game_bans
    if total_bans > 0 and features.days_since_last_ban > 0:
        days = float(features.days_since_last_ban)
        recency = clamp(1.0 - days / _BAN_DECAY_DAYS)
        signals.append(
            Signal(
                key="ban.recency",
                label="Anciennete de la sanction",
                category=SignalCategory.BAN,
                score=recency,
                confidence=1.0,
                weight=config.weight_of("ban.recency"),
                explanation=(
                    f"Derniere sanction il y a {features.days_since_last_ban} jours."
                    + (
                        " Sanction recente : le comportement peut etre toujours d'actualite."
                        if recency > 0.6
                        else " Sanction ancienne, poids reduit."
                    )
                ),
                observed=days,
                sample_size=1,
                metadata={"factual": True},
            )
        )

    if features.community_banned or features.economy_banned:
        reasons = []
        if features.community_banned:
            reasons.append("bannissement communautaire")
        if features.economy_banned:
            reasons.append("restriction sur le marche")
        signals.append(
            Signal(
                key="ban.community",
                label="Restrictions Steam",
                category=SignalCategory.BAN,
                score=0.55,
                confidence=1.0,
                weight=config.weight_of("ban.community"),
                explanation=(
                    "Compte sous " + " et ".join(reasons)
                    + " — indicateur d'abus, pas necessairement de triche en jeu."
                ),
                sample_size=1,
                metadata={"factual": True},
            )
        )

    return tuple(signals)


def has_confirmed_ban(features: PlayerFeatures) -> bool:
    return features.vac_bans > 0 or features.game_bans > 0
