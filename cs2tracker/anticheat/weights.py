"""Pondération des détecteurs et paramètres du moteur de score.

Centraliser ces valeurs permet de recalibrer le modèle sans toucher aux
détecteurs eux-mêmes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Mapping

#: Poids par clé de détecteur. Somme non normalisée : le moteur normalise.
DETECTOR_WEIGHTS: Final[dict[str, float]] = {
    # --- Sanctions (factuel, très lourd) -------------------------------------
    "ban.vac": 3.0,
    "ban.game": 2.2,
    "ban.recency": 1.2,
    "ban.community": 0.5,
    # --- Visée (le cœur de la détection statistique) -------------------------
    "aim.headshot_rate": 2.6,
    "aim.accuracy": 2.2,
    "aim.hits_per_kill": 1.5,
    "aim.shots_per_kill": 1.2,
    "aim.damage_per_kill": 1.0,
    # --- Armes ---------------------------------------------------------------
    "weapon.category_headshots": 1.8,
    "weapon.spray_accuracy": 1.6,
    "weapon.uniformity": 1.4,
    # --- Progression / expérience -------------------------------------------
    "progression.performance_vs_hours": 1.9,
    "progression.kills_per_hour": 1.3,
    "progression.kd": 1.2,
    "progression.round_win_rate": 0.9,
    "progression.mvp_rate": 0.8,
    # --- Compte --------------------------------------------------------------
    "account.age": 0.9,
    "account.privacy": 0.6,
    "account.library": 0.7,
    "account.social": 0.5,
    "account.smurf_profile": 1.1,
    # --- Temps réel ----------------------------------------------------------
    "live.headshot_rate": 2.0,
    "live.adr": 1.4,
    "live.multi_kills": 1.3,
    "live.kill_rhythm": 1.7,
    "live.fast_chains": 1.2,
    "live.utility_neglect": 0.7,
    "live.survival": 0.8,
    # --- Régularité ----------------------------------------------------------
    "consistency.adr_variability": 1.6,
    "consistency.stats_vs_live": 1.5,
}


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Paramètres de l'agrégation finale."""

    #: Confiance minimale sous laquelle un signal est ignoré dans le score.
    min_confidence: float = 0.05
    #: Exposant appliqué au score agrégé — >1 rend le moteur plus conservateur.
    aggregation_exponent: float = 1.15
    #: Score minimal imposé si au moins un signal critique est présent.
    critical_signal_floor: float = 62.0
    #: Score minimal imposé en présence d'un ban VAC/jeu avéré.
    confirmed_ban_floor: float = 80.0
    #: Nombre de signaux « élevés » à partir duquel on applique un bonus de corroboration.
    corroboration_threshold: int = 3
    #: Multiplicateur appliqué lorsque plusieurs signaux indépendants concordent.
    corroboration_multiplier: float = 1.12
    #: Confiance globale minimale pour oser un verdict autre que « indéterminé ».
    min_global_confidence: float = 0.25
    weights: Mapping[str, float] = field(default_factory=lambda: dict(DETECTOR_WEIGHTS))

    def weight_of(self, key: str) -> float:
        return self.weights.get(key, 1.0)


DEFAULT_CONFIG: Final = EngineConfig()
