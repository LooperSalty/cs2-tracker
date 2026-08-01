"""Mise en forme lisible d'un rapport d'analyse (console, UI, export texte)."""

from __future__ import annotations

from typing import Any, Sequence

from cs2tracker.anticheat.engine import AnalysisResult, DISCLAIMER
from cs2tracker.anticheat.signals import Severity, Signal

_VERDICT_COLORS = {
    "CLEAN": "#3fb950",
    "LOW": "#9ecbff",
    "MODERATE": "#d29922",
    "HIGH": "#f85149",
    "CRITICAL": "#ff5c5c",
    "INDETERMINE": "#8b949e",
}

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def verdict_color(verdict: str) -> str:
    return _VERDICT_COLORS.get(verdict, "#8b949e")


def sorted_signals(signals: Sequence[Signal]) -> tuple[Signal, ...]:
    return tuple(
        sorted(
            signals,
            key=lambda s: (_SEVERITY_ORDER[s.severity], -s.contribution),
        )
    )


def summary_line(result: AnalysisResult) -> str:
    return (
        f"{result.name} — score {result.suspicion_score:.0f}/100 "
        f"({result.verdict}, confiance {result.global_confidence * 100:.0f} %)"
    )


def recommendation(result: AnalysisResult) -> str:
    """Conseil d'action, calibré pour ne jamais encourager l'accusation hâtive."""
    if result.has_confirmed_ban:
        return (
            "Sanction Valve deja enregistree sur ce compte. Aucune action requise de "
            "ta part : l'information est publique et factuelle."
        )
    if result.is_inconclusive:
        return (
            "Donnees trop maigres pour se prononcer (profil prive ou echantillon "
            "insuffisant). Observe davantage de manches avant toute conclusion."
        )
    if result.verdict in {"HIGH", "CRITICAL"}:
        return (
            "Plusieurs indicateurs independants concordent. Utilise le signalement "
            "en jeu (touche par defaut : clic droit sur le joueur > Signaler) et "
            "laisse Overwatch/VAC trancher. N'accuse personne publiquement sur la base "
            "de ce score."
        )
    if result.verdict == "MODERATE":
        return (
            "Quelques ecarts notables, compatibles avec un tres bon joueur ou un smurf. "
            "Continue d'observer ; un signalement n'est justifie qu'en cas de "
            "comportement flagrant en jeu."
        )
    return "Aucune action recommandee : le profil ne se distingue pas de la population."


def to_text(result: AnalysisResult, *, max_signals: int = 12) -> str:
    """Rapport texte complet, utilisable en console ou en export."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"RAPPORT D'ANALYSE — {result.name}")
    lines.append(f"SteamID64 : {result.steamid}")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Score de suspicion : {result.suspicion_score:5.1f} / 100")
    lines.append(f"Verdict            : {result.verdict} — {result.verdict_label}")
    lines.append(f"Confiance globale  : {result.global_confidence * 100:.0f} %")
    lines.append("")

    sources = ", ".join(
        name for name, available in result.data_sources.items() if available
    )
    lines.append(f"Sources exploitees : {sources or 'aucune'}")
    lines.append("")

    if result.categories:
        lines.append("--- Par famille d'indicateurs " + "-" * 42)
        for category in result.categories:
            bar = _bar(category.score)
            lines.append(
                f"  {category.category:<14} {bar} {category.score * 100:5.1f} "
                f"(confiance {category.confidence * 100:3.0f} %, "
                f"{category.signal_count} signal/aux)"
            )
        lines.append("")

    lines.append("--- Indicateurs les plus contributifs " + "-" * 34)
    for signal in sorted_signals(result.signals)[:max_signals]:
        if signal.confidence <= 0:
            continue
        lines.append(f"  [{signal.severity.value.upper():^8}] {signal.label}")
        lines.append(f"      {signal.explanation}")
        if signal.z_score is not None and abs(signal.z_score) > 0.1:
            lines.append(
                f"      (mesure {signal.observed:.3f} / reference "
                f"{signal.expected if signal.expected is not None else float('nan'):.3f} — "
                f"z = {signal.z_score:+.2f}, echantillon {signal.sample_size})"
            )
        lines.append("")

    lines.append("--- Recommandation " + "-" * 52)
    lines.append(f"  {recommendation(result)}")
    lines.append("")
    lines.append("--- Avertissement " + "-" * 53)
    for chunk in _wrap(DISCLAIMER, 70):
        lines.append(f"  {chunk}")
    lines.append("=" * 72)
    return "\n".join(lines)


def to_compact_dict(result: AnalysisResult) -> dict[str, Any]:
    """Version allégée pour les listes (lobby, historique)."""
    return {
        "steamid": result.steamid,
        "name": result.name,
        "score": round(result.suspicion_score, 1),
        "verdict": result.verdict,
        "color": verdict_color(result.verdict),
        "confidence": round(result.global_confidence, 3),
        "has_confirmed_ban": result.has_confirmed_ban,
        "top_reason": (
            result.highlights[0].label if result.highlights else "aucun signal notable"
        ),
    }


def _bar(ratio: float, width: int = 20) -> str:
    filled = int(round(max(0.0, min(1.0, ratio)) * width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        if length + len(word) + len(current) > width and current:
            lines.append(" ".join(current))
            current, length = [word], len(word)
        else:
            current.append(word)
            length += len(word)
    if current:
        lines.append(" ".join(current))
    return lines
