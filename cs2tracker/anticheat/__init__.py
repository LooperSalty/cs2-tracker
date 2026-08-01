"""Moteur d'analyse anti-triche heuristique.

Ce paquet n'accède **jamais** à la mémoire du jeu, n'injecte rien et ne modifie
aucun fichier de CS2 autre que le ``.cfg`` officiel de Game State Integration.
Il ne travaille que sur des données publiques (Steam Web API) et sur le flux GSI
que Valve expose volontairement.
"""

from cs2tracker.anticheat.engine import (
    AnalysisResult,
    DISCLAIMER,
    analyse,
    analyse_many,
)
from cs2tracker.anticheat.signals import Severity, Signal, SignalCategory

__all__ = [
    "AnalysisResult",
    "DISCLAIMER",
    "Severity",
    "Signal",
    "SignalCategory",
    "analyse",
    "analyse_many",
]
