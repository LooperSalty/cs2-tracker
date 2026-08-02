"""Suivi des verdicts : le moteur avait-il raison ?

Sans boucle de rétroaction, un score anti-triche n'est qu'une opinion : rien ne
dit si les joueurs classés « HIGH » finissent effectivement bannis.

Ce module enregistre chaque verdict, puis reconsulte périodiquement le statut
VAC des profils concernés. La comparaison produit une **courbe de calibration
réelle** — le taux de bannissement observé par palier de score.

Un point de méthode : seuls comptent les bannissements **postérieurs** au
verdict. Un compte déjà banni au moment de l'analyse ne valide rien, puisque le
moteur voyait la sanction et l'a utilisée.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from cs2tracker.core.utils import now_iso, safe_div
from cs2tracker.storage.db import Database, rows_to_list

#: Paliers de la courbe de calibration : bornes basses inclusives.
SCORE_BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 30.0, "0-29"),
    (30.0, 50.0, "30-49"),
    (50.0, 70.0, "50-69"),
    (70.0, 85.0, "70-84"),
    (85.0, 100.01, "85-100"),
)

#: Un verdict n'est reverifie qu'au-dela de ce delai, en heures.
RECHECK_AFTER_HOURS = 24


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    """Résultat observé pour une tranche de score."""

    label: str
    verdicts: int
    banned_after: int
    still_pending: int

    @property
    def ban_rate(self) -> float:
        return safe_div(self.banned_after, self.verdicts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "range": self.label,
            "verdicts": self.verdicts,
            "banned_after": self.banned_after,
            "pending": self.still_pending,
            "ban_rate": round(self.ban_rate, 4),
        }


class AuditRepository:
    """Enregistre les verdicts et mesure leur justesse a posteriori."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- enregistrement ------------------------------------------------------
    def record(
        self,
        steamid64: str,
        *,
        analysed_at: str,
        score: float,
        verdict: str,
        bans_at_verdict: int,
    ) -> None:
        """Consigne un verdict rendu, avec l'état des sanctions à cet instant."""
        self._db.execute(
            """
            INSERT INTO verdict_audit (
                steamid64, analysed_at, score, verdict, bans_at_verdict, bans_now
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(steamid64, analysed_at) DO NOTHING
            """,
            (steamid64, analysed_at, score, verdict, bans_at_verdict, bans_at_verdict),
        )

    # --- reverification ------------------------------------------------------
    def due_for_recheck(self, limit: int = 100) -> list[str]:
        """SteamIDs à reconsulter : jamais bannis, et pas vus depuis un moment."""
        rows = self._db.query(
            """
            SELECT DISTINCT steamid64 FROM verdict_audit
            WHERE banned_at IS NULL
              AND (
                    last_checked_at IS NULL
                 OR julianday('now') - julianday(last_checked_at) > ?
              )
            ORDER BY score DESC
            LIMIT ?
            """,
            (RECHECK_AFTER_HOURS / 24.0, limit),
        )
        return [str(row["steamid64"]) for row in rows]

    def apply_check(self, steamid64: str, total_bans: int) -> bool:
        """Enregistre le résultat d'une reconsultation.

        Renvoie ``True`` si un bannissement **nouveau** vient d'être constaté,
        c'est-à-dire supérieur à celui connu au moment du verdict.
        """
        timestamp = now_iso()
        self._db.execute(
            """
            UPDATE verdict_audit
            SET last_checked_at = ?, checks = checks + 1, bans_now = ?
            WHERE steamid64 = ? AND banned_at IS NULL
            """,
            (timestamp, total_bans, steamid64),
        )

        newly_banned = self._db.execute(
            """
            UPDATE verdict_audit
            SET banned_at = ?
            WHERE steamid64 = ? AND banned_at IS NULL AND bans_now > bans_at_verdict
            """,
            (timestamp, steamid64),
        )
        # `execute` renvoie lastrowid ; on relit pour savoir si la ligne a change.
        row = self._db.query_one(
            "SELECT COUNT(*) AS n FROM verdict_audit "
            "WHERE steamid64 = ? AND banned_at = ?",
            (steamid64, timestamp),
        )
        del newly_banned
        return bool(row and int(row["n"]) > 0)

    # --- mesure --------------------------------------------------------------
    def calibration(self) -> list[dict[str, Any]]:
        """Taux de bannissement observé par tranche de score."""
        rows = self._db.query(
            """
            SELECT score,
                   CASE WHEN banned_at IS NOT NULL THEN 1 ELSE 0 END AS banned,
                   CASE WHEN last_checked_at IS NULL THEN 1 ELSE 0 END AS pending
            FROM verdict_audit
            """
        )

        buckets: list[CalibrationBucket] = []
        for low, high, label in SCORE_BUCKETS:
            inside = [r for r in rows if low <= float(r["score"]) < high]
            buckets.append(
                CalibrationBucket(
                    label=label,
                    verdicts=len(inside),
                    banned_after=sum(int(r["banned"]) for r in inside),
                    still_pending=sum(int(r["pending"]) for r in inside),
                )
            )
        return [bucket.as_dict() for bucket in buckets]

    def summary(self) -> dict[str, Any]:
        """Vue d'ensemble, avec l'avertissement qui s'impose sur la taille."""
        row = self._db.query_one(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN banned_at IS NOT NULL THEN 1 ELSE 0 END) AS banned,
                   SUM(CASE WHEN last_checked_at IS NULL THEN 1 ELSE 0 END) AS pending,
                   MIN(analysed_at) AS since
            FROM verdict_audit
            """
        )
        total = int(row["total"]) if row else 0
        banned = int(row["banned"] or 0) if row else 0

        buckets = self.calibration()
        # Une courbe correcte est monotone : plus le score monte, plus le taux
        # de bannissement doit monter. On le verifie plutot que de l'affirmer.
        rates = [b["ban_rate"] for b in buckets if b["verdicts"] > 0]
        monotonic = all(a <= b + 1e-9 for a, b in zip(rates, rates[1:]))

        return {
            "verdicts_tracked": total,
            "confirmed_banned": banned,
            "never_checked": int(row["pending"] or 0) if row else 0,
            "tracking_since": row["since"] if row else None,
            "overall_ban_rate": round(safe_div(banned, total), 4),
            "buckets": buckets,
            "monotonic": monotonic,
            # En dessous, aucune conclusion statistique n'est defendable.
            "statistically_usable": total >= 200,
            "note": (
                "Seuls les bannissements posterieurs au verdict sont comptes : "
                "un compte deja sanctionne au moment de l'analyse ne valide rien."
            ),
        }

    def recent_confirmations(self, limit: int = 25) -> list[dict[str, Any]]:
        """Verdicts confirmés par une sanction Valve survenue depuis."""
        rows = self._db.query(
            """
            SELECT a.steamid64, a.score, a.verdict, a.analysed_at, a.banned_at,
                   p.persona_name
            FROM verdict_audit a
            LEFT JOIN players p ON p.steamid64 = a.steamid64
            WHERE a.banned_at IS NOT NULL
            ORDER BY a.banned_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return rows_to_list(rows)

    def history_for(self, steamid64: str) -> list[dict[str, Any]]:
        rows = self._db.query(
            "SELECT * FROM verdict_audit WHERE steamid64 = ? ORDER BY analysed_at DESC",
            (steamid64,),
        )
        return rows_to_list(rows)


def bucket_for(score: float) -> str:
    for low, high, label in SCORE_BUCKETS:
        if low <= score < high:
            return label
    return SCORE_BUCKETS[-1][2]
