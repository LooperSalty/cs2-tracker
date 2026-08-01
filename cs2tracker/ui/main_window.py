"""Fenêtre principale : navigation latérale et pile de pages."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from cs2tracker import __app_name__, __version__
from cs2tracker.ui import theme
from cs2tracker.ui.api_client import ApiClient
from cs2tracker.ui.pages import (
    AnticheatPage,
    LivePage,
    MatchesPage,
    PlayerPage,
    SettingsPage,
)
from cs2tracker.ui.widgets import Badge
from cs2tracker.ui.workers import PollingTimer

#: Fréquence de vérification de l'état global affiché dans la barre de statut.
STATUS_POLL_MS = 5_000
SIDEBAR_WIDTH = 210


class MainWindow(QMainWindow):
    """Coquille de l'application."""

    def __init__(self, client: ApiClient) -> None:
        super().__init__()
        self._client = client
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1400, 880)
        self.setMinimumSize(1100, 700)

        self._build()
        self._connect_pages()

        self._status_timer = PollingTimer(
            STATUS_POLL_MS,
            self._client.system_status,
            self._on_status,
            self._on_status_error,
            self,
        )
        self._status_timer.start()
        QTimer.singleShot(400, self._live_page.start)

    # --- construction --------------------------------------------------------
    def _build(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._pages = QStackedWidget()
        self._player_page = PlayerPage(self._client)
        self._live_page = LivePage(self._client)
        self._anticheat_page = AnticheatPage(self._client)
        self._matches_page = MatchesPage(self._client)
        self._settings_page = SettingsPage(self._client)

        for page in (
            self._player_page,
            self._live_page,
            self._anticheat_page,
            self._matches_page,
            self._settings_page,
        ):
            self._pages.addWidget(page)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(central)

        self._build_status_bar()

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        title = QLabel("CS2 TRACKER")
        title.setObjectName("SidebarTitle")
        subtitle = QLabel("Statistiques · Temps reel · Analyse")
        subtitle.setObjectName("SidebarSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        entries = (
            ("  Joueur", 0),
            ("  Temps reel", 1),
            ("  Anti-triche", 2),
            ("  Matchs", 3),
            ("  Configuration", 4),
        )
        for label, index in entries:
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, i=index: self._pages.setCurrentIndex(i))
            self._nav_group.addButton(button, index)
            layout.addWidget(button)
        self._nav_group.button(0).setChecked(True)

        layout.addStretch(1)

        footer = QLabel(
            "Donnees publiques Steam\net GSI officiel Valve.\nAucune lecture memoire."
        )
        footer.setObjectName("Muted")
        footer.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px; padding: 12px;")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        return sidebar

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self._message = QLabel("Pret.")
        self._steam_badge = Badge("STEAM —", theme.TEXT_MUTED)
        self._gsi_badge = Badge("GSI —", theme.TEXT_MUTED)
        bar.addWidget(self._message, 1)
        bar.addPermanentWidget(self._steam_badge)
        bar.addPermanentWidget(self._gsi_badge)
        self.setStatusBar(bar)

    def _connect_pages(self) -> None:
        for page in (
            self._player_page,
            self._live_page,
            self._anticheat_page,
            self._matches_page,
            self._settings_page,
        ):
            page.status_message.connect(self._show_message)

        self._player_page.player_loaded.connect(self._on_player_loaded)
        self._live_page.analyse_requested.connect(self._go_to_analysis)
        self._matches_page.analyse_requested.connect(self._go_to_analysis)
        self._pages.currentChanged.connect(self._on_page_changed)

    # --- comportements -------------------------------------------------------
    def _show_message(self, message: str) -> None:
        self._message.setText(message)

    def _on_player_loaded(self, steamid: str, reason: str) -> None:
        if reason == "analyse":
            self._go_to_analysis(steamid)

    def _go_to_analysis(self, steamid: str) -> None:
        self._nav_group.button(2).setChecked(True)
        self._pages.setCurrentIndex(2)
        self._anticheat_page.analyse_steamid(steamid)

    def _on_page_changed(self, index: int) -> None:
        if index == 3:
            self._matches_page.refresh()
        elif index == 4:
            self._settings_page.refresh()

    def _on_status(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        steam_ok = bool(data.get("steam_api_configured"))
        self._steam_badge.set_status(
            "STEAM OK" if steam_ok else "CLE MANQUANTE",
            theme.SUCCESS if steam_ok else theme.DANGER,
        )
        live = data.get("live") or {}
        connected = bool(live.get("connected"))
        installed = bool(data.get("gsi_config_installed"))
        if connected:
            self._gsi_badge.set_status("GSI EN DIRECT", theme.SUCCESS)
        elif installed:
            self._gsi_badge.set_status("GSI EN ATTENTE", theme.WARNING)
        else:
            self._gsi_badge.set_status("GSI ABSENT", theme.TEXT_MUTED)

    def _on_status_error(self, message: str) -> None:
        self._steam_badge.set_status("API HORS LIGNE", theme.DANGER)
        self._show_message(message)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        self._status_timer.stop()
        self._live_page.stop()
        self._client.close()
        super().closeEvent(event)
