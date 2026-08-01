"""Page « Temps réel » : état de la partie, scoreboard et flux d'événements."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cs2tracker.ui import theme
from cs2tracker.ui.api_client import ApiClient
from cs2tracker.ui.widgets import Badge, Card, DataTable, SectionHeader, StatTile, tile_row
from cs2tracker.ui.workers import PollingTimer, run_async

#: Cadence de rafraîchissement de l'état de jeu (ms).
POLL_INTERVAL_MS = 1_000
#: Nombre d'événements conservés dans le journal affiché.
MAX_EVENT_ROWS = 300

_EVENT_LABELS = {
    "kill": ("Elimination", theme.SUCCESS),
    "headshot_kill": ("Headshot", theme.ACCENT),
    "multi_kill": ("Multi-kill", theme.ACCENT_HOVER),
    "death": ("Mort", theme.DANGER),
    "assist": ("Assistance", theme.INFO),
    "mvp": ("MVP", theme.ACCENT),
    "round_start": ("Debut de manche", theme.TEXT_SECONDARY),
    "round_freeze": ("Freezetime", theme.TEXT_MUTED),
    "round_end": ("Fin de manche", theme.TEXT_SECONDARY),
    "bomb_planted": ("Bombe posee", theme.WARNING),
    "bomb_defused": ("Bombe desamorcee", theme.CT_BLUE),
    "bomb_exploded": ("Explosion", theme.DANGER),
    "match_start": ("Debut de match", theme.SUCCESS),
    "match_end": ("Fin de match", theme.INFO),
    "map_change": ("Changement de carte", theme.INFO),
    "weapon_switch": ("Changement d'arme", theme.TEXT_MUTED),
    "damage_taken": ("Degats subis", theme.WARNING),
    "flashed": ("Aveugle", theme.T_YELLOW),
    "low_health": ("Sante critique", theme.DANGER),
    "connection": ("Liaison GSI", theme.SUCCESS),
}


class LivePage(QWidget):
    """Suivi en direct de la partie via le Game State Integration."""

    status_message = Signal(str)
    analyse_requested = Signal(str)

    def __init__(self, client: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._last_sequence = 0
        self._build()
        self._state_timer = PollingTimer(
            POLL_INTERVAL_MS, self._fetch_all, self._on_data, self._on_error, self
        )

    # --- construction --------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(
            SectionHeader(
                "Partie en direct",
                "Alimente par le Game State Integration officiel de CS2. Les donnees "
                "de tous les joueurs ne sont transmises qu'en mode spectateur ou GOTV.",
            )
        )
        layout.addWidget(self._build_status_bar())
        layout.addWidget(self._build_tiles())

        split = QHBoxLayout()
        split.setSpacing(14)
        split.addWidget(self._build_scoreboard(), stretch=3)
        split.addWidget(self._build_event_feed(), stretch=2)
        layout.addLayout(split, stretch=1)

    def _build_status_bar(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(10)

        self._connection_badge = Badge("DECONNECTE", theme.TEXT_MUTED)
        self._map_label = QLabel("Aucune partie detectee")
        self._map_label.setObjectName("PageSubtitle")
        self._score_label = QLabel("")
        self._score_label.setStyleSheet("font-size: 16px; font-weight: 700;")

        self._toggle_button = QPushButton("Demarrer le suivi")
        self._toggle_button.setObjectName("Primary")
        self._toggle_button.clicked.connect(self._toggle)

        self._analyse_lobby_button = QPushButton("Analyser le lobby")
        self._analyse_lobby_button.clicked.connect(self._analyse_lobby)

        row.addWidget(self._connection_badge)
        row.addWidget(self._map_label, stretch=1)
        row.addWidget(self._score_label)
        row.addWidget(self._analyse_lobby_button)
        row.addWidget(self._toggle_button)
        card.body().addLayout(row)
        return card

    def _build_tiles(self) -> QWidget:
        self._tiles = {
            "round": StatTile("Manche"),
            "phase": StatTile("Phase"),
            "health": StatTile("Sante"),
            "money": StatTile("Argent"),
            "kills": StatTile("Kills (manche)"),
            "kd": StatTile("K/D du match"),
            "adr": StatTile("ADR observe"),
        }
        return tile_row(list(self._tiles.values()))

    def _build_scoreboard(self) -> QWidget:
        card = Card("Tableau des scores")
        self._scoreboard = DataTable(
            ("Joueur", "Equipe", "K", "D", "A", "MVP", "K/D", "ADR", "HS", "PV", "$")
        )
        self._scoreboard.itemDoubleClicked.connect(self._on_row_double_clicked)
        card.add(self._scoreboard)
        hint = QLabel(
            "Double-clique sur une ligne pour lancer une analyse anti-triche."
        )
        hint.setObjectName("Muted")
        card.add(hint)
        return card

    def _build_event_feed(self) -> QWidget:
        card = Card("Journal des evenements")
        self._events = QListWidget()
        self._events.setStyleSheet(
            f"QListWidget {{ background-color: {theme.BG_DEEP}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 8px; "
            f"font-family: {theme.MONO_FAMILY}; font-size: 11px; }}"
            f"QListWidget::item {{ padding: 3px 6px; }}"
        )
        card.add(self._events)
        return card

    # --- cycle de vie --------------------------------------------------------
    def start(self) -> None:
        if not self._state_timer.is_running:
            self._state_timer.start()
            self._toggle_button.setText("Arreter le suivi")

    def stop(self) -> None:
        self._state_timer.stop()
        self._toggle_button.setText("Demarrer le suivi")

    def _toggle(self) -> None:
        if self._state_timer.is_running:
            self.stop()
            self.status_message.emit("Suivi temps reel arrete.")
        else:
            self.start()
            self.status_message.emit("Suivi temps reel demarre.")

    # --- donnees -------------------------------------------------------------
    def _fetch_all(self) -> dict[str, Any]:
        state = self._client.live_state()
        scoreboard = self._client.live_scoreboard()
        events = self._client.live_events(since=self._last_sequence, limit=120)
        return {"state": state, "scoreboard": scoreboard, "events": events}

    def _on_error(self, message: str) -> None:
        self._connection_badge.set_status("API INJOIGNABLE", theme.DANGER)
        self.status_message.emit(message)

    def _on_data(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        self._render_state(payload.get("state") or {})
        self._render_scoreboard(payload.get("scoreboard") or [])
        self._render_events(payload.get("events") or {})

    def _render_state(self, snapshot: dict) -> None:
        connected = bool(snapshot.get("connected"))
        self._connection_badge.set_status(
            "GSI CONNECTE" if connected else "EN ATTENTE DU JEU",
            theme.SUCCESS if connected else theme.TEXT_MUTED,
        )

        state = snapshot.get("state") or {}
        map_state = state.get("map") or {}
        round_state = state.get("round") or {}
        player = state.get("player") or {}
        player_state = player.get("state") or {}
        match_stats = player.get("match_stats") or {}

        if map_state.get("name"):
            mode = map_state.get("mode", "")
            self._map_label.setText(f"{map_state['name']}  ·  {mode}")
            ct = (map_state.get("team_ct") or {}).get("score", 0)
            t = (map_state.get("team_t") or {}).get("score", 0)
            self._score_label.setText(f"CT {ct}  —  {t} T")
            self._score_label.setStyleSheet(
                f"font-size: 16px; font-weight: 700; color: {theme.TEXT_PRIMARY};"
            )
        else:
            self._map_label.setText(
                "Aucune partie detectee — lance CS2 avec la configuration GSI installee."
            )
            self._score_label.setText("")

        self._tiles["round"].set_value(str(map_state.get("round", "—")))
        self._tiles["phase"].set_value(str(round_state.get("phase", "—")).upper())
        health = player_state.get("health")
        self._tiles["health"].set_value(
            f"{health}" if health is not None else "—",
            theme.DANGER if isinstance(health, int) and health <= 30 else None,
        )
        money = player_state.get("money")
        self._tiles["money"].set_value(f"{money} $" if money is not None else "—")
        self._tiles["kills"].set_value(str(player_state.get("round_kills", "—")))
        self._tiles["kd"].set_value(
            f"{match_stats.get('kd', 0):.2f}" if match_stats else "—"
        )

        if player.get("name"):
            self._tiles["kd"].set_hint(
                f"{player.get('name')} — {match_stats.get('kills', 0)}/"
                f"{match_stats.get('deaths', 0)}"
            )

    def _render_scoreboard(self, rows: list[dict]) -> None:
        table_rows = []
        colors = []
        for row in rows:
            table_rows.append(
                (
                    row.get("name", "?"),
                    row.get("team", "—"),
                    row.get("kills", 0),
                    row.get("deaths", 0),
                    row.get("assists", 0),
                    row.get("mvps", 0),
                    f"{row.get('kd', 0):.2f}",
                    f"{row.get('adr', 0):.0f}",
                    f"{(row.get('headshot_rate') or 0) * 100:.0f} %",
                    row.get("health") if row.get("health") is not None else "—",
                    row.get("money") if row.get("money") is not None else "—",
                )
            )
            colors.append(
                theme.CT_BLUE if row.get("team") == "CT" else theme.T_YELLOW
            )
        self._scoreboard.fill(table_rows, colors)
        self._scoreboard_steamids = [row.get("steamid", "") for row in rows]

        if rows:
            adr_values = [row.get("adr", 0) for row in rows]
            self._tiles["adr"].set_value(f"{max(adr_values):.0f}")
            self._tiles["adr"].set_hint("meilleur ADR du lobby")

    def _render_events(self, payload: dict) -> None:
        self._last_sequence = payload.get("latest_sequence", self._last_sequence)
        for event in payload.get("events", []):
            label, color = _EVENT_LABELS.get(
                event.get("type", ""), (event.get("type", "?"), theme.TEXT_SECONDARY)
            )
            actor = event.get("player") or ""
            detail = _format_detail(event.get("detail") or {})
            text = f"R{event.get('round', 0):02d}  {label}"
            if actor:
                text += f"  ·  {actor}"
            if detail:
                text += f"  ({detail})"

            item = QListWidgetItem(text)
            item.setForeground(QColor(color))
            self._events.insertItem(0, item)

        while self._events.count() > MAX_EVENT_ROWS:
            self._events.takeItem(self._events.count() - 1)

    # --- interactions --------------------------------------------------------
    def _on_row_double_clicked(self, item: Any) -> None:
        row = item.row()
        steamids = getattr(self, "_scoreboard_steamids", [])
        if 0 <= row < len(steamids) and steamids[row]:
            self.analyse_requested.emit(steamids[row])

    def _analyse_lobby(self) -> None:
        self._analyse_lobby_button.setEnabled(False)
        self.status_message.emit("Analyse du lobby en cours…")
        run_async(
            self._client.analyse_live_lobby,
            self._on_lobby_analysed,
            self.status_message.emit,
            lambda: self._analyse_lobby_button.setEnabled(True),
        )

    def _on_lobby_analysed(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        count = data.get("analysed", 0)
        if count == 0:
            self.status_message.emit(
                data.get("message", "Aucun joueur observe a analyser.")
            )
            return
        summary = data.get("summary") or []
        worst = summary[0] if summary else {}
        self.status_message.emit(
            f"{count} joueur(s) analyse(s). Plus haut score : "
            f"{worst.get('name', '?')} — {worst.get('score', 0)}/100 "
            f"({worst.get('verdict', '?')})."
        )


def _format_detail(detail: dict) -> str:
    parts = []
    for key in ("count", "headshots", "weapon", "kills", "amount", "health", "win_team", "map"):
        if key in detail and detail[key] not in (None, "", 0):
            parts.append(f"{key}={detail[key]}")
    return ", ".join(parts)
