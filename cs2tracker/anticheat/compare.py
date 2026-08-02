"""Comparaison directe de deux joueurs, métrique par métrique."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from cs2tracker.anticheat.percentiles import rank_player
from cs2tracker.core.models import PlayerProfile
from cs2tracker.core.utils import safe_div

#: Métriques confrontées, avec le sens dans lequel « mieux » se lit.
_METRICS: tuple[tuple[str, str, str, bool], ...] = (
    ("kd", "Ratio K/D", "", False),
    ("headshot_rate", "Headshots", "%", False),
    ("accuracy", "Precision", "%", False),
    ("damage_per_round", "Degats / manche", "", False),
    ("kills_per_round", "Kills / manche", "", False),
    ("mvp_rate", "Taux de MVP", "%", False),
    ("round_win_rate", "Manches gagnees", "%", False),
    ("kills_per_hour", "Kills / heure", "", False),
    ("shots_per_kill", "Balles / kill", "", True),
    ("hits_per_kill", "Impacts / kill", "", True),
)


@dataclass(frozen=True, slots=True)
class MetricDuel:
    """Une métrique confrontée entre deux joueurs."""

    key: str
    label: str
    unit: str
    left: float
    right: float
    lower_is_better: bool

    @property
    def winner(self) -> str:
        if abs(self.left - self.right) < 1e-9:
            return "egalite"
        better_left = (
            self.left < self.right if self.lower_is_better else self.left > self.right
        )
        return "left" if better_left else "right"

    @property
    def gap_percent(self) -> float:
        """Écart relatif, rapporté à la plus petite des deux valeurs."""
        base = min(abs(self.left), abs(self.right)) or 1.0
        return abs(self.left - self.right) / base * 100.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "left": round(self.left, 4),
            "right": round(self.right, 4),
            "winner": self.winner,
            "gap_percent": round(self.gap_percent, 1),
            "lower_is_better": self.lower_is_better,
        }


def _side(profile: PlayerProfile) -> dict[str, Any]:
    summary = profile.summary
    stats = profile.stats
    account = profile.account
    ranking = rank_player(stats)

    return {
        "steamid64": str(profile.identity.get("steamid64", "")),
        "name": summary.persona_name if summary else "",
        "avatar": (summary.avatar_full or summary.avatar) if summary else "",
        "hours": round(account.cs2_hours, 1) if account else 0.0,
        "rounds": stats.total_rounds_played if stats else 0,
        "overall_percentile": ranking.get("overall_percentile"),
        "overall_tier": ranking.get("overall_tier_label"),
        "has_stats": stats is not None and stats.total_rounds_played > 0,
    }


def compare(left: PlayerProfile, right: PlayerProfile) -> dict[str, Any]:
    """Confronte deux profils et désigne un vainqueur par métrique."""
    left_stats, right_stats = left.stats, right.stats

    if left_stats is None or right_stats is None:
        missing = left if left_stats is None else right
        name = missing.summary.persona_name if missing.summary else "ce joueur"
        return {
            "comparable": False,
            "reason": (
                f"Les statistiques de {name} sont indisponibles — profil prive, "
                "ou aucune partie jouee."
            ),
            "left": _side(left),
            "right": _side(right),
        }

    duels = [
        MetricDuel(
            key=key,
            label=label,
            unit=unit,
            left=getattr(left_stats, _attribute(key)),
            right=getattr(right_stats, _attribute(key)),
            lower_is_better=lower_is_better,
        )
        for key, label, unit, lower_is_better in _METRICS
    ]

    left_wins = sum(1 for duel in duels if duel.winner == "left")
    right_wins = sum(1 for duel in duels if duel.winner == "right")

    return {
        "comparable": True,
        "left": _side(left),
        "right": _side(right),
        "metrics": [duel.as_dict() for duel in duels],
        "tally": {
            "left": left_wins,
            "right": right_wins,
            "draws": len(duels) - left_wins - right_wins,
        },
        "verdict": _verdict(left, right, left_wins, right_wins),
        # Comparer 200 manches a 80 000 n'a pas de sens : on le signale plutot
        # que de laisser croire a une egalite de fiabilite.
        "sample_warning": _sample_warning(
            left_stats.total_rounds_played, right_stats.total_rounds_played
        ),
    }


def _attribute(key: str) -> str:
    """Nom de la propriété correspondante sur ``Cs2Stats``."""
    return {"kd": "kd_ratio"}.get(key, key)


def _verdict(
    left: PlayerProfile, right: PlayerProfile, left_wins: int, right_wins: int
) -> str:
    left_name = left.summary.persona_name if left.summary else "Joueur A"
    right_name = right.summary.persona_name if right.summary else "Joueur B"

    if left_wins == right_wins:
        return f"{left_name} et {right_name} sont au coude a coude."
    leader, count, other = (
        (left_name, left_wins, right_wins)
        if left_wins > right_wins
        else (right_name, right_wins, left_wins)
    )
    return f"{leader} mene sur {count} metriques contre {other}."


def _sample_warning(left_rounds: int, right_rounds: int) -> str:
    smaller, larger = sorted((left_rounds, right_rounds))
    if smaller == 0:
        return "L'un des deux profils n'a aucune manche enregistree."
    if safe_div(larger, smaller) >= 5:
        return (
            f"Echantillons tres inegaux ({smaller} manches contre {larger}) : "
            "les moyennes du plus petit sont bien moins stables."
        )
    return ""
