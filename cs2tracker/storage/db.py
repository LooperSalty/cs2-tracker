"""Accès SQLite : connexion unique, migrations, exécution paramétrée.

Toutes les requêtes sont paramétrées (``?``) : aucune valeur utilisateur n'est
concaténée dans du SQL.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

from cs2tracker.constants import DB_SCHEMA_VERSION
from cs2tracker.core.errors import StorageError
from cs2tracker.core.utils import now_iso
from cs2tracker.logging_setup import get_logger

logger = get_logger(__name__)

_SCHEMA_FILE = Path(__file__).with_name("schema.sql")


class Database:
    """Connexion SQLite partagée, protégée par un verrou (accès multi-thread)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None

    # --- cycle de vie --------------------------------------------------------
    def connect(self) -> None:
        if self._connection is not None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self._path, check_same_thread=False, timeout=10.0
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            self._connection = connection
        except sqlite3.Error as exc:
            raise StorageError(f"Ouverture de la base impossible: {exc}") from exc
        self._migrate()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _require(self) -> sqlite3.Connection:
        if self._connection is None:
            self.connect()
        if self._connection is None:  # pragma: no cover - défensif
            raise StorageError("Base non initialisee")
        return self._connection

    # --- migrations ----------------------------------------------------------
    def _migrate(self) -> None:
        try:
            script = _SCHEMA_FILE.read_text(encoding="utf-8")
        except OSError as exc:
            raise StorageError(f"Schema SQL introuvable: {exc}") from exc

        with self._lock:
            connection = self._require()
            try:
                connection.executescript(script)
                current = connection.execute(
                    "SELECT MAX(version) AS version FROM schema_version"
                ).fetchone()
                if current is None or current["version"] is None:
                    connection.execute(
                        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                        (DB_SCHEMA_VERSION, now_iso()),
                    )
                connection.commit()
            except sqlite3.Error as exc:
                connection.rollback()
                raise StorageError(f"Migration echouee: {exc}") from exc
        logger.info("Base prete: %s", self._path)

    # --- exécution -----------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Exécute une écriture et renvoie le ``lastrowid``."""
        with self._lock:
            connection = self._require()
            try:
                cursor = connection.execute(sql, tuple(params))
                connection.commit()
                return int(cursor.lastrowid or 0)
            except sqlite3.Error as exc:
                connection.rollback()
                raise StorageError(f"Ecriture echouee: {exc}") from exc

    def execute_many(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        with self._lock:
            connection = self._require()
            try:
                connection.executemany(sql, [tuple(row) for row in rows])
                connection.commit()
            except sqlite3.Error as exc:
                connection.rollback()
                raise StorageError(f"Ecriture groupee echouee: {exc}") from exc

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            connection = self._require()
            try:
                return connection.execute(sql, tuple(params)).fetchall()
            except sqlite3.Error as exc:
                raise StorageError(f"Lecture echouee: {exc}") from exc

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # --- diagnostic ----------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        tables = ("players", "stat_snapshots", "analyses", "matches", "match_players")
        counts: dict[str, int] = {}
        for table in tables:
            row = self.query_one(f"SELECT COUNT(*) AS n FROM {table}")  # noqa: S608
            counts[table] = int(row["n"]) if row else 0
        size = self._path.stat().st_size if self._path.is_file() else 0
        return {
            "path": str(self._path),
            "size_bytes": size,
            "schema_version": DB_SCHEMA_VERSION,
            "rows": counts,
        }


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_list(rows: Sequence[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
