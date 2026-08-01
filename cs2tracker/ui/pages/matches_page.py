"""Page « Matchs » : historique des parties enregistrées via le GSI."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from cs2tracker.ui import theme
from cs2tracker.ui.api_client import ApiClient
from cs2tracker.ui.widgets import Card, DataTable, SectionHeader
from cs2tracker.ui.workers import run_async


class MatchesPage(QWidget):
    """Consultation des matchs observés et de leurs statistiques par joueur."""

    status_message = Signal(str)
    analyse_requested = Signal(str)

    def __init__(self, client: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._match_ids: list[int] = []
        self._player_steamids: list[str] = []
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.addWidget(
            SectionHeader(
                "Matchs enregistres",
                "Chaque partie suivie en direct est archivee localement : score, "
                "manches et statistiques par joueur.",
            ),
            stretch=1,
        )
        self._refresh_button = QPushButton("Actualiser")
        self._refresh_button.clicked.connect(self.refresh)
        header_row.addWidget(self._refresh_button, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        matches_card = Card("Parties")
        self._matches_table = DataTable(
            ("Date", "Carte", "Mode", "Score CT", "Score T", "Manches", "Joueurs")
        )
        self._matches_table.itemSelectionChanged.connect(self._on_match_selected)
        matches_card.add(self._matches_table)
        splitter.addWidget(matches_card)

        detail = QWidget()
        detail_layout = QHBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(14)

        players_card = Card("Joueurs de la partie")
        self._players_table = DataTable(
            ("Joueur", "Equipe", "K", "D", "A", "MVP", "ADR", "HS", "Manches")
        )
        self._players_table.itemDoubleClicked.connect(self._on_player_double_clicked)
        players_card.add(self._players_table)
        hint = QLabel("Double-clique sur un joueur pour lancer une analyse.")
        hint.setObjectName("Muted")
        players_card.add(hint)
        detail_layout.addWidget(players_card, stretch=3)

        rounds_card = Card("Deroule des manches")
        self._rounds_table = DataTable(("Manche", "Vainqueur", "CT", "T", "Bombe"))
        rounds_card.add(self._rounds_table)
        detail_layout.addWidget(rounds_card, stretch=2)

        splitter.addWidget(detail)
        splitter.setSizes([260, 380])
        layout.addWidget(splitter, stretch=1)

    # --- donnees -------------------------------------------------------------
    def refresh(self) -> None:
        self._refresh_button.setEnabled(False)
        run_async(
            lambda: self._client.matches(limit=100),
            self._render_matches,
            self.status_message.emit,
            lambda: self._refresh_button.setEnabled(True),
        )

    def _render_matches(self, data: Any) -> None:
        matches = data if isinstance(data, list) else []
        self._match_ids = [int(match.get("id", 0)) for match in matches]
        rows = [
            (
                (match.get("started_at") or "")[:19].replace("T", " "),
                match.get("map_name") or "—",
                match.get("mode") or "—",
                match.get("score_ct", 0),
                match.get("score_t", 0),
                match.get("rounds_total", 0),
                (match.get("summary") or {}).get("players", "—"),
            )
            for match in matches
        ]
        self._matches_table.fill(rows)
        if not matches:
            self.status_message.emit(
                "Aucun match enregistre pour l'instant — lance CS2 avec le suivi actif."
            )

    def _on_match_selected(self) -> None:
        row = self._matches_table.currentRow()
        if not (0 <= row < len(self._match_ids)):
            return
        match_id = self._match_ids[row]
        run_async(
            lambda: self._client.match_detail(match_id),
            self._render_detail,
            self.status_message.emit,
        )

    def _render_detail(self, data: Any) -> None:
        if not isinstance(data, dict):
            return

        players = data.get("players") or []
        self._player_steamids = [str(p.get("steamid64", "")) for p in players]
        player_rows = []
        colors = []
        for player in players:
            player_rows.append(
                (
                    player.get("name") or player.get("steamid64", "?"),
                    player.get("team") or "—",
                    player.get("kills", 0),
                    player.get("deaths", 0),
                    player.get("assists", 0),
                    player.get("mvps", 0),
                    f"{player.get('adr', 0):.0f}",
                    f"{(player.get('headshot_rate') or 0) * 100:.0f} %",
                    player.get("rounds", 0),
                )
            )
            colors.append(
                theme.CT_BLUE if player.get("team") == "CT" else theme.T_YELLOW
            )
        self._players_table.fill(player_rows, colors)

        rounds = data.get("rounds") or []
        round_rows = [
            (
                entry.get("round_number", 0),
                entry.get("winner") or "—",
                (entry.get("details") or {}).get("score_ct", 0),
                (entry.get("details") or {}).get("score_t", 0),
                (entry.get("details") or {}).get("bomb", "—") or "—",
            )
            for entry in rounds
        ]
        self._rounds_table.fill(round_rows)

    def _on_player_double_clicked(self, item: Any) -> None:
        row = item.row()
        if 0 <= row < len(self._player_steamids) and self._player_steamids[row]:
            self.analyse_requested.emit(self._player_steamids[row])
