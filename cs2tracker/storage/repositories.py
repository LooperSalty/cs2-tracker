"""Dépôts d'accès aux données : une classe par agrégat métier."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from cs2tracker.anticheat.engine import AnalysisResult
from cs2tracker.core.models import PlayerProfile
from cs2tracker.core.utils import now_iso
from cs2tracker.gsi.tracker import LivePlayerMetrics
from cs2tracker.storage.db import Database, row_to_dict, rows_to_list


class PlayerRepository:
    """Joueurs connus du tracker (favoris, notes, dernière vue)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert_from_profile(self, profile: PlayerProfile) -> str:
        steamid = str(profile.identity.get("steamid64", ""))
        if not steamid:
            return ""
        summary = profile.summary
        timestamp = now_iso()
        self._db.execute(
            """
            INSERT INTO players (
                steamid64, persona_name, avatar_url, profile_url, country_code,
                account_created, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(steamid64) DO UPDATE SET
                persona_name  = excluded.persona_name,
                avatar_url    = excluded.avatar_url,
                profile_url   = excluded.profile_url,
                country_code  = excluded.country_code,
                account_created = excluded.account_created,
                last_seen_at  = excluded.last_seen_at
            """,
            (
                steamid,
                summary.persona_name if summary else "",
                (summary.avatar_full or summary.avatar) if summary else "",
                summary.profile_url if summary else "",
                summary.country_code if summary else None,
                summary.time_created if summary else None,
                timestamp,
                timestamp,
            ),
        )
        return steamid

    def ensure(self, steamid64: str, name: str = "") -> None:
        timestamp = now_iso()
        self._db.execute(
            """
            INSERT INTO players (steamid64, persona_name, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(steamid64) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (steamid64, name, timestamp, timestamp),
        )

    def get(self, steamid64: str) -> dict[str, Any] | None:
        return row_to_dict(
            self._db.query_one("SELECT * FROM players WHERE steamid64 = ?", (steamid64,))
        )

    def list_all(self, *, favourites_only: bool = False, limit: int = 200) -> list[dict[str, Any]]:
        if favourites_only:
            rows = self._db.query(
                "SELECT * FROM players WHERE is_favourite = 1 "
                "ORDER BY last_seen_at DESC LIMIT ?",
                (limit,),
            )
        else:
            rows = self._db.query(
                "SELECT * FROM players ORDER BY last_seen_at DESC LIMIT ?", (limit,)
            )
        return rows_to_list(rows)

    def set_favourite(self, steamid64: str, favourite: bool) -> None:
        self._db.execute(
            "UPDATE players SET is_favourite = ? WHERE steamid64 = ?",
            (1 if favourite else 0, steamid64),
        )

    def set_notes(self, steamid64: str, notes: str) -> None:
        self._db.execute(
            "UPDATE players SET notes = ? WHERE steamid64 = ?", (notes, steamid64)
        )

    def delete(self, steamid64: str) -> None:
        self._db.execute("DELETE FROM players WHERE steamid64 = ?", (steamid64,))


class SnapshotRepository:
    """Historique des statistiques, pour tracer la progression dans le temps."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, profile: PlayerProfile) -> int:
        stats = profile.stats
        if stats is None:
            return 0
        steamid = str(profile.identity.get("steamid64", ""))
        return self._db.execute(
            """
            INSERT INTO stat_snapshots (
                steamid64, captured_at, kills, deaths, rounds_played, matches_played,
                matches_won, time_played, headshot_kills, shots_fired, shots_hit,
                damage_done, mvps, kd_ratio, headshot_rate, accuracy, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                steamid,
                now_iso(),
                stats.total_kills,
                stats.total_deaths,
                stats.total_rounds_played,
                stats.total_matches_played,
                stats.total_matches_won,
                stats.total_time_played,
                stats.total_kills_headshot,
                stats.total_shots_fired,
                stats.total_shots_hit,
                stats.total_damage_done,
                stats.total_mvps,
                stats.kd_ratio,
                stats.headshot_rate,
                stats.accuracy,
                json.dumps(stats.as_dict(), ensure_ascii=False),
            ),
        )

    def history(self, steamid64: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.query(
            """
            SELECT id, captured_at, kills, deaths, rounds_played, matches_played,
                   matches_won, time_played, headshot_kills, shots_fired, shots_hit,
                   damage_done, mvps, kd_ratio, headshot_rate, accuracy
            FROM stat_snapshots
            WHERE steamid64 = ?
            ORDER BY captured_at DESC
            LIMIT ?
            """,
            (steamid64, limit),
        )
        return rows_to_list(rows)

    def latest(self, steamid64: str) -> dict[str, Any] | None:
        return row_to_dict(
            self._db.query_one(
                "SELECT * FROM stat_snapshots WHERE steamid64 = ? "
                "ORDER BY captured_at DESC LIMIT 1",
                (steamid64,),
            )
        )

    def progression(self, steamid64: str, limit: int = 2) -> dict[str, Any] | None:
        """Différentiel entre les deux derniers instantanés."""
        rows = self.history(steamid64, limit=max(2, limit))
        if len(rows) < 2:
            return None
        newest, previous = rows[0], rows[1]
        delta_rounds = newest["rounds_played"] - previous["rounds_played"]
        delta_kills = newest["kills"] - previous["kills"]
        delta_deaths = newest["deaths"] - previous["deaths"]
        return {
            "from": previous["captured_at"],
            "to": newest["captured_at"],
            "rounds": delta_rounds,
            "kills": delta_kills,
            "deaths": delta_deaths,
            "kd": round(delta_kills / delta_deaths, 3) if delta_deaths else None,
            "kills_per_round": (
                round(delta_kills / delta_rounds, 3) if delta_rounds else None
            ),
        }


class AnalysisRepository:
    """Historique des analyses anti-triche."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, result: AnalysisResult) -> int:
        return self._db.execute(
            """
            INSERT INTO analyses (
                steamid64, analysed_at, score, verdict, confidence,
                confirmed_ban, report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.steamid,
                result.analysed_at,
                result.suspicion_score,
                result.verdict,
                result.global_confidence,
                1 if result.has_confirmed_ban else 0,
                json.dumps(
                    result.as_dict(include_features=False), ensure_ascii=False
                ),
            ),
        )

    def history(self, steamid64: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.query(
            """
            SELECT id, analysed_at, score, verdict, confidence, confirmed_ban
            FROM analyses WHERE steamid64 = ?
            ORDER BY analysed_at DESC LIMIT ?
            """,
            (steamid64, limit),
        )
        return rows_to_list(rows)

    def latest(self, steamid64: str) -> dict[str, Any] | None:
        row = self._db.query_one(
            "SELECT * FROM analyses WHERE steamid64 = ? ORDER BY analysed_at DESC LIMIT 1",
            (steamid64,),
        )
        if row is None:
            return None
        data = dict(row)
        data["report"] = json.loads(data.pop("report_json", "{}") or "{}")
        return data

    def most_suspicious(self, limit: int = 25) -> list[dict[str, Any]]:
        rows = self._db.query(
            """
            SELECT a.steamid64, p.persona_name, MAX(a.score) AS score,
                   a.verdict, a.analysed_at, a.confirmed_ban
            FROM analyses a
            LEFT JOIN players p ON p.steamid64 = a.steamid64
            GROUP BY a.steamid64
            ORDER BY score DESC
            LIMIT ?
            """,
            (limit,),
        )
        return rows_to_list(rows)


class MatchRepository:
    """Matchs observés en direct via le GSI."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, map_name: str, mode: str, summary: Mapping[str, Any]) -> int:
        return self._db.execute(
            """
            INSERT INTO matches (map_name, mode, started_at, summary_json)
            VALUES (?, ?, ?, ?)
            """,
            (map_name, mode, now_iso(), json.dumps(dict(summary), ensure_ascii=False)),
        )

    def finish(
        self,
        match_id: int,
        *,
        score_ct: int,
        score_t: int,
        rounds_total: int,
        summary: Mapping[str, Any],
    ) -> None:
        self._db.execute(
            """
            UPDATE matches
            SET ended_at = ?, score_ct = ?, score_t = ?, rounds_total = ?,
                summary_json = ?
            WHERE id = ?
            """,
            (
                now_iso(),
                score_ct,
                score_t,
                rounds_total,
                json.dumps(dict(summary), ensure_ascii=False),
                match_id,
            ),
        )

    def save_players(
        self, match_id: int, metrics: Sequence[LivePlayerMetrics]
    ) -> None:
        rows = [
            (
                match_id,
                m.steamid,
                m.name,
                m.team,
                m.total_kills,
                m.total_deaths,
                m.total_assists,
                m.total_mvps,
                m.adr,
                m.live_headshot_rate,
                m.rounds_observed,
                json.dumps(m.as_dict(), ensure_ascii=False),
            )
            for m in metrics
        ]
        if not rows:
            return
        self._db.execute_many(
            """
            INSERT INTO match_players (
                match_id, steamid64, name, team, kills, deaths, assists, mvps,
                adr, headshot_rate, rounds, metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, steamid64) DO UPDATE SET
                kills = excluded.kills, deaths = excluded.deaths,
                assists = excluded.assists, mvps = excluded.mvps,
                adr = excluded.adr, headshot_rate = excluded.headshot_rate,
                rounds = excluded.rounds, metrics_json = excluded.metrics_json
            """,
            rows,
        )

    def save_round(
        self, match_id: int, round_number: int, winner: str, details: Mapping[str, Any]
    ) -> None:
        self._db.execute(
            """
            INSERT INTO match_rounds (match_id, round_number, winner, ended_at, details_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(match_id, round_number) DO UPDATE SET
                winner = excluded.winner, details_json = excluded.details_json
            """,
            (
                match_id,
                round_number,
                winner,
                now_iso(),
                json.dumps(dict(details), ensure_ascii=False),
            ),
        )

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.query(
            "SELECT * FROM matches ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        matches = rows_to_list(rows)
        for match in matches:
            match["summary"] = json.loads(match.pop("summary_json", "{}") or "{}")
        return matches

    def get(self, match_id: int) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM matches WHERE id = ?", (match_id,))
        if row is None:
            return None
        match = dict(row)
        match["summary"] = json.loads(match.pop("summary_json", "{}") or "{}")
        match["players"] = self.players_of(match_id)
        match["rounds"] = self.rounds_of(match_id)
        return match

    def players_of(self, match_id: int) -> list[dict[str, Any]]:
        rows = self._db.query(
            "SELECT * FROM match_players WHERE match_id = ? ORDER BY kills DESC",
            (match_id,),
        )
        players = rows_to_list(rows)
        for player in players:
            player["metrics"] = json.loads(player.pop("metrics_json", "{}") or "{}")
        return players

    def rounds_of(self, match_id: int) -> list[dict[str, Any]]:
        rows = self._db.query(
            "SELECT * FROM match_rounds WHERE match_id = ? ORDER BY round_number",
            (match_id,),
        )
        rounds = rows_to_list(rows)
        for entry in rounds:
            entry["details"] = json.loads(entry.pop("details_json", "{}") or "{}")
        return rounds

    def player_history(self, steamid64: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.query(
            """
            SELECT mp.*, m.map_name, m.mode, m.started_at, m.score_ct, m.score_t
            FROM match_players mp
            JOIN matches m ON m.id = mp.match_id
            WHERE mp.steamid64 = ?
            ORDER BY m.started_at DESC
            LIMIT ?
            """,
            (steamid64, limit),
        )
        history = rows_to_list(rows)
        for entry in history:
            entry.pop("metrics_json", None)
        return history
