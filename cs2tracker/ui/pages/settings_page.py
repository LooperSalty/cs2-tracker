"""Page « Configuration » : clé API, installation GSI, diagnostic."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cs2tracker.config import get_settings, persist_steam_key
from cs2tracker.ui import theme
from cs2tracker.ui.api_client import ApiClient
from cs2tracker.ui.widgets import Badge, Card, DataTable, SectionHeader
from cs2tracker.ui.workers import run_async

_STEAM_KEY_URL = "https://steamcommunity.com/dev/apikey"


class SettingsPage(QWidget):
    """Configuration et vérification de l'installation."""

    status_message = Signal(str)

    def __init__(self, client: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(
            SectionHeader(
                "Configuration",
                "Cle API Steam, liaison temps reel avec CS2 et diagnostic du systeme.",
            )
        )
        layout.addWidget(self._build_api_key_card())
        layout.addWidget(self._build_gsi_card())
        layout.addWidget(self._build_status_card(), stretch=1)

    def _build_api_key_card(self) -> QWidget:
        card = Card("Cle API Steam")
        info = QLabel(
            "Necessaire pour lire les profils et les statistiques. "
            f"Elle s'obtient gratuitement sur <a href='{_STEAM_KEY_URL}' "
            f"style='color:{theme.ACCENT}'>{_STEAM_KEY_URL}</a>. "
            "La cle est stockee dans le fichier .env local et n'est jamais transmise "
            "ailleurs qu'a Steam."
        )
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        info.setObjectName("Muted")
        card.add(info)

        row = QHBoxLayout()
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Colle ta cle API Steam ici")
        current = get_settings().steam_api_key
        if current:
            self._key_input.setPlaceholderText(
                f"Cle deja configuree ({current[:4]}…{current[-4:]})"
            )

        save_button = QPushButton("Enregistrer")
        save_button.setObjectName("Primary")
        save_button.clicked.connect(self._save_key)

        row.addWidget(self._key_input, stretch=1)
        row.addWidget(save_button)
        card.body().addLayout(row)

        self._key_notice = QLabel("")
        self._key_notice.setObjectName("Muted")
        self._key_notice.setWordWrap(True)
        card.add(self._key_notice)
        return card

    def _build_gsi_card(self) -> QWidget:
        card = Card("Liaison temps reel (Game State Integration)")
        info = QLabel(
            "Installe le fichier <b>gamestate_integration_cs2tracker.cfg</b> dans le "
            "dossier de configuration de CS2. C'est le mecanisme officiel de Valve : "
            "le jeu envoie lui-meme son etat a cette application. "
            "<b>Redemarre CS2 apres l'installation.</b>"
        )
        info.setWordWrap(True)
        info.setObjectName("Muted")
        card.add(info)

        row = QHBoxLayout()
        row.addWidget(QLabel("Cadence d'envoi (s)"))
        self._throttle = QDoubleSpinBox()
        self._throttle.setRange(0.01, 5.0)
        self._throttle.setSingleStep(0.05)
        self._throttle.setValue(0.1)
        self._throttle.setToolTip(
            "Intervalle minimal entre deux envois du jeu. 0.1 s offre un suivi fluide "
            "sans charge notable."
        )
        row.addWidget(self._throttle)

        install_button = QPushButton("Installer / mettre a jour")
        install_button.setObjectName("Primary")
        install_button.clicked.connect(self._install_gsi)

        remove_button = QPushButton("Desinstaller")
        remove_button.setObjectName("Danger")
        remove_button.clicked.connect(self._uninstall_gsi)

        preview_button = QPushButton("Voir le fichier genere")
        preview_button.clicked.connect(self._preview_gsi)

        row.addStretch(1)
        row.addWidget(preview_button)
        row.addWidget(remove_button)
        row.addWidget(install_button)
        card.body().addLayout(row)

        self._gsi_output = QPlainTextEdit()
        self._gsi_output.setReadOnly(True)
        self._gsi_output.setMaximumHeight(150)
        self._gsi_output.setStyleSheet(
            f"font-family: {theme.MONO_FAMILY}; font-size: 11px;"
        )
        self._gsi_output.setVisible(False)
        card.add(self._gsi_output)
        return card

    def _build_status_card(self) -> QWidget:
        card = Card("Diagnostic")
        row = QHBoxLayout()
        self._steam_badge = Badge("STEAM —", theme.TEXT_MUTED)
        self._cs2_badge = Badge("CS2 —", theme.TEXT_MUTED)
        self._gsi_badge = Badge("GSI —", theme.TEXT_MUTED)
        self._live_badge = Badge("LIVE —", theme.TEXT_MUTED)
        for badge in (self._steam_badge, self._cs2_badge, self._gsi_badge, self._live_badge):
            row.addWidget(badge)
        row.addStretch(1)

        refresh_button = QPushButton("Rafraichir")
        refresh_button.clicked.connect(self.refresh)
        cache_button = QPushButton("Vider le cache Steam")
        cache_button.clicked.connect(self._clear_cache)
        row.addWidget(cache_button)
        row.addWidget(refresh_button)
        card.body().addLayout(row)

        self._status_table = DataTable(("Element", "Valeur"))
        card.add(self._status_table)
        return card

    # --- actions -------------------------------------------------------------
    def refresh(self) -> None:
        run_async(self._client.system_status, self._render_status, self._on_error)

    def _save_key(self) -> None:
        key = self._key_input.text().strip()
        if len(key) < 16:
            self._key_notice.setText(
                "Cette cle semble trop courte — une cle Steam fait 32 caracteres."
            )
            return
        try:
            persist_steam_key(key)
        except OSError as exc:
            self._key_notice.setText(f"Ecriture du fichier .env impossible : {exc}")
            return
        self._key_input.clear()
        self._key_notice.setText(
            "Cle enregistree dans le fichier .env. "
            "Redemarre l'application pour qu'elle soit prise en compte."
        )
        self.status_message.emit("Cle API Steam enregistree.")

    def _install_gsi(self) -> None:
        throttle = self._throttle.value()
        run_async(
            lambda: self._client.install_gsi(throttle),
            self._on_gsi_installed,
            self._on_error,
        )

    def _on_gsi_installed(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        self._gsi_output.setVisible(True)
        self._gsi_output.setPlainText(
            f"{data.get('message', '')}\n\nFichier : {data.get('config_path', '')}\n"
            f"Point de collecte : {data.get('endpoint', '')}"
        )
        self.status_message.emit(str(data.get("message", "Configuration GSI ecrite.")))
        self.refresh()

    def _uninstall_gsi(self) -> None:
        run_async(
            self._client.uninstall_gsi,
            lambda data: self._after_uninstall(data),
            self._on_error,
        )

    def _after_uninstall(self, data: Any) -> None:
        removed = bool(isinstance(data, dict) and data.get("removed"))
        self.status_message.emit(
            "Configuration GSI supprimee." if removed else "Aucune configuration a supprimer."
        )
        self.refresh()

    def _preview_gsi(self) -> None:
        run_async(self._client.gsi_preview, self._on_preview, self._on_error)

    def _on_preview(self, data: Any) -> None:
        if isinstance(data, dict):
            self._gsi_output.setVisible(True)
            self._gsi_output.setPlainText(str(data.get("content", "")))

    def _clear_cache(self) -> None:
        run_async(
            self._client.clear_cache,
            lambda data: self.status_message.emit(
                f"{(data or {}).get('cleared', 0)} entree(s) de cache supprimee(s)."
            ),
            self._on_error,
        )

    def _on_error(self, message: str) -> None:
        self.status_message.emit(message)

    # --- rendu ---------------------------------------------------------------
    def _render_status(self, data: Any) -> None:
        if not isinstance(data, dict):
            return

        steam_ok = bool(data.get("steam_api_configured"))
        cs2_ok = bool(data.get("cs2_detected"))
        gsi_ok = bool(data.get("gsi_config_installed"))
        live = data.get("live") or {}
        live_ok = bool(live.get("connected"))

        self._steam_badge.set_status(
            "STEAM OK" if steam_ok else "CLE API MANQUANTE",
            theme.SUCCESS if steam_ok else theme.DANGER,
        )
        self._cs2_badge.set_status(
            "CS2 DETECTE" if cs2_ok else "CS2 INTROUVABLE",
            theme.SUCCESS if cs2_ok else theme.WARNING,
        )
        self._gsi_badge.set_status(
            "GSI INSTALLE" if gsi_ok else "GSI NON INSTALLE",
            theme.SUCCESS if gsi_ok else theme.WARNING,
        )
        self._live_badge.set_status(
            "JEU CONNECTE" if live_ok else "JEU HORS LIGNE",
            theme.SUCCESS if live_ok else theme.TEXT_MUTED,
        )

        paths = data.get("cs2_paths") or {}
        database = data.get("database") or {}
        recorder = data.get("recorder") or {}
        cache = data.get("cache") or {}
        rows = [
            ("Version", data.get("version", "—")),
            ("API locale", data.get("api_base_url", "—")),
            ("Point de collecte GSI", data.get("gsi_endpoint", "—")),
            ("Installation Steam", paths.get("steam_path", "—")),
            ("Dossier du jeu", paths.get("game_path", "—")),
            ("Dossier cfg", paths.get("cfg_path", "—")),
            ("Base de donnees", database.get("path", "—")),
            ("Taille de la base", f"{database.get('size_bytes', 0) / 1024:.0f} Ko"),
            ("Joueurs suivis", (database.get("rows") or {}).get("players", 0)),
            ("Instantanes", (database.get("rows") or {}).get("stat_snapshots", 0)),
            ("Analyses", (database.get("rows") or {}).get("analyses", 0)),
            ("Matchs", (database.get("rows") or {}).get("matches", 0)),
            ("Enregistrement des matchs", "actif" if recorder.get("enabled") else "desactive"),
            ("Match en cours", recorder.get("match_id") or "—"),
            ("Payloads GSI recus", live.get("payloads_received", 0)),
            ("Requetes Steam", data.get("steam_requests", 0)),
            ("Cache Steam", f"{cache.get('entries', 0)} entrees, "
                            f"{(cache.get('hit_rate') or 0) * 100:.0f} % de reussite"),
        ]
        self._status_table.fill([(str(k), str(v)) for k, v in rows])
