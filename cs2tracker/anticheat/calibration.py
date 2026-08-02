"""Mesure de la justesse du moteur sur des corpus étiquetés.

**Le problème.** Les poids et les distributions de référence sont des choix
d'auteur. Rien ne démontre que le moteur sépare correctement un tricheur d'un
très bon joueur — et sans mesure, tout ajustement se fait à l'aveugle.

**Le protocole.** Deux corpus étiquetés :

* ``cheater`` — comptes portant un bannissement VAC ou éditeur confirmé ;
* ``legit`` — joueurs professionnels, streamers connus, comptes de confiance.

Le moteur est exécuté sur chacun, puis on mesure précision, rappel et surtout
le **taux de faux positifs** : signaler un joueur honnête coûte plus cher que
manquer un tricheur.

Un point de méthode qui compte : lors de l'évaluation, les détecteurs de
sanctions sont **neutralisés**. Sans cela, le moteur « reconnaîtrait » les
tricheurs en lisant leur bannissement — une tautologie parfaite qui produirait
100 % de réussite sans rien prouver.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Sequence

from cs2tracker.anticheat.engine import AnalysisResult, analyse
from cs2tracker.anticheat.weights import DEFAULT_CONFIG, EngineConfig
from cs2tracker.core.models import PlayerProfile
from cs2tracker.core.utils import mean, safe_div

#: Seuil de decision par defaut : au-dela, le moteur « accuse ».
DEFAULT_THRESHOLD = 70.0


def blind_config(config: EngineConfig = DEFAULT_CONFIG) -> EngineConfig:
    """Configuration ignorant les sanctions déjà prononcées.

    Indispensable pour évaluer : un corpus de tricheurs est constitué de
    comptes bannis, que les détecteurs `ban.*` reconnaîtraient immédiatement.
    Le moteur obtiendrait un score parfait en lisant la réponse.
    """
    weights = {
        key: (0.0 if key.startswith("ban.") else value)
        for key, value in config.weights.items()
    }
    return replace(
        config,
        weights=weights,
        # Les planchers lies aux sanctions doivent tomber avec elles.
        confirmed_ban_floor=0.0,
    )


@dataclass(frozen=True, slots=True)
class LabelledProfile:
    """Un profil et son étiquette de vérité terrain."""

    profile: PlayerProfile
    is_cheater: bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class ConfusionMatrix:
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

    @property
    def precision(self) -> float:
        return safe_div(self.true_positive, self.true_positive + self.false_positive)

    @property
    def recall(self) -> float:
        return safe_div(self.true_positive, self.true_positive + self.false_negative)

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return safe_div(2 * self.precision * self.recall, denominator)

    @property
    def false_positive_rate(self) -> float:
        """Part des joueurs honnêtes signalés à tort — la métrique qui prime."""
        return safe_div(self.false_positive, self.false_positive + self.true_negative)

    @property
    def accuracy(self) -> float:
        total = (
            self.true_positive + self.false_positive
            + self.true_negative + self.false_negative
        )
        return safe_div(self.true_positive + self.true_negative, total)

    def as_dict(self) -> dict[str, Any]:
        return {
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "accuracy": round(self.accuracy, 4),
        }


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    threshold: float
    matrix: ConfusionMatrix
    cheater_scores: tuple[float, ...] = field(default_factory=tuple)
    legit_scores: tuple[float, ...] = field(default_factory=tuple)

    @property
    def separation(self) -> float:
        """Écart entre les moyennes des deux corpus.

        C'est l'indicateur le plus parlant : un moteur utile écarte nettement
        les deux populations, indépendamment du seuil choisi.
        """
        return mean(self.cheater_scores) - mean(self.legit_scores)

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "sample": {
                "cheaters": len(self.cheater_scores),
                "legit": len(self.legit_scores),
            },
            "metrics": self.matrix.as_dict(),
            "mean_score": {
                "cheaters": round(mean(self.cheater_scores), 1),
                "legit": round(mean(self.legit_scores), 1),
                "separation": round(self.separation, 1),
            },
            "usable": len(self.cheater_scores) >= 30 and len(self.legit_scores) >= 30,
            "note": (
                "Les detecteurs de sanctions sont neutralises pendant l'evaluation : "
                "sans cela le moteur reconnaitrait les tricheurs en lisant leur "
                "bannissement, ce qui ne prouverait rien."
            ),
        }


def evaluate(
    labelled: Sequence[LabelledProfile],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    config: EngineConfig | None = None,
) -> CalibrationReport:
    """Exécute le moteur sur un corpus étiqueté et mesure sa justesse."""
    engine_config = config or blind_config()

    cheater_scores: list[float] = []
    legit_scores: list[float] = []
    matrix = ConfusionMatrix()

    for entry in labelled:
        result: AnalysisResult = analyse(entry.profile, config=engine_config)
        flagged = result.suspicion_score >= threshold

        if entry.is_cheater:
            cheater_scores.append(result.suspicion_score)
            matrix = replace(
                matrix,
                true_positive=matrix.true_positive + int(flagged),
                false_negative=matrix.false_negative + int(not flagged),
            )
        else:
            legit_scores.append(result.suspicion_score)
            matrix = replace(
                matrix,
                false_positive=matrix.false_positive + int(flagged),
                true_negative=matrix.true_negative + int(not flagged),
            )

    return CalibrationReport(
        threshold=threshold,
        matrix=matrix,
        cheater_scores=tuple(cheater_scores),
        legit_scores=tuple(legit_scores),
    )


def sweep_thresholds(
    labelled: Sequence[LabelledProfile],
    thresholds: Iterable[float] = range(30, 100, 5),
    config: EngineConfig | None = None,
) -> list[dict[str, Any]]:
    """Balaye les seuils pour choisir le point de fonctionnement.

    Le meilleur seuil n'est pas celui qui maximise la réussite globale, mais
    celui qui garde le taux de faux positifs acceptable : accuser un joueur
    honnête est bien plus coûteux que laisser passer un tricheur.
    """
    engine_config = config or blind_config()
    return [
        evaluate(labelled, threshold=float(value), config=engine_config).as_dict()
        for value in thresholds
    ]


def recommend_threshold(
    labelled: Sequence[LabelledProfile],
    max_false_positive_rate: float = 0.02,
    config: EngineConfig | None = None,
) -> dict[str, Any]:
    """Seuil le plus bas respectant un plafond de faux positifs."""
    results = sweep_thresholds(labelled, config=config)
    acceptable = [
        entry
        for entry in results
        if entry["metrics"]["false_positive_rate"] <= max_false_positive_rate
    ]
    if not acceptable:
        return {
            "recommended": None,
            "reason": (
                f"Aucun seuil ne tient sous {max_false_positive_rate:.0%} de faux "
                "positifs sur ce corpus. Le moteur doit etre recalibre avant "
                "d'etre utilise pour signaler."
            ),
            "sweep": results,
        }

    best = min(acceptable, key=lambda entry: entry["threshold"])
    return {
        "recommended": best["threshold"],
        "reason": (
            f"Seuil le plus sensible respectant {max_false_positive_rate:.0%} de "
            f"faux positifs (rappel {best['metrics']['recall']:.0%})."
        ),
        "metrics": best["metrics"],
        "sweep": results,
    }
