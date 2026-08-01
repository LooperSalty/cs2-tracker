"""Ensemble des détecteurs. Chacun expose ``detect(features, config)``."""

from __future__ import annotations

from typing import Callable, Final, Sequence

from cs2tracker.anticheat.detectors import (
    account,
    aim,
    bans,
    consistency,
    live_behavior,
    progression,
    weapon_profile,
)
from cs2tracker.anticheat.features import PlayerFeatures
from cs2tracker.anticheat.signals import Signal
from cs2tracker.anticheat.weights import EngineConfig

DetectorFn = Callable[[PlayerFeatures, EngineConfig], Sequence[Signal]]

#: Ordre d'exécution — sans effet sur le score, mais structure l'affichage.
ALL_DETECTORS: Final[tuple[tuple[str, DetectorFn], ...]] = (
    ("sanctions", bans.detect),
    ("visee", aim.detect),
    ("armes", weapon_profile.detect),
    ("progression", progression.detect),
    ("compte", account.detect),
    ("temps_reel", live_behavior.detect),
    ("regularite", consistency.detect),
)

__all__ = [
    "ALL_DETECTORS",
    "DetectorFn",
    "account",
    "aim",
    "bans",
    "consistency",
    "live_behavior",
    "progression",
    "weapon_profile",
]
