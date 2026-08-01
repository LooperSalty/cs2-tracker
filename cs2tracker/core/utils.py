"""Petits utilitaires numériques et de temps, sans dépendance externe."""

from __future__ import annotations

import math
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence


def now_ts() -> float:
    """Timestamp UNIX (secondes, flottant)."""
    return time.time()


def now_iso() -> str:
    """Horodatage ISO-8601 UTC, suffixé ``Z``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ts_to_iso(ts: float | int | None) -> str | None:
    if not ts:
        return None
    try:
        return (
            datetime.fromtimestamp(float(ts), tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return None


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Division qui ne lève jamais ; renvoie ``default`` si dénominateur nul."""
    if not denominator:
        return default
    result = numerator / denominator
    if math.isnan(result) or math.isinf(result):
        return default
    return result


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def z_score(value: float, mean: float, stdev: float) -> float:
    """Écart-type normalisé ; 0 si l'écart-type est nul."""
    return safe_div(value - mean, stdev, default=0.0)


def logistic(x: float, midpoint: float = 0.0, steepness: float = 1.0) -> float:
    """Sigmoïde bornée (0, 1) — sert à convertir un z-score en suspicion."""
    exponent = -steepness * (x - midpoint)
    # Bornage pour éviter tout overflow sur des z-scores extrêmes.
    exponent = max(-60.0, min(60.0, exponent))
    return 1.0 / (1.0 + math.exp(exponent))


def mean(values: Sequence[float]) -> float:
    return safe_div(float(sum(values)), float(len(values)), 0.0)


def stdev(values: Sequence[float]) -> float:
    """Écart-type d'échantillon (n-1). 0.0 si moins de 2 valeurs."""
    count = len(values)
    if count < 2:
        return 0.0
    avg = mean(values)
    variance = sum((v - avg) ** 2 for v in values) / (count - 1)
    return math.sqrt(variance)


def coefficient_of_variation(values: Sequence[float]) -> float:
    """Écart-type rapporté à la moyenne — mesure de régularité sans unité."""
    avg = mean(values)
    if avg <= 0:
        return 0.0
    return stdev(values) / avg


def percentile(values: Sequence[float], q: float) -> float:
    """Percentile par interpolation linéaire. ``q`` dans [0, 1]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = clamp(q) * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[int(position)]
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def shrunk_rate(hits: float, trials: float, prior_rate: float, prior_weight: float) -> float:
    """Taux lissé bayésien (Beta-binomial) — évite les 100 % sur 3 tirs.

    Un joueur avec 2 kills dont 2 headshots n'a pas « 100 % de HS » : on tire
    l'estimation vers la moyenne de population tant que l'échantillon est petit.
    """
    if trials <= 0:
        return prior_rate
    return (hits + prior_rate * prior_weight) / (trials + prior_weight)


def sample_confidence(sample_size: float, full: float, minimum: float) -> float:
    """Confiance 0..1 croissante (log) avec la taille d'échantillon."""
    if sample_size <= minimum:
        return 0.0
    if sample_size >= full:
        return 1.0
    return clamp(math.log(sample_size / minimum) / math.log(full / minimum))


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(result) or math.isinf(result):
        return default
    return result


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def humanize_seconds(seconds: float) -> str:
    seconds = max(0.0, to_float(seconds))
    hours, remainder = divmod(int(seconds), 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return "".join(c if c.isalnum() else "-" for c in ascii_text).strip("-")


def chunked(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    """Découpe une séquence en tranches de ``size`` éléments maximum."""
    if size <= 0:
        raise ValueError("size doit etre > 0")
    for start in range(0, len(items), size):
        yield items[start : start + size]
