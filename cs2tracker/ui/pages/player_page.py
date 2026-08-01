"""Page « Joueur » : recherche, profil, statistiques détaillées."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cs2tracker.ui import theme
from cs2tracker.ui.api_client import ApiClient
from cs2tracker.ui.widgets import (
    Badge,
    Card,
    DataTable,
    SectionHeader,
    StatTile,
    tile_row,
)
from cs2tracker.ui.workers import run_async


class PlayerPage(QWidget):
    """Recherche d'un joueur et présentation exhaustive de ses données."""

    #: Émis quand un joueur est chargé, pour alimenter les autres pages.
    player_loaded = Signal(str, str)
    status_message = Signal(str)

    def __init__(self, client: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._current_steamid = ""
        self._build()

    # --- construction --------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(
            SectionHeader(
                "Profil joueur",
                "SteamID64, SteamID2/3, URL de profil ou pseudo personnalise.",
            )
        )
        layout.addWidget(self._build_search_bar())
        layout.addWidget(self._build_identity_card())
        layout.addWidget(self._build_tiles())
        layout.addWidget(self._build_tabs(), stretch=1)

    def _build_search_bar(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "76561198000000000  |  STEAM_1:0:12345  |  steamcommunity.com/id/pseudo"
        )
        self._search_input.returnPressed.connect(self._on_search)

        self._search_button = QPushButton("Rechercher")
        self._search_button.setObjectName("Primary")
        self._search_button.clicked.connect(self._on_search)

        self._analyse_button = QPushButton("Analyser")
        self._analyse_button.setEnabled(False)
        self._analyse_button.clicked.connect(self._on_analyse_requested)

        row.addWidget(self._search_input, stretch=1)
        row.addWidget(self._search_button)
        row.addWidget(self._analyse_button)
        return container

    def _build_identity_card(self) -> QWidget:
        card = Card()
        row = QHBoxLayout()
        row.setSpacing(14)

        left = QVBoxLayout()
        self._name_label = QLabel("Aucun joueur charge")
        self._name_label.setObjectName("PageTitle")
        self._id_label = QLabel("")
        self._id_label.setObjectName("Mono")
        self._id_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._meta_label = QLabel("")
        self._meta_label.setObjectName("Muted")
        self._meta_label.setWordWrap(True)
        left.addWidget(self._name_label)
        left.addWidget(self._id_label)
        left.addWidget(self._meta_label)

        badges = QHBoxLayout()
        badges.setSpacing(6)
        self._visibility_badge = Badge("—", theme.TEXT_MUTED)
        self._ban_badge = Badge("—", theme.TEXT_MUTED)
        self._status_badge = Badge("—", theme.TEXT_MUTED)
        for badge in (self._visibility_badge, self._ban_badge, self._status_badge):
            badges.addWidget(badge)
        badges.addStretch(1)

        right = QVBoxLayout()
        right.addLayout(badges)
        right.addStretch(1)

        row.addLayout(left, stretch=1)
        row.addLayout(right)
        card.body().addLayout(row)
        return card

    def _build_tiles(self) -> QWidget:
        self._tiles: dict[str, StatTile] = {
            "kd": StatTile("Ratio K/D"),
            "hs": StatTile("Taux de HS"),
            "accuracy": StatTile("Precision"),
            "adr": StatTile("Degats / manche"),
            "hours": StatTile("Heures CS2"),
            "rounds": StatTile("Manches jouees"),
            "winrate": StatTile("Victoires"),
        }
        return tile_row(list(self._tiles.values()))

    def _build_tabs(self) -> QWidget:
        self._tabs = QTabWidget()

        self._overview_table = DataTable(("Indicateur", "Valeur"))
        self._tabs.addTab(_scrollable(self._overview_table), "Vue d'ensemble")

        self._weapons_table = DataTable(
            ("Arme", "Categorie", "Kills", "Tirs", "Impacts", "Precision", "Tirs/kill")
        )
        self._tabs.addTab(_scrollable(self._weapons_table), "Armes")

        self._maps_table = DataTable(("Carte", "Manches", "Victoires", "Taux"))
        self._tabs.addTab(_scrollable(self._maps_table), "Cartes")

        self._games_table = DataTable(("Jeu", "Heures", "2 semaines", "Derniere partie"))
        self._tabs.addTab(_scrollable(self._games_table), "Bibliotheque")

        self._history_table = DataTable(
            ("Date", "Kills", "Morts", "Manches", "K/D", "HS", "Precision")
        )
        self._tabs.addTab(_scrollable(self._history_table), "Historique local")

        return self._tabs

    # --- actions -------------------------------------------------------------
    def search(self, query: str) -> None:
        self._search_input.setText(query)
        self._on_search()

    def _on_search(self) -> None:
        query = self._search_input.text().strip()
        if not query:
            self.status_message.emit("Saisis un identifiant Steam.")
            return

        self._set_busy(True)
        self.status_message.emit(f"Recherche de « {query} »…")
        run_async(
            lambda: self._client.search_player(query),
            self._on_profile_loaded,
            self._on_error,
            lambda: self._set_busy(False),
        )

    def _on_analyse_requested(self) -> None:
        if self._current_steamid:
            self.player_loaded.emit(self._current_steamid, "analyse")

    def _set_busy(self, busy: bool) -> None:
        self._search_button.setEnabled(not busy)
        self._search_button.setText("Recherche…" if busy else "Rechercher")

    def _on_error(self, message: str) -> None:
        self.status_message.emit(message)

    # --- rendu ---------------------------------------------------------------
    def _on_profile_loaded(self, data: Any) -> None:
        if not isinstance(data, dict):
            self.status_message.emit("Reponse inattendue de l'API.")
            return

        identity = data.get("identity") or {}
        summary = data.get("summary") or {}
        bans = data.get("bans") or {}
        stats = data.get("stats") or {}
        account = data.get("account") or {}

        self._current_steamid = str(identity.get("steamid64", ""))
        self._analyse_button.setEnabled(bool(self._current_steamid))

        self._render_identity(identity, summary, bans, account)
        self._render_tiles(stats, account)
        self._render_overview(data)
        self._render_weapons(stats.get("weapons") or [])
        self._render_maps(stats.get("maps") or [])
        self._load_games()
        self._load_history()

        errors = data.get("partial_errors") or []
        if errors:
            self.status_message.emit(
                f"{summary.get('persona_name', 'Joueur')} charge — donnees partielles : "
                + ", ".join(errors)
            )
        else:
            self.status_message.emit(
                f"{summary.get('persona_name', 'Joueur')} charge."
            )
        self.player_loaded.emit(self._current_steamid, "loaded")

    def _render_identity(
        self, identity: dict, summary: dict, bans: dict, account: dict
    ) -> None:
        self._name_label.setText(summary.get("persona_name") or "Profil sans nom")
        self._id_label.setText(
            f"{identity.get('steamid64', '')}   ·   {identity.get('steamid3', '')}"
            f"   ·   {identity.get('steamid2', '')}"
        )

        meta_parts: list[str] = []
        if summary.get("time_created"):
            meta_parts.append(f"compte cree le {summary['time_created'][:10]}")
        if summary.get("country_code"):
            meta_parts.append(f"pays {summary['country_code']}")
        if account.get("steam_level") is not None:
            meta_parts.append(f"niveau Steam {account['steam_level']}")
        if account.get("friends_count"):
            meta_parts.append(f"{account['friends_count']} amis")
        if account.get("games_owned"):
            meta_parts.append(f"{account['games_owned']} jeux")
        self._meta_label.setText("   ·   ".join(meta_parts) or "Metadonnees indisponibles")

        is_public = summary.get("is_public")
        self._visibility_badge.set_status(
            "PROFIL PUBLIC" if is_public else "PROFIL PRIVE",
            theme.SUCCESS if is_public else theme.WARNING,
        )

        if bans.get("has_any_ban"):
            total = bans.get("total_bans", 0)
            self._ban_badge.set_status(
                f"{total} SANCTION(S)", theme.DANGER
            )
        else:
            self._ban_badge.set_status("AUCUNE SANCTION", theme.SUCCESS)

        if summary.get("playing_cs2"):
            self._status_badge.set_status("EN JEU SUR CS2", theme.ACCENT)
        elif summary.get("in_game"):
            self._status_badge.set_status(
                str(summary.get("game_extra_info", "EN JEU")).upper()[:24], theme.INFO
            )
        else:
            self._status_badge.set_status(
                str(summary.get("persona_state_label", "—")).upper(), theme.TEXT_MUTED
            )

    def _render_tiles(self, stats: dict, account: dict) -> None:
        ratios = stats.get("ratios") or {}
        totals = stats.get("totals") or {}

        def fmt(value: Any, suffix: str = "", digits: int = 2) -> str:
            if value is None:
                return "—"
            try:
                return f"{float(value):.{digits}f}{suffix}"
            except (TypeError, ValueError):
                return "—"

        self._tiles["kd"].set_value(fmt(ratios.get("kd")))
        self._tiles["hs"].set_value(
            fmt((ratios.get("headshot_rate") or 0) * 100, " %", 1)
        )
        self._tiles["accuracy"].set_value(
            fmt((ratios.get("accuracy") or 0) * 100, " %", 1)
        )
        self._tiles["adr"].set_value(fmt(ratios.get("damage_per_round"), "", 0))
        self._tiles["hours"].set_value(
            fmt(account.get("cs2_hours") or totals.get("hours_played"), " h", 0)
        )
        self._tiles["rounds"].set_value(f"{totals.get('rounds_played', 0):,}".replace(",", " "))
        self._tiles["winrate"].set_value(
            fmt((ratios.get("match_win_rate") or 0) * 100, " %", 1)
        )

        if account.get("cs2_hours_2weeks"):
            self._tiles["hours"].set_hint(
                f"{account['cs2_hours_2weeks']:.1f} h sur 2 semaines"
            )

    def _render_overview(self, data: dict) -> None:
        stats = data.get("stats") or {}
        totals = stats.get("totals") or {}
        ratios = stats.get("ratios") or {}
        last = stats.get("last_match") or {}
        account = data.get("account") or {}
        bans = data.get("bans") or {}
        achievements = data.get("achievements") or {}

        rows: list[tuple[str, str]] = [
            ("Eliminations totales", f"{totals.get('kills', 0):,}".replace(",", " ")),
            ("Morts totales", f"{totals.get('deaths', 0):,}".replace(",", " ")),
            ("Headshots", f"{totals.get('headshot_kills', 0):,}".replace(",", " ")),
            ("Balles tirees", f"{totals.get('shots_fired', 0):,}".replace(",", " ")),
            ("Balles au but", f"{totals.get('shots_hit', 0):,}".replace(",", " ")),
            ("Degats infliges", f"{totals.get('damage_done', 0):,}".replace(",", " ")),
            ("Argent gagne", f"{totals.get('money_earned', 0):,} $".replace(",", " ")),
            ("Manches jouees", f"{totals.get('rounds_played', 0):,}".replace(",", " ")),
            ("Manches gagnees", f"{totals.get('rounds_won', 0):,}".replace(",", " ")),
            ("Matchs joues", str(totals.get("matches_played", 0))),
            ("Matchs gagnes", str(totals.get("matches_won", 0))),
            ("MVP", str(totals.get("assists_proxy_mvps", 0))),
            ("Bombes posees", str(totals.get("bombs_planted", 0))),
            ("Bombes desamorcees", str(totals.get("bombs_defused", 0))),
            ("Otages liberes", str(totals.get("hostages_rescued", 0))),
            ("Manches pistolet gagnees", str(totals.get("pistol_rounds_won", 0))),
            ("—", "—"),
            ("Kills par manche", f"{ratios.get('kills_per_round', 0):.3f}"),
            ("Morts par manche", f"{ratios.get('deaths_per_round', 0):.3f}"),
            ("Degats par kill", f"{ratios.get('damage_per_kill', 0):.1f}"),
            ("Tirs par kill", f"{ratios.get('shots_per_kill', 0):.1f}"),
            ("Impacts par kill", f"{ratios.get('hits_per_kill', 0):.2f}"),
            ("Kills par heure", f"{ratios.get('kills_per_hour', 0):.1f}"),
            ("Taux de MVP", f"{(ratios.get('mvp_rate') or 0) * 100:.2f} %"),
            ("Taux de manches gagnees", f"{(ratios.get('round_win_rate') or 0) * 100:.2f} %"),
            ("—", "—"),
            ("Dernier match — K/D", f"{last.get('kd', 0):.2f}"),
            ("Dernier match — ADR", f"{last.get('adr', 0):.1f}"),
            ("Dernier match — kills", str(last.get("kills", 0))),
            ("Dernier match — MVP", str(last.get("mvps", 0))),
            ("Dernier match — arme favorite", str(last.get("favourite_weapon", "—"))),
            ("—", "—"),
            ("Succes debloques", f"{achievements.get('unlocked', 0)} / {achievements.get('total', 0)}"),
            ("Bannissements VAC", str(bans.get("number_of_vac_bans", 0))),
            ("Bannissements editeur", str(bans.get("number_of_game_bans", 0))),
            ("Jours depuis la sanction", str(bans.get("days_since_last_ban", 0))),
            ("Restriction marche", str(bans.get("economy_ban", "none"))),
            ("Part de CS2 dans le temps de jeu",
             f"{(account.get('cs2_share_of_playtime') or 0) * 100:.1f} %"),
        ]
        self._overview_table.fill(rows)

    def _render_weapons(self, weapons: list[dict]) -> None:
        rows = [
            (
                weapon.get("name", "?"),
                weapon.get("category", "—"),
                f"{weapon.get('kills', 0):,}".replace(",", " "),
                f"{weapon.get('shots_fired', 0):,}".replace(",", " "),
                f"{weapon.get('shots_hit', 0):,}".replace(",", " "),
                f"{(weapon.get('accuracy') or 0) * 100:.1f} %",
                f"{weapon.get('shots_per_kill', 0):.1f}",
            )
            for weapon in weapons
        ]
        self._weapons_table.fill(rows)

    def _render_maps(self, maps: list[dict]) -> None:
        rows = [
            (
                game_map.get("name", "?"),
                f"{game_map.get('rounds_played', 0):,}".replace(",", " "),
                f"{game_map.get('wins', 0):,}".replace(",", " "),
                f"{(game_map.get('win_rate') or 0) * 100:.1f} %",
            )
            for game_map in maps
        ]
        self._maps_table.fill(rows)

    def _load_games(self) -> None:
        if not self._current_steamid:
            return
        steamid = self._current_steamid
        run_async(
            lambda: self._client.player_games(steamid, limit=40),
            self._render_games,
            lambda _msg: self._games_table.clear_rows(),
        )

    def _render_games(self, data: Any) -> None:
        games = (data or {}).get("top_games", []) if isinstance(data, dict) else []
        rows = [
            (
                game.get("name") or f"App {game.get('appid')}",
                f"{game.get('hours', 0):.1f} h",
                f"{game.get('hours_2weeks', 0):.1f} h",
                (game.get("last_played") or "—")[:10],
            )
            for game in games
        ]
        self._games_table.fill(rows)

    def _load_history(self) -> None:
        if not self._current_steamid:
            return
        steamid = self._current_steamid
        run_async(
            lambda: self._client.player_history(steamid),
            self._render_history,
            lambda _msg: self._history_table.clear_rows(),
        )

    def _render_history(self, data: Any) -> None:
        snapshots = (data or {}).get("snapshots", []) if isinstance(data, dict) else []
        rows = [
            (
                (snapshot.get("captured_at") or "")[:19].replace("T", " "),
                f"{snapshot.get('kills', 0):,}".replace(",", " "),
                f"{snapshot.get('deaths', 0):,}".replace(",", " "),
                f"{snapshot.get('rounds_played', 0):,}".replace(",", " "),
                f"{snapshot.get('kd_ratio', 0):.3f}",
                f"{(snapshot.get('headshot_rate') or 0) * 100:.1f} %",
                f"{(snapshot.get('accuracy') or 0) * 100:.1f} %",
            )
            for snapshot in snapshots
        ]
        self._history_table.fill(rows)


def _scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(widget)
    return area
