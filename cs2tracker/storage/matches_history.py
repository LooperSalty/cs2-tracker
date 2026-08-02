"""Performances match par match, et graphe des compagnons de jeu.

**Pourquoi ce module existe.** Steam ne renvoie que des cumuls depuis la
création du compte, plus un unique « dernier match ». Un joueur à 8 000 manches
a une moyenne que plus rien ne fait bouger : un mois de triche s'y dissout.

Enregistrer chaque match séparément transforme un point en **distribution**.
On peut alors mesurer ce qu'aucune moyenne ne montre : la régularité entre
matchs, les parties isolées aberrantes, et — via le graphe des coéquipiers —
les groupes dont tous les membres sont suspects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from cs2tracker.core.utils import (
    coefficient_of_variation,
    mean,
    now_iso,
    percentile,
    safe_div,
    stdev,
)
from cs2tracker.storage.db import Database, rows_to_list

#: En deçà, une distribution n'a pas de sens.
MIN_MATCHES_FOR_DISTRIBUTION = 5


@dataclass(frozen=True, slots=True)
class MatchRecord:
    """Un match joué par un joueur, quelle qu'en soit la source."""

    steamid64: str
    played_at: str
    source: str
    external_id: str
    map_name: str = ""
    rounds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    headshots: int = 0
    damage: int = 0
    mvps: int = 0
    won: bool | None = None
    details: Mapping[str, Any] | None = None

    @property
    def kills_per_round(self) -> float:
        return safe_div(self.kills, self.rounds)

    @property
    def adr(self) -> float:
        return safe_div(self.damage, self.rounds)

    @property
    def headshot_rate(self) -> float:
        return safe_div(self.headshots, self.kills)


class PlayerMatchRepository:
    """Historique de matchs et statistiques dérivées."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, record: MatchRecord) -> None:
        self._db.execute(
            """
            INSERT INTO player_matches (
                steamid64, played_at, source, external_id, map_name, rounds,
                kills, deaths, assists, headshots, damage, mvps, won, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(steamid64, source, external_id) DO UPDATE SET
                rounds = excluded.rounds, kills = excluded.kills,
                deaths = excluded.deaths, assists = excluded.assists,
                headshots = excluded.headshots, damage = excluded.damage,
                mvps = excluded.mvps, won = excluded.won,
                details_json = excluded.details_json
            """,
            (
                record.steamid64, record.played_at, record.source, record.external_id,
                record.map_name, record.rounds, record.kills, record.deaths,
                record.assists, record.headshots, record.damage, record.mvps,
                None if record.won is None else int(record.won),
                json.dumps(dict(record.details or {}), ensure_ascii=False),
            ),
        )

    def save_many(self, records: Iterable[MatchRecord]) -> int:
        count = 0
        for record in records:
            self.save(record)
            count += 1
        return count

    def list_for(self, steamid64: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._db.query(
            """
            SELECT * FROM player_matches WHERE steamid64 = ?
            ORDER BY played_at DESC LIMIT ?
            """,
            (steamid64, limit),
        )
        matches = rows_to_list(rows)
        for match in matches:
            match["details"] = json.loads(match.pop("details_json", "{}") or "{}")
        return matches

    def distribution(self, steamid64: str, limit: int = 200) -> dict[str, Any] | None:
        """Statistiques de dispersion sur l'ensemble des matchs enregistrés.

        C'est là que se voit ce qu'une moyenne à vie masque : un joueur dont
        chaque match se ressemble trop, ou dont quelques parties se détachent
        radicalement du reste.
        """
        matches = self.list_for(steamid64, limit=limit)
        if len(matches) < MIN_MATCHES_FOR_DISTRIBUTION:
            return None

        def series(key: str, divisor: str | None = None) -> list[float]:
            values = []
            for match in matches:
                if divisor:
                    base = float(match.get(divisor) or 0)
                    if base <= 0:
                        continue
                    values.append(float(match.get(key) or 0) / base)
                else:
                    values.append(float(match.get(key) or 0))
            return values

        kpr = series("kills", "rounds")
        adr = series("damage", "rounds")
        hs = [
            float(m["headshots"]) / float(m["kills"])
            for m in matches
            if (m.get("kills") or 0) > 0
        ]

        wins = [m["won"] for m in matches if m.get("won") is not None]

        return {
            "matches": len(matches),
            "from": matches[-1]["played_at"],
            "to": matches[0]["played_at"],
            "kills_per_round": _describe(kpr),
            "adr": _describe(adr),
            "headshot_rate": _describe(hs),
            "win_rate": round(safe_div(sum(wins), len(wins)), 4) if wins else None,
            # Une regularite trop forte entre matchs est aussi atypique qu'une
            # moyenne trop haute : elle indique un plancher de performance.
            "consistency": {
                "kpr_variation": round(coefficient_of_variation(kpr), 4),
                "adr_variation": round(coefficient_of_variation(adr), 4),
            },
        }

    def outliers(self, steamid64: str, limit: int = 200) -> list[dict[str, Any]]:
        """Matchs dont la performance s'écarte nettement du reste."""
        matches = self.list_for(steamid64, limit=limit)
        if len(matches) < MIN_MATCHES_FOR_DISTRIBUTION:
            return []

        ratios = [
            (m, safe_div(m["kills"], m["rounds"]))
            for m in matches
            if (m.get("rounds") or 0) > 0
        ]
        values = [value for _match, value in ratios]
        average = mean(values)
        dispersion = stdev(values)
        if dispersion <= 0:
            return []

        flagged = []
        for match, value in ratios:
            z = (value - average) / dispersion
            if z >= 2.0:
                flagged.append(
                    {
                        "played_at": match["played_at"],
                        "map": match["map_name"],
                        "kills": match["kills"],
                        "rounds": match["rounds"],
                        "kills_per_round": round(value, 3),
                        "z_score": round(z, 2),
                    }
                )
        return sorted(flagged, key=lambda entry: entry["z_score"], reverse=True)


def _describe(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "mean": round(mean(values), 4),
        "stdev": round(stdev(values), 4),
        "min": round(min(values), 4),
        "p25": round(percentile(values, 0.25), 4),
        "median": round(percentile(values, 0.5), 4),
        "p75": round(percentile(values, 0.75), 4),
        "max": round(max(values), 4),
    }


class TeammateRepository:
    """Graphe des joueurs croisés, pour repérer les groupes."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def record_lobby(self, players: Sequence[tuple[str, str]]) -> None:
        """Enregistre les paires d'un lobby.

        ``players`` est une suite de ``(steamid, equipe)``. On note à la fois la
        co-présence et l'appartenance à la même équipe : jouer *contre*
        quelqu'un régulièrement n'a pas le même sens que jouer *avec* lui.
        """
        timestamp = now_iso()
        for index, (steamid, team) in enumerate(players):
            for other_id, other_team in players[index + 1 :]:
                if not steamid or not other_id or steamid == other_id:
                    continue
                same_team = 1 if team and team == other_team else 0
                # La relation est symetrique : on ecrit les deux sens pour
                # pouvoir interroger n'importe quel joueur directement.
                for a, b in ((steamid, other_id), (other_id, steamid)):
                    self._db.execute(
                        """
                        INSERT INTO teammates (
                            steamid64, teammate_id, matches, same_team,
                            first_seen_at, last_seen_at
                        ) VALUES (?, ?, 1, ?, ?, ?)
                        ON CONFLICT(steamid64, teammate_id) DO UPDATE SET
                            matches = matches + 1,
                            same_team = same_team + excluded.same_team,
                            last_seen_at = excluded.last_seen_at
                        """,
                        (a, b, same_team, timestamp, timestamp),
                    )

    def companions(self, steamid64: str, min_matches: int = 2) -> list[dict[str, Any]]:
        rows = self._db.query(
            """
            SELECT t.teammate_id, t.matches, t.same_team, t.last_seen_at,
                   p.persona_name,
                   (SELECT MAX(score) FROM analyses a
                     WHERE a.steamid64 = t.teammate_id) AS suspicion
            FROM teammates t
            LEFT JOIN players p ON p.steamid64 = t.teammate_id
            WHERE t.steamid64 = ? AND t.matches >= ?
            ORDER BY t.matches DESC
            """,
            (steamid64, min_matches),
        )
        return rows_to_list(rows)

    def group_risk(self, steamid64: str, min_matches: int = 2) -> dict[str, Any]:
        """Score de risque du cercle de jeu.

        Un joueur peut croiser un tricheur par hasard. En revanche, un cercle
        rapproché dont *plusieurs* membres sont suspects ne relève plus du
        hasard — c'est un signal qu'aucune analyse individuelle ne produit.
        """
        companions = self.companions(steamid64, min_matches=min_matches)
        analysed = [c for c in companions if c.get("suspicion") is not None]

        if not analysed:
            return {
                "companions": len(companions),
                "analysed": 0,
                "available": False,
                "reason": (
                    "Aucun compagnon de jeu n'a encore ete analyse. "
                    "Analyse quelques lobbies pour alimenter le graphe."
                ),
            }

        scores = [float(c["suspicion"]) for c in analysed]
        flagged = [score for score in scores if score >= 70]

        return {
            "companions": len(companions),
            "analysed": len(analysed),
            "available": True,
            "average_suspicion": round(mean(scores), 1),
            "max_suspicion": round(max(scores), 1),
            "flagged_companions": len(flagged),
            "flagged_ratio": round(safe_div(len(flagged), len(analysed)), 3),
            "top": sorted(
                (
                    {
                        "steamid64": c["teammate_id"],
                        "name": c.get("persona_name") or c["teammate_id"],
                        "matches": c["matches"],
                        "same_team": c["same_team"],
                        "suspicion": round(float(c["suspicion"]), 1),
                    }
                    for c in analysed
                ),
                key=lambda entry: entry["suspicion"],
                reverse=True,
            )[:10],
        }

    def clusters(self, min_matches: int = 3, min_score: float = 60.0) -> list[dict[str, Any]]:
        """Groupes de joueurs suspects qui jouent régulièrement ensemble.

        Composantes connexes du graphe restreint aux comptes déjà signalés.
        """
        rows = self._db.query(
            """
            SELECT DISTINCT t.steamid64, t.teammate_id
            FROM teammates t
            WHERE t.matches >= ?
              AND (SELECT MAX(score) FROM analyses a
                    WHERE a.steamid64 = t.steamid64) >= ?
              AND (SELECT MAX(score) FROM analyses b
                    WHERE b.steamid64 = t.teammate_id) >= ?
            """,
            (min_matches, min_score, min_score),
        )

        # Union-find : regroupe les comptes relies entre eux.
        parent: dict[str, str] = {}

        def find(node: str) -> str:
            parent.setdefault(node, node)
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(a: str, b: str) -> None:
            root_a, root_b = find(a), find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        for row in rows:
            union(str(row["steamid64"]), str(row["teammate_id"]))

        groups: dict[str, list[str]] = {}
        for node in parent:
            groups.setdefault(find(node), []).append(node)

        return sorted(
            (
                {"members": sorted(members), "size": len(members)}
                for members in groups.values()
                if len(members) >= 2
            ),
            key=lambda group: group["size"],
            reverse=True,
        )
