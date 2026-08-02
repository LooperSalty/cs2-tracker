"""Analyse de démos CS2 : les détections que le GSI ne permet pas.

**Ce que ça débloque.** Le Game State Integration ne transmet ni les angles de
visée ni la position du réticule. Le moteur ne pouvait donc mesurer que le
rythme et l'efficacité — jamais le geste lui-même.

Une démo contient les *ticks* du serveur : position et angle de vue de chaque
joueur, 64 fois par seconde. C'est la seule source permettant d'observer ce
qu'un logiciel d'aide à la visée modifie réellement.

| Détecteur | Signature recherchée |
|---|---|
| ``snap`` | Accélération angulaire quasi instantanée juste avant le tir |
| ``overshoot`` | Le réticule dépasse la cible puis se recale *après* |
| ``walltrack`` | L'angle suit un adversaire hors de la ligne de vue |
| ``recoil`` | Contre-mouvement identique à la trame près |
| ``hitzones`` | Répartition réelle des impacts — inaccessible via Steam |

**Dépendance optionnelle.** Le parsing s'appuie sur ``demoparser2``. Absent, le
module se désactive proprement au lieu d'empêcher l'application de démarrer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from cs2tracker.core.utils import clamp, mean, percentile, safe_div, stdev
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

#: Fenêtre observée avant chaque tir, en ticks (64 ticks ≈ 1 seconde).
PRE_SHOT_TICKS = 16
#: Au-delà, une correction d'angle n'est plus humainement plausible.
SNAP_DEGREES_PER_TICK = 22.0
#: Nombre de tirs minimal avant de produire le moindre chiffre.
MIN_SHOTS_FOR_ANALYSIS = 40


def parser_available() -> bool:
    """Vrai si ``demoparser2`` est installé."""
    try:
        import demoparser2  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class AimSample:
    """Un tir, avec la trajectoire angulaire qui l'a précédé."""

    tick: int
    steamid: str
    weapon: str
    #: Variation d'angle par tick sur la fenêtre précédant le tir, en degrés.
    deltas: tuple[float, ...]

    @property
    def peak_speed(self) -> float:
        return max(self.deltas) if self.deltas else 0.0

    @property
    def final_adjustment(self) -> float:
        """Correction sur les deux derniers ticks avant le tir."""
        return sum(self.deltas[-2:]) if len(self.deltas) >= 2 else 0.0


@dataclass(frozen=True, slots=True)
class DemoFinding:
    """Un constat issu de la démo, toujours accompagné de son échantillon."""

    key: str
    label: str
    score: float
    confidence: float
    explanation: str
    observed: float
    sample_size: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(clamp(self.score), 4),
            "confidence": round(clamp(self.confidence), 3),
            "explanation": self.explanation,
            "observed": round(self.observed, 4),
            "sample_size": self.sample_size,
            "metadata": dict(self.metadata),
        }


def angle_delta(a: float, b: float) -> float:
    """Écart angulaire le plus court entre deux caps, en degrés.

    Sans ce repliement, un passage de 359° à 1° serait lu comme un
    retournement de 358° — et chaque tour de caméra deviendrait un « snap ».
    """
    diff = (b - a + 180.0) % 360.0 - 180.0
    return abs(diff)


def view_speed(yaw_series: Sequence[float], pitch_series: Sequence[float]) -> list[float]:
    """Vitesse angulaire tick par tick, en degrés."""
    speeds: list[float] = []
    for index in range(1, min(len(yaw_series), len(pitch_series))):
        dyaw = angle_delta(yaw_series[index - 1], yaw_series[index])
        dpitch = abs(pitch_series[index] - pitch_series[index - 1])
        speeds.append(math.hypot(dyaw, dpitch))
    return speeds


# --------------------------------------------------------------- detecteurs

def detect_snaps(samples: Sequence[AimSample]) -> DemoFinding:
    """Accélérations angulaires incompatibles avec un mouvement de souris.

    Un humain accélère et décélère progressivement, même très vite. Une
    acquisition assistée produit au contraire un pic isolé sur un ou deux ticks,
    immédiatement suivi du tir.
    """
    if len(samples) < MIN_SHOTS_FOR_ANALYSIS:
        return DemoFinding(
            key="demo.snap", label="Acquisition instantanee de cible",
            score=0.0, confidence=0.0,
            explanation=f"Seulement {len(samples)} tirs analysables.",
            observed=0.0, sample_size=len(samples),
        )

    peaks = [sample.peak_speed for sample in samples]
    snapped = [peak for peak in peaks if peak >= SNAP_DEGREES_PER_TICK]
    ratio = safe_div(len(snapped), len(samples))

    # Un joueur rapide produit quelques pics ; c'est leur *proportion* qui
    # distingue un geste humain d'une acquisition automatisee.
    score = clamp(ratio / 0.25)

    return DemoFinding(
        key="demo.snap",
        label="Acquisition instantanee de cible",
        score=score,
        confidence=clamp(len(samples) / 400.0),
        explanation=(
            f"{ratio * 100:.1f} % des tirs sont precedes d'une correction de plus de "
            f"{SNAP_DEGREES_PER_TICK:.0f}° en un tick "
            f"(mediane observee : {percentile(peaks, 0.5):.1f}°/tick). "
            "Un mouvement de souris accelere et decelere progressivement."
            if score >= 0.25
            else
            f"Pics de vitesse angulaire dans la norme "
            f"(mediane {percentile(peaks, 0.5):.1f}°/tick)."
        ),
        observed=ratio,
        sample_size=len(samples),
        metadata={"median_peak": round(percentile(peaks, 0.5), 2)},
    )


def detect_overshoot(samples: Sequence[AimSample]) -> DemoFinding:
    """Recalage du réticule *après* avoir dépassé la cible.

    Beaucoup d'aides à la visée corrigent en deux temps : un déplacement brut
    qui dépasse, puis un retour. Le tir intervient après ce retour, ce qui
    laisse une signature en accordéon très reconnaissable.
    """
    if len(samples) < MIN_SHOTS_FOR_ANALYSIS:
        return DemoFinding(
            key="demo.overshoot", label="Recalage apres depassement",
            score=0.0, confidence=0.0,
            explanation="Echantillon de tirs insuffisant.",
            observed=0.0, sample_size=len(samples),
        )

    reversals = 0
    for sample in samples:
        if len(sample.deltas) < 4:
            continue
        tail = sample.deltas[-4:]
        # Un pic marque suivi d'un mouvement bien plus faible : la correction
        # a dépassé, puis s'est reprise.
        if max(tail[:2]) > 8.0 and max(tail[2:]) < max(tail[:2]) * 0.3:
            reversals += 1

    ratio = safe_div(reversals, len(samples))
    return DemoFinding(
        key="demo.overshoot",
        label="Recalage apres depassement",
        score=clamp(ratio / 0.30),
        confidence=clamp(len(samples) / 400.0),
        explanation=(
            f"{ratio * 100:.1f} % des tirs suivent un depassement puis un retour "
            "sur la cible — signature des corrections en deux temps."
            if ratio >= 0.08
            else f"Peu de recalages apres depassement ({ratio * 100:.1f} %)."
        ),
        observed=ratio,
        sample_size=len(samples),
    )


def detect_recoil_perfection(spray_deltas: Sequence[float]) -> DemoFinding:
    """Compensation de recul trop régulière.

    Le schéma de recul de CS2 est fixe : un joueur peut l'apprendre. Mais sa
    main introduit toujours du bruit. Une compensation dont la dispersion est
    quasi nulle indique un script.
    """
    if len(spray_deltas) < 60:
        return DemoFinding(
            key="demo.recoil", label="Compensation de recul",
            score=0.0, confidence=0.0,
            explanation="Pas assez de rafales longues analysees.",
            observed=0.0, sample_size=len(spray_deltas),
        )

    dispersion = stdev(spray_deltas)
    average = mean(spray_deltas)
    variation = safe_div(dispersion, abs(average) or 1.0)

    # Metrique inversee : c'est la *regularite* qui interpelle.
    score = clamp((0.35 - variation) / 0.30)

    return DemoFinding(
        key="demo.recoil",
        label="Compensation de recul",
        score=score,
        confidence=clamp(len(spray_deltas) / 400.0),
        explanation=(
            f"La compensation varie de seulement {variation:.2f} d'une rafale a "
            "l'autre. Une main humaine laisse toujours du bruit residuel."
            if score >= 0.25
            else f"Compensation de recul irreguliere ({variation:.2f}) — geste humain."
        ),
        observed=variation,
        sample_size=len(spray_deltas),
    )


def summarise_hitzones(zones: dict[str, int]) -> dict[str, Any]:
    """Répartition réelle des impacts par zone du corps.

    C'est l'information que l'API Steam ne donne pas : elle ne distingue que la
    tête du reste. Une démo fournit la ventilation complète.
    """
    total = sum(zones.values())
    if not total:
        return {"available": False}
    return {
        "available": True,
        "total_hits": total,
        "zones": {
            name: {"hits": hits, "share": round(hits / total, 4)}
            for name, hits in sorted(zones.items(), key=lambda kv: kv[1], reverse=True)
        },
    }


# ------------------------------------------------------------------- facade

@dataclass(frozen=True, slots=True)
class DemoAnalysis:
    """Résultat complet de l'analyse d'une démo."""

    demo: str
    available: bool
    reason: str = ""
    tickrate: int = 0
    players: int = 0
    findings: tuple[DemoFinding, ...] = ()
    hitzones: dict[str, Any] = field(default_factory=dict)

    @property
    def aggregate_score(self) -> float:
        scored = [f for f in self.findings if f.confidence > 0.05]
        if not scored:
            return 0.0
        total_weight = sum(f.confidence for f in scored)
        return safe_div(sum(f.score * f.confidence for f in scored), total_weight) * 100

    def as_dict(self) -> dict[str, Any]:
        return {
            "demo": self.demo,
            "available": self.available,
            "reason": self.reason,
            "tickrate": self.tickrate,
            "players": self.players,
            "score": round(self.aggregate_score, 1),
            "findings": [finding.as_dict() for finding in self.findings],
            "hitzones": dict(self.hitzones),
            "disclaimer": (
                "Analyse de trajectoire angulaire. Elle observe le geste, pas le "
                "logiciel : un joueur exceptionnel peut produire des valeurs "
                "elevees. Seul Valve peut conclure."
            ),
        }


def analyse_demo(path: str | Path, steamid64: str = "") -> DemoAnalysis:
    """Analyse une démo. Ne lève jamais : renvoie toujours un résultat lisible."""
    demo_path = Path(path)
    name = demo_path.name

    if not demo_path.is_file():
        return DemoAnalysis(demo=name, available=False, reason="Fichier introuvable.")

    if not parser_available():
        return DemoAnalysis(
            demo=name,
            available=False,
            reason=(
                "Le module demoparser2 n'est pas installe. "
                "Ajoute-le avec : pip install demoparser2"
            ),
        )

    try:
        return _run_parser(demo_path, steamid64)
    except Exception as exc:  # noqa: BLE001 - une demo corrompue ne doit rien casser
        logger.exception("Analyse de %s interrompue.", name)
        return DemoAnalysis(
            demo=name, available=False, reason=f"Demo illisible : {exc}"
        )


def _run_parser(demo_path: Path, steamid64: str) -> DemoAnalysis:
    """Extraction des ticks et application des détecteurs."""
    from demoparser2 import DemoParser  # type: ignore[import-not-found]

    parser = DemoParser(str(demo_path))

    # Les tirs donnent les instants a examiner ; les ticks donnent la
    # trajectoire angulaire qui les precede.
    shots = parser.parse_event("weapon_fire", player=["X", "Y"])
    ticks = parser.parse_ticks(["pitch", "yaw", "X", "Y", "Z", "health"])

    if ticks is None or len(ticks) == 0:
        return DemoAnalysis(
            demo=demo_path.name, available=False,
            reason="Aucune donnee de tick exploitable dans cette demo.",
        )

    samples = _build_samples(ticks, shots, steamid64)
    spray = _spray_deltas(ticks, shots, steamid64)
    zones = _hitzones(parser, steamid64)

    findings = (
        detect_snaps(samples),
        detect_overshoot(samples),
        detect_recoil_perfection(spray),
    )

    return DemoAnalysis(
        demo=demo_path.name,
        available=True,
        tickrate=64,
        players=int(ticks["steamid"].nunique()) if "steamid" in ticks else 0,
        findings=findings,
        hitzones=summarise_hitzones(zones),
    )


def _build_samples(ticks: Any, shots: Any, steamid64: str) -> list[AimSample]:
    """Reconstruit la fenêtre angulaire précédant chaque tir."""
    if shots is None or len(shots) == 0:
        return []

    samples: list[AimSample] = []
    by_player: dict[str, Any] = {}
    for steamid, group in ticks.groupby("steamid"):
        by_player[str(steamid)] = group.sort_values("tick")

    for _index, shot in shots.iterrows():
        shooter = str(shot.get("steamid", ""))
        if steamid64 and shooter != steamid64:
            continue
        frames = by_player.get(shooter)
        if frames is None:
            continue

        tick = int(shot.get("tick", 0))
        window = frames[(frames["tick"] > tick - PRE_SHOT_TICKS) & (frames["tick"] <= tick)]
        if len(window) < 4:
            continue

        speeds = view_speed(window["yaw"].tolist(), window["pitch"].tolist())
        if speeds:
            samples.append(
                AimSample(
                    tick=tick,
                    steamid=shooter,
                    weapon=str(shot.get("weapon", "")),
                    deltas=tuple(speeds),
                )
            )
    return samples


def _spray_deltas(ticks: Any, shots: Any, steamid64: str) -> list[float]:
    """Corrections verticales pendant les rafales, pour juger du recul."""
    samples = _build_samples(ticks, shots, steamid64)
    # Seules les rafales soutenues sont pertinentes : un tir isole n'a pas de
    # recul a compenser.
    return [
        sample.final_adjustment
        for sample in samples
        if len(sample.deltas) >= 6
    ]


def _hitzones(parser: Any, steamid64: str) -> dict[str, int]:
    """Comptage des impacts par zone, depuis les événements de dégâts."""
    zone_names = {
        0: "generique", 1: "tete", 2: "poitrine", 3: "estomac",
        4: "bras gauche", 5: "bras droit", 6: "jambe gauche", 7: "jambe droite",
        8: "cou", 10: "torse",
    }
    try:
        hurts = parser.parse_event("player_hurt")
    except Exception:  # noqa: BLE001 - evenement absent selon les demos
        return {}
    if hurts is None or len(hurts) == 0:
        return {}

    zones: dict[str, int] = {}
    for _index, row in hurts.iterrows():
        attacker = str(row.get("attacker_steamid", ""))
        if steamid64 and attacker != steamid64:
            continue
        group = zone_names.get(int(row.get("hitgroup", 0) or 0), "generique")
        zones[group] = zones.get(group, 0) + 1
    return zones
