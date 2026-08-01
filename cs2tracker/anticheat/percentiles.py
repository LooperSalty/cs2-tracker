"""Positionnement d'un joueur dans la population, métrique par métrique.

Un chiffre brut ne dit rien à personne : « 21 % de précision », est-ce bien ?
Ce module convertit chaque statistique en **percentile** — « meilleur que 68 %
des joueurs » — en réutilisant les distributions de référence qui servent déjà
au moteur anti-triche. Aucune donnée supplémentaire n'est nécessaire.

Hypothèse assumée : les métriques sont approximativement normales autour de leur
moyenne de population. C'est faux dans les queues extrêmes, ce qui n'a pas
d'importance ici — au-delà du 99ᵉ percentile, la seule information utile est
« très au-dessus du lot ».
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final, Mapping

from cs2tracker.anticheat import baselines
from cs2tracker.anticheat.baselines import Baseline
from cs2tracker.core.models import Cs2Stats
from cs2tracker.core.utils import clamp

#: Paliers de restitution. Bornes basses inclusives.
TIERS: Final[tuple[tuple[float, str, str], ...]] = (
    (0.99, "elite", "Elite"),
    (0.90, "excellent", "Excellent"),
    (0.75, "bon", "Bon"),
    (0.40, "moyen", "Moyen"),
    (0.15, "faible", "Sous la moyenne"),
    (0.00, "debutant", "Debutant"),
)


def normal_cdf(z: float) -> float:
    """Fonction de répartition de la loi normale centrée réduite."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def tier_for(percentile: float) -> tuple[str, str]:
    for threshold, key, label in TIERS:
        if percentile >= threshold:
            return key, label
    return TIERS[-1][1], TIERS[-1][2]


@dataclass(frozen=True, slots=True)
class Ranked:
    """Une statistique replacée dans la population."""

    key: str
    label: str
    value: float
    percentile: float
    baseline_mean: float
    unit: str
    #: Vrai lorsqu'une valeur **basse** est meilleure (balles par kill…).
    lower_is_better: bool

    @property
    def tier(self) -> tuple[str, str]:
        return tier_for(self.percentile)

    @property
    def top_percent(self) -> float:
        """Position exprimée « top X % », plus parlante que le percentile."""
        return round((1.0 - self.percentile) * 100, 1)

    def as_dict(self) -> dict[str, Any]:
        tier_key, tier_label = self.tier
        return {
            "key": self.key,
            "label": self.label,
            "value": round(self.value, 4),
            "percentile": round(self.percentile * 100, 1),
            "top_percent": self.top_percent,
            "average": round(self.baseline_mean, 4),
            "unit": self.unit,
            "tier": tier_key,
            "tier_label": tier_label,
            "lower_is_better": self.lower_is_better,
        }


def rank_metric(
    key: str,
    label: str,
    value: float,
    baseline: Baseline,
    *,
    unit: str = "",
    lower_is_better: bool = False,
) -> Ranked:
    z = baseline.z(value)
    if lower_is_better:
        z = -z
    return Ranked(
        key=key,
        label=label,
        value=value,
        percentile=clamp(normal_cdf(z), 0.001, 0.999),
        baseline_mean=baseline.mean,
        unit=unit,
        lower_is_better=lower_is_better,
    )


#: Métriques présentées au joueur, dans l'ordre d'affichage.
_RANKED_METRICS: Final = (
    ("kd", "Ratio K/D", "kd_ratio", baselines.KD_RATIO, "", False),
    ("headshot_rate", "Headshots", "headshot_rate", baselines.HEADSHOT_RATE, "%", False),
    ("accuracy", "Precision", "accuracy", baselines.ACCURACY, "%", False),
    ("damage_per_round", "Degats / manche", "damage_per_round", baselines.DAMAGE_PER_ROUND, "", False),
    ("kills_per_round", "Kills / manche", "kills_per_round", baselines.KILLS_PER_ROUND, "", False),
    ("mvp_rate", "Taux de MVP", "mvp_rate", baselines.MVP_RATE, "%", False),
    ("round_win_rate", "Manches gagnees", "round_win_rate", baselines.ROUND_WIN_RATE, "%", False),
    ("kills_per_hour", "Kills / heure", "kills_per_hour", baselines.KILLS_PER_HOUR, "", False),
    ("shots_per_kill", "Balles / kill", "shots_per_kill", baselines.SHOTS_PER_KILL, "", True),
    ("hits_per_kill", "Impacts / kill", "hits_per_kill", baselines.HITS_PER_KILL, "", True),
)


def rank_player(stats: Cs2Stats | None) -> dict[str, Any]:
    """Classe toutes les métriques d'un joueur et calcule une note globale."""
    if stats is None or stats.total_rounds_played <= 0:
        return {
            "available": False,
            "reason": "Statistiques de jeu indisponibles.",
            "metrics": [],
        }

    ranked = [
        rank_metric(
            key, label, getattr(stats, attribute), baseline,
            unit=unit, lower_is_better=lower_is_better,
        )
        for key, label, attribute, baseline, unit, lower_is_better in _RANKED_METRICS
    ]

    # Note globale : moyenne des percentiles des seules métriques de performance.
    # Les métriques d'efficacité (balles par kill) y sont incluses car un joueur
    # efficace l'est réellement — c'est le moteur anti-triche, pas le classement,
    # qui s'inquiète d'une efficacité *anormale*.
    overall = sum(item.percentile for item in ranked) / len(ranked)
    tier_key, tier_label = tier_for(overall)

    return {
        "available": True,
        "overall_percentile": round(overall * 100, 1),
        "overall_top_percent": round((1 - overall) * 100, 1),
        "overall_tier": tier_key,
        "overall_tier_label": tier_label,
        "sample": {
            "rounds": stats.total_rounds_played,
            "kills": stats.total_kills,
            "reliable": stats.has_meaningful_sample,
        },
        "metrics": [item.as_dict() for item in ranked],
    }


def rank_weapon_accuracy(
    weapon_key: str, accuracy: float, category: str
) -> Mapping[str, Any] | None:
    """Percentile de précision d'une arme, comparée à sa propre catégorie."""
    reference = baselines.WEAPON_CATEGORY_BASELINES.get(category)
    if reference is None or accuracy <= 0:
        return None
    z = (accuracy - reference.accuracy_mean) / max(reference.accuracy_stdev, 1e-6)
    percentile = clamp(normal_cdf(z), 0.001, 0.999)
    tier_key, tier_label = tier_for(percentile)
    return {
        "weapon": weapon_key,
        "percentile": round(percentile * 100, 1),
        "tier": tier_key,
        "tier_label": tier_label,
        "category_average": round(reference.accuracy_mean, 4),
    }
