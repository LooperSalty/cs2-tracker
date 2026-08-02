"""Références segmentées par niveau de jeu.

**Le problème que ça résout.** Le moteur comparait tout le monde à la moyenne de
la population entière. Un joueur de niveau compétitif était donc *toujours*
signalé : ses statistiques sont réellement extrêmes par rapport à l'ensemble des
joueurs. C'était la première cause de faux positifs restante.

La correction consiste à comparer chaque joueur à **ses pairs** plutôt qu'à
tout le monde. À défaut d'un rang officiel — le classement Premier n'est pas
exposé par l'API Steam —, le niveau est estimé à partir de signaux disponibles :
niveau FACEIT lorsqu'il est connu, sinon volume de jeu et rendement.

Comme pour ``baselines.py``, les valeurs ci-dessous sont des estimations
calibrées et non des mesures officielles. Elles sont isolées ici pour être
ajustables sans toucher aux détecteurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from cs2tracker.anticheat.baselines import Baseline


@dataclass(frozen=True, slots=True)
class SkillTier:
    """Palier de niveau et ses distributions de référence."""

    key: str
    label: str
    #: Bornes indicatives en niveau FACEIT (1-10), quand il est connu.
    faceit_range: tuple[int, int]
    headshot_rate: Baseline
    accuracy: Baseline
    kills_per_round: Baseline
    damage_per_round: Baseline
    kd_ratio: Baseline

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "faceit_range": list(self.faceit_range),
            "headshot_rate": round(self.headshot_rate.mean, 4),
            "accuracy": round(self.accuracy.mean, 4),
            "kills_per_round": round(self.kills_per_round.mean, 4),
            "damage_per_round": round(self.damage_per_round.mean, 2),
            "kd_ratio": round(self.kd_ratio.mean, 3),
        }


#: Quatre paliers plutôt que dix : au-delà, les distributions se chevauchent
#: tellement que la segmentation n'apporte plus rien.
TIERS: Final[tuple[SkillTier, ...]] = (
    SkillTier(
        key="debutant",
        label="Debutant",
        faceit_range=(1, 3),
        headshot_rate=Baseline(0.38, 0.10, hard_ceiling=0.85),
        accuracy=Baseline(0.175, 0.045, hard_ceiling=0.50),
        kills_per_round=Baseline(0.50, 0.14, hard_ceiling=1.5),
        damage_per_round=Baseline(58.0, 16.0, hard_ceiling=160.0),
        kd_ratio=Baseline(0.82, 0.20, hard_ceiling=3.0),
    ),
    SkillTier(
        key="intermediaire",
        label="Intermediaire",
        faceit_range=(4, 6),
        headshot_rate=Baseline(0.45, 0.093, hard_ceiling=0.88),
        accuracy=Baseline(0.205, 0.043, hard_ceiling=0.54),
        kills_per_round=Baseline(0.63, 0.15, hard_ceiling=1.7),
        damage_per_round=Baseline(73.0, 17.0, hard_ceiling=175.0),
        kd_ratio=Baseline(1.00, 0.21, hard_ceiling=3.4),
    ),
    SkillTier(
        key="avance",
        label="Avance",
        faceit_range=(7, 8),
        headshot_rate=Baseline(0.51, 0.088, hard_ceiling=0.90),
        accuracy=Baseline(0.228, 0.042, hard_ceiling=0.57),
        kills_per_round=Baseline(0.74, 0.15, hard_ceiling=1.9),
        damage_per_round=Baseline(85.0, 17.0, hard_ceiling=190.0),
        kd_ratio=Baseline(1.18, 0.22, hard_ceiling=3.8),
    ),
    SkillTier(
        key="elite",
        label="Elite",
        faceit_range=(9, 10),
        headshot_rate=Baseline(0.56, 0.085, hard_ceiling=0.92),
        accuracy=Baseline(0.248, 0.041, hard_ceiling=0.60),
        kills_per_round=Baseline(0.84, 0.16, hard_ceiling=2.1),
        damage_per_round=Baseline(96.0, 18.0, hard_ceiling=205.0),
        kd_ratio=Baseline(1.35, 0.24, hard_ceiling=4.2),
    ),
)

TIER_BY_KEY: Final[dict[str, SkillTier]] = {tier.key: tier for tier in TIERS}

#: Palier retenu quand rien ne permet de trancher.
DEFAULT_TIER: Final = TIER_BY_KEY["intermediaire"]

#: Heures de jeu délimitant les paliers, à défaut de niveau FACEIT.
_HOURS_THRESHOLDS: Final = ((150.0, "debutant"), (900.0, "intermediaire"), (2500.0, "avance"))


@dataclass(frozen=True, slots=True)
class TierAssignment:
    """Palier retenu, avec la raison — l'utilisateur doit pouvoir la contester."""

    tier: SkillTier
    source: str
    confident: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "tier": self.tier.key,
            "label": self.tier.label,
            "source": self.source,
            "confident": self.confident,
            "reference": self.tier.as_dict(),
        }


def tier_from_faceit(level: int) -> SkillTier:
    for tier in TIERS:
        low, high = tier.faceit_range
        if low <= level <= high:
            return tier
    return TIERS[-1] if level > 10 else TIERS[0]


def assign_tier(
    *,
    faceit_level: int | None = None,
    hours_played: float = 0.0,
    kills_per_round: float = 0.0,
    rounds_played: int = 0,
) -> TierAssignment:
    """Estime le palier d'un joueur.

    Le niveau FACEIT prime : c'est le seul classement objectif accessible. À
    défaut, on combine volume de jeu et rendement — imparfait, mais nettement
    préférable à comparer un joueur de 3 000 heures à la moyenne générale.
    """
    if faceit_level and faceit_level > 0:
        return TierAssignment(
            tier=tier_from_faceit(faceit_level),
            source=f"niveau FACEIT {faceit_level}",
            confident=True,
        )

    # Sans classement, l'echantillon doit au moins etre consequent.
    if rounds_played < 500:
        return TierAssignment(
            tier=DEFAULT_TIER,
            source="echantillon insuffisant, palier median retenu",
            confident=False,
        )

    by_hours = "elite"
    for threshold, key in _HOURS_THRESHOLDS:
        if hours_played < threshold:
            by_hours = key
            break

    # Le rendement corrige l'anciennete : beaucoup d'heures ne fait pas un bon
    # joueur, et l'inverse est vrai aussi.
    by_output = "debutant"
    for tier in TIERS:
        if kills_per_round >= tier.kills_per_round.mean - tier.kills_per_round.stdev * 0.5:
            by_output = tier.key

    order = [tier.key for tier in TIERS]
    combined_index = (order.index(by_hours) + order.index(by_output)) // 2

    return TierAssignment(
        tier=TIERS[combined_index],
        source=f"estime ({hours_played:.0f} h, {kills_per_round:.2f} kill/manche)",
        confident=False,
    )
