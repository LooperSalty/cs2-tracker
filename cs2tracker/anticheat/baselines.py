"""Référentiels statistiques de population servant de base aux z-scores.

**Nature de ces valeurs** : ce sont des estimations calibrées de la population
matchmaking CS:GO/CS2, pas des mesures officielles Valve. Elles sont exposées
ici, isolées et documentées, précisément pour être ajustables : chaque valeur
peut être recalibrée sans toucher à la logique des détecteurs.

Toute conclusion tirée de ces baselines est **probabiliste**. Un écart n'est
jamais une preuve de triche : c'est une anomalie statistique à interpréter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Baseline:
    """Distribution de référence d'une métrique."""

    mean: float
    stdev: float
    #: Valeur au-delà de laquelle la métrique devient physiquement improbable.
    hard_ceiling: float = float("inf")
    #: Valeur en deçà de laquelle la métrique devient improbable (métriques inversées).
    hard_floor: float = float("-inf")
    label: str = ""
    unit: str = ""

    def z(self, value: float) -> float:
        if self.stdev <= 0:
            return 0.0
        return (value - self.mean) / self.stdev


# --- Statistiques à vie (Steam Web API) --------------------------------------

HEADSHOT_RATE: Final = Baseline(
    mean=0.45, stdev=0.095, hard_ceiling=0.90,
    label="Taux de tirs a la tete", unit="%",
)
ACCURACY: Final = Baseline(
    mean=0.205, stdev=0.045, hard_ceiling=0.55,
    label="Precision globale", unit="%",
)
KD_RATIO: Final = Baseline(
    mean=0.98, stdev=0.22, hard_ceiling=3.5,
    label="Ratio K/D", unit="",
)
KILLS_PER_ROUND: Final = Baseline(
    mean=0.62, stdev=0.16, hard_ceiling=1.8,
    label="Kills par manche", unit="",
)
DAMAGE_PER_ROUND: Final = Baseline(
    mean=72.0, stdev=18.0, hard_ceiling=180.0,
    label="Degats par manche (ADR)", unit="dmg",
)
KILLS_PER_HOUR: Final = Baseline(
    mean=45.0, stdev=13.0, hard_ceiling=140.0,
    label="Kills par heure", unit="/h",
)
HITS_PER_KILL: Final = Baseline(
    mean=3.9, stdev=1.0, hard_floor=1.3,
    label="Impacts par kill", unit="",
)
SHOTS_PER_KILL: Final = Baseline(
    mean=19.0, stdev=5.5, hard_floor=5.0,
    label="Balles tirees par kill", unit="",
)
MVP_RATE: Final = Baseline(
    mean=0.105, stdev=0.032, hard_ceiling=0.40,
    label="Taux de MVP", unit="%",
)
ROUND_WIN_RATE: Final = Baseline(
    mean=0.50, stdev=0.055, hard_ceiling=0.80,
    label="Taux de manches gagnees", unit="%",
)
#: Coherent avec ADR ~72 et ~0.62 kill/manche : 72 / 0.62 ≈ 116 degats par kill.
#: Un joueur ne peut pas descendre sous ~100 (les PV d'une cible), d'ou le plancher.
DAMAGE_PER_KILL: Final = Baseline(
    mean=122.0, stdev=15.0, hard_floor=101.0,
    label="Degats par kill", unit="dmg",
)

# --- Métriques temps réel (GSI) ----------------------------------------------

LIVE_HEADSHOT_RATE: Final = Baseline(
    mean=0.46, stdev=0.13, hard_ceiling=0.95,
    label="Taux de HS en direct", unit="%",
)
LIVE_ADR: Final = Baseline(
    mean=75.0, stdev=22.0, hard_ceiling=200.0,
    label="ADR observe", unit="dmg",
)
#: Coefficient de variation des dégâts par manche. **Métrique inversée** :
#: c'est une valeur *basse* qui interpelle (régularité mécanique).
ADR_VARIABILITY: Final = Baseline(
    mean=0.78, stdev=0.20, hard_floor=0.22,
    label="Irregularite des degats", unit="",
)
MULTI_KILL_RATE: Final = Baseline(
    mean=0.12, stdev=0.065, hard_ceiling=0.55,
    label="Taux de manches a 3+ kills", unit="%",
)
#: Écart-type des délais entre kills. **Métrique inversée** également.
KILL_INTERVAL_STDEV: Final = Baseline(
    mean=4.6, stdev=1.9, hard_floor=0.6,
    label="Dispersion des delais entre kills", unit="s",
)
FAST_CHAIN_RATE: Final = Baseline(
    mean=0.22, stdev=0.12, hard_ceiling=0.85,
    label="Taux d'enchainements rapides", unit="%",
)
UTILITY_PER_ROUND: Final = Baseline(
    mean=1.35, stdev=0.55, hard_floor=0.05,
    label="Utilitaires par manche", unit="",
)
SURVIVAL_RATE: Final = Baseline(
    mean=0.34, stdev=0.10, hard_ceiling=0.85,
    label="Taux de survie", unit="%",
)

# --- Méta-compte --------------------------------------------------------------

FRIENDS_COUNT: Final = Baseline(mean=48.0, stdev=45.0, label="Nombre d'amis")
STEAM_LEVEL: Final = Baseline(mean=12.0, stdev=13.0, label="Niveau Steam")
GAMES_OWNED: Final = Baseline(mean=38.0, stdev=45.0, label="Jeux possedes")

#: Ancienneté (en jours) en dessous de laquelle un compte est « jeune ».
YOUNG_ACCOUNT_DAYS: Final = 180
#: Heures CS2 en dessous desquelles l'échantillon de jeu est très mince.
LOW_EXPERIENCE_HOURS: Final = 150.0
#: Heures au-delà desquelles la performance devient statistiquement crédible.
HIGH_EXPERIENCE_HOURS: Final = 1_500.0

#: Poids du prior bayésien pour lisser les taux (kills, HS…).
PRIOR_WEIGHT_KILLS: Final = 250.0
PRIOR_WEIGHT_SHOTS: Final = 3_000.0
PRIOR_WEIGHT_ROUNDS: Final = 60.0


@dataclass(frozen=True, slots=True)
class WeaponBaseline:
    """Référence spécifique à une arme (le HS n'a pas le même sens partout)."""

    headshot_rate_mean: float
    headshot_rate_stdev: float
    accuracy_mean: float
    accuracy_stdev: float


#: Références par catégorie d'arme, plus robustes qu'une moyenne globale.
WEAPON_CATEGORY_BASELINES: Final[dict[str, WeaponBaseline]] = {
    "Fusil": WeaponBaseline(0.47, 0.10, 0.22, 0.05),
    "Pistolet": WeaponBaseline(0.43, 0.12, 0.24, 0.06),
    "SMG": WeaponBaseline(0.34, 0.10, 0.21, 0.05),
    "Sniper": WeaponBaseline(0.22, 0.09, 0.34, 0.08),
    "Fusil a pompe": WeaponBaseline(0.20, 0.08, 0.29, 0.07),
    "Mitrailleuse": WeaponBaseline(0.28, 0.10, 0.18, 0.05),
}
