"""Page « Anti-triche » : analyse d'un joueur ou d'un lobby entier."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cs2tracker.ui import theme
from cs2tracker.ui.api_client import ApiClient
from cs2tracker.ui.widgets import Card, DataTable, ScoreGauge, SectionHeader
from cs2tracker.ui.workers import run_async


class AnticheatPage(QWidget):
    """Restitution complète et explicable du score de suspicion."""

    status_message = Signal(str)

    def __init__(self, client: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._current_steamid = ""
        self._build()
        self._load_disclaimer()

    # --- construction --------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(
            SectionHeader(
                "Analyse anti-triche",
                "Score heuristique explicable, calcule sur des donnees publiques Steam "
                "et le flux GSI officiel. Ce n'est ni une preuve ni une accusation.",
            )
        )
        layout.addWidget(self._build_controls())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_verdict_panel())
        splitter.addWidget(self._build_detail_panel())
        splitter.setSizes([360, 720])
        layout.addWidget(splitter, stretch=1)

    def _build_controls(self) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "SteamID64 du joueur a analyser (ou plusieurs, separes par des virgules)"
        )
        self._input.returnPressed.connect(self._on_analyse)

        self._use_live = QCheckBox("Croiser avec le temps reel")
        self._use_live.setChecked(True)

        self._analyse_button = QPushButton("Analyser")
        self._analyse_button.setObjectName("Primary")
        self._analyse_button.clicked.connect(self._on_analyse)

        self._batch_button = QPushButton("Analyser le lobby en direct")
        self._batch_button.clicked.connect(self._on_analyse_live_lobby)

        row.addWidget(self._input, stretch=1)
        row.addWidget(self._use_live)
        row.addWidget(self._analyse_button)
        row.addWidget(self._batch_button)
        return container

    def _build_verdict_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        gauge_card = Card("Score de suspicion")
        self._gauge = ScoreGauge()
        gauge_card.add(self._gauge)
        self._player_label = QLabel("Aucun joueur analyse")
        self._player_label.setObjectName("Muted")
        self._player_label.setWordWrap(True)
        gauge_card.add(self._player_label)
        layout.addWidget(gauge_card)

        category_card = Card("Par famille d'indicateurs")
        self._categories = DataTable(("Famille", "Score", "Confiance", "Signaux"))
        self._categories.setMaximumHeight(220)
        category_card.add(self._categories)
        layout.addWidget(category_card)

        reco_card = Card("Recommandation")
        self._recommendation = QLabel(
            "Lance une analyse pour obtenir une recommandation."
        )
        self._recommendation.setWordWrap(True)
        reco_card.add(self._recommendation)
        layout.addWidget(reco_card)

        layout.addStretch(1)
        return container

    def _build_detail_panel(self) -> QWidget:
        self._tabs = QTabWidget()

        self._signals_table = DataTable(
            ("Indicateur", "Gravite", "Score", "Confiance", "Mesure", "Reference", "z")
        )
        self._tabs.addTab(self._signals_table, "Indicateurs")

        self._explanations = QTextEdit()
        self._explanations.setReadOnly(True)
        self._tabs.addTab(self._explanations, "Explications detaillees")

        self._report = QPlainTextEdit()
        self._report.setReadOnly(True)
        self._report.setStyleSheet(
            f"font-family: {theme.MONO_FAMILY}; font-size: 11px;"
        )
        self._tabs.addTab(self._report, "Rapport texte")

        self._lobby_table = DataTable(
            ("Joueur", "Score", "Verdict", "Confiance", "Sanction", "Signal principal")
        )
        self._tabs.addTab(self._lobby_table, "Lobby")

        self._methodology = QTextEdit()
        self._methodology.setReadOnly(True)
        self._tabs.addTab(_wrap_scroll(self._methodology), "Methodologie")

        return self._tabs

    # --- actions -------------------------------------------------------------
    def analyse_steamid(self, steamid: str) -> None:
        self._input.setText(steamid)
        self._on_analyse()

    def _on_analyse(self) -> None:
        raw = self._input.text().strip()
        if not raw:
            self.status_message.emit("Saisis au moins un SteamID64.")
            return

        players = [part.strip() for part in raw.split(",") if part.strip()]
        if len(players) > 1:
            self._run_batch(players)
            return

        steamid = players[0]
        self._current_steamid = steamid
        self._set_busy(True)
        self.status_message.emit(f"Analyse de {steamid} en cours…")
        use_live = self._use_live.isChecked()
        run_async(
            lambda: self._client.analyse(steamid, use_live=use_live),
            self._on_analysis_ready,
            self._on_error,
            lambda: self._set_busy(False),
        )

    def _on_analyse_live_lobby(self) -> None:
        self._batch_button.setEnabled(False)
        self.status_message.emit("Analyse du lobby en direct…")
        run_async(
            self._client.analyse_live_lobby,
            self._on_batch_ready,
            self._on_error,
            lambda: self._batch_button.setEnabled(True),
        )

    def _run_batch(self, players: list[str]) -> None:
        self._set_busy(True)
        use_live = self._use_live.isChecked()
        self.status_message.emit(f"Analyse de {len(players)} joueurs…")
        run_async(
            lambda: self._client.analyse_batch(players, use_live=use_live),
            self._on_batch_ready,
            self._on_error,
            lambda: self._set_busy(False),
        )

    def _set_busy(self, busy: bool) -> None:
        self._analyse_button.setEnabled(not busy)
        self._analyse_button.setText("Analyse…" if busy else "Analyser")

    def _on_error(self, message: str) -> None:
        self.status_message.emit(message)

    # --- rendu ---------------------------------------------------------------
    def _on_analysis_ready(self, data: Any) -> None:
        if not isinstance(data, dict):
            self.status_message.emit("Reponse d'analyse inattendue.")
            return

        score = float(data.get("suspicion_score", 0))
        verdict = str(data.get("verdict", "INDETERMINE"))
        self._gauge.update_score(
            score,
            verdict,
            str(data.get("verdict_label", "")),
            float(data.get("global_confidence", 0)),
        )

        sources = data.get("data_sources") or {}
        active = [name for name, ok in sources.items() if ok]
        self._player_label.setText(
            f"{data.get('name', '?')}  ·  {data.get('steamid', '')}\n"
            f"Sources exploitees : {', '.join(active) or 'aucune'}"
        )

        self._render_categories(data.get("categories") or [])
        self._render_signals(data.get("signals") or [])
        self._render_explanations(data)
        self._load_text_report(str(data.get("steamid", "")))

        self.status_message.emit(
            f"{data.get('name', '?')} — score {score:.0f}/100 ({verdict})."
        )

    def _render_categories(self, categories: list[dict]) -> None:
        rows = []
        colors = []
        for category in categories:
            score = float(category.get("score", 0))
            rows.append(
                (
                    category.get("category", "?"),
                    f"{score:.1f}",
                    f"{(category.get('confidence') or 0) * 100:.0f} %",
                    str(category.get("signals", 0)),
                )
            )
            colors.append(theme.score_color(score))
        self._categories.fill(rows, colors)

    def _render_signals(self, signals: list[dict]) -> None:
        ordered = sorted(
            signals, key=lambda s: s.get("contribution", 0), reverse=True
        )
        rows = []
        colors = []
        for signal in ordered:
            severity = str(signal.get("severity", "info"))
            observed = signal.get("observed")
            expected = signal.get("expected")
            z_value = signal.get("z_score")
            rows.append(
                (
                    signal.get("label", signal.get("key", "?")),
                    severity,
                    f"{(signal.get('score') or 0) * 100:.0f}",
                    f"{(signal.get('confidence') or 0) * 100:.0f} %",
                    f"{observed:.3f}" if isinstance(observed, (int, float)) else "—",
                    f"{expected:.3f}" if isinstance(expected, (int, float)) else "—",
                    f"{z_value:+.2f}" if isinstance(z_value, (int, float)) else "—",
                )
            )
            colors.append(theme.SEVERITY_COLORS.get(severity, theme.TEXT_MUTED))
        self._signals_table.fill(rows, colors)

    def _render_explanations(self, data: dict) -> None:
        parts: list[str] = []
        highlights = data.get("highlights") or []
        if highlights:
            parts.append("<h3 style='color:#f0932b'>Indicateurs les plus contributifs</h3>")
            for signal in highlights:
                color = theme.SEVERITY_COLORS.get(
                    str(signal.get("severity", "info")), theme.TEXT_MUTED
                )
                parts.append(
                    f"<p><b style='color:{color}'>[{signal.get('severity', '').upper()}] "
                    f"{signal.get('label', '')}</b><br>"
                    f"<span style='color:#9aa7b4'>{signal.get('explanation', '')}</span><br>"
                    f"<span style='color:#6b7785;font-size:11px'>"
                    f"echantillon : {signal.get('sample_size', 0)} · "
                    f"poids : {signal.get('weight', 0)} · "
                    f"contribution : {signal.get('contribution', 0)}</span></p>"
                )

        parts.append("<h3 style='color:#f0932b'>Tous les indicateurs</h3>")
        for signal in sorted(
            data.get("signals") or [], key=lambda s: s.get("contribution", 0), reverse=True
        ):
            if not signal.get("explanation"):
                continue
            color = theme.SEVERITY_COLORS.get(
                str(signal.get("severity", "info")), theme.TEXT_MUTED
            )
            parts.append(
                f"<p><b style='color:{color}'>{signal.get('label', '')}</b> "
                f"<span style='color:#6b7785'>({signal.get('category', '')})</span><br>"
                f"<span style='color:#9aa7b4'>{signal.get('explanation', '')}</span></p>"
            )

        parts.append(
            f"<hr><p style='color:#6b7785;font-size:11px'>{data.get('disclaimer', '')}</p>"
        )
        self._explanations.setHtml("".join(parts))

    def _load_text_report(self, steamid: str) -> None:
        if not steamid:
            return
        run_async(
            lambda: self._client.analyse_report(steamid),
            lambda data: self._on_report_ready(data),
            lambda msg: self._report.setPlainText(f"Rapport indisponible : {msg}"),
        )

    def _on_report_ready(self, data: Any) -> None:
        if isinstance(data, dict):
            self._report.setPlainText(str(data.get("text", "")))
            self._recommendation.setText(_extract_recommendation(str(data.get("text", ""))))

    def _on_batch_ready(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        summary = data.get("summary") or []
        if not summary:
            self.status_message.emit(
                data.get("message", "Aucun joueur analysable dans ce lobby.")
            )
            return

        rows = []
        colors = []
        for entry in summary:
            score = float(entry.get("score", 0))
            rows.append(
                (
                    entry.get("name", "?"),
                    f"{score:.0f}",
                    entry.get("verdict", "?"),
                    f"{(entry.get('confidence') or 0) * 100:.0f} %",
                    "OUI" if entry.get("has_confirmed_ban") else "non",
                    entry.get("top_reason", "—"),
                )
            )
            colors.append(theme.VERDICT_COLORS.get(entry.get("verdict", ""), theme.TEXT_MUTED))
        self._lobby_table.fill(rows, colors)
        self._tabs.setCurrentWidget(self._lobby_table)

        results = data.get("results") or []
        if results:
            self._on_analysis_ready(results[0])
        self.status_message.emit(f"{len(summary)} joueur(s) analyse(s).")

    def _load_disclaimer(self) -> None:
        run_async(
            self._client.anticheat_disclaimer,
            self._render_methodology,
            lambda _msg: None,
        )

    def _render_methodology(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        methodology = data.get("methodology") or {}
        bands = data.get("verdict_bands") or {}
        html = [
            "<h2 style='color:#f0932b'>Ce que fait le moteur</h2>",
            "<p style='color:#9aa7b4'>Il compare les statistiques du joueur a des "
            "distributions de reference, pondere chaque ecart par la taille de "
            "l'echantillon, puis exige que <b>plusieurs familles d'indicateurs "
            "independantes</b> concordent avant de faire monter le score.</p>",
            "<h3 style='color:#f0932b'>Sources utilisees</h3><ul style='color:#9aa7b4'>",
        ]
        html += [f"<li>{item}</li>" for item in methodology.get("sources", [])]
        html.append("</ul><h3 style='color:#3fb950'>Ce qu'il ne fait jamais</h3>")
        html.append("<ul style='color:#9aa7b4'>")
        html += [f"<li>{item}</li>" for item in methodology.get("never_used", [])]
        html.append("</ul><h3 style='color:#d29922'>Faux positifs connus</h3>")
        html.append("<ul style='color:#9aa7b4'>")
        html += [f"<li>{item}</li>" for item in methodology.get("known_false_positives", [])]
        html.append("</ul><h3 style='color:#f0932b'>Echelle des verdicts</h3>")
        html.append("<ul style='color:#9aa7b4'>")
        html += [f"<li><b>{name}</b> : {value}</li>" for name, value in bands.items()]
        html.append("</ul>")
        html.append(
            f"<hr><p style='color:#6b7785;font-size:11px'>{data.get('disclaimer', '')}</p>"
        )
        self._methodology.setHtml("".join(html))


def _extract_recommendation(report_text: str) -> str:
    marker = "--- Recommandation"
    if marker not in report_text:
        return "Analyse effectuee."
    tail = report_text.split(marker, 1)[1]
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    # La première ligne est la bordure de section, la suivante porte le conseil.
    return lines[1] if len(lines) > 1 else "Analyse effectuee."


def _wrap_scroll(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(widget)
    return area
