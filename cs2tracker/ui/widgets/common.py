"""Widgets réutilisables de l'interface."""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cs2tracker.ui import theme


class Card(QFrame):
    """Panneau arrondi standard, avec titre optionnel."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(10)
        if title:
            label = QLabel(title.upper())
            label.setObjectName("CardTitle")
            self._layout.addWidget(label)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


class StatTile(QFrame):
    """Tuile « valeur + libellé », brique de base des tableaux de bord."""

    def __init__(
        self,
        label: str,
        value: str = "—",
        hint: str = "",
        color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardElevated")
        self.setMinimumWidth(130)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)

        self._value = QLabel(value)
        self._value.setObjectName("StatValue")
        if color:
            self._value.setStyleSheet(f"color: {color};")

        self._label = QLabel(label.upper())
        self._label.setObjectName("StatLabel")

        layout.addWidget(self._value)
        layout.addWidget(self._label)

        self._hint = QLabel(hint)
        self._hint.setObjectName("Muted")
        self._hint.setVisible(bool(hint))
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

    def set_value(self, value: str, color: str | None = None) -> None:
        self._value.setText(value)
        self._value.setStyleSheet(f"color: {color};" if color else "")

    def set_hint(self, hint: str) -> None:
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))


class Badge(QLabel):
    """Pastille colorée pour un statut court."""

    def __init__(
        self, text: str = "", color: str = theme.TEXT_MUTED, parent: QWidget | None = None
    ) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.set_style(color)

    def set_style(self, color: str) -> None:
        self.setStyleSheet(
            f"""
            background-color: {_with_alpha(color, 0.15)};
            color: {color};
            border: 1px solid {_with_alpha(color, 0.45)};
            border-radius: 10px;
            padding: 3px 12px;
            font-size: 11px;
            font-weight: 700;
            """
        )

    def set_status(self, text: str, color: str) -> None:
        self.setText(text)
        self.set_style(color)


class ScoreGauge(QWidget):
    """Jauge de score de suspicion avec verdict et niveau de confiance."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self._score = QLabel("—")
        self._score.setStyleSheet(
            f"font-size: 40px; font-weight: 800; color: {theme.TEXT_MUTED};"
        )
        self._verdict = Badge("EN ATTENTE", theme.TEXT_MUTED)
        header.addWidget(self._score)
        header.addWidget(QLabel("/ 100"))
        header.addStretch(1)
        header.addWidget(self._verdict)
        layout.addLayout(header)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        layout.addWidget(self._bar)

        self._detail = QLabel("Aucune analyse effectuee.")
        self._detail.setObjectName("Muted")
        self._detail.setWordWrap(True)
        layout.addWidget(self._detail)

    def update_score(
        self, score: float, verdict: str, label: str, confidence: float
    ) -> None:
        color = theme.VERDICT_COLORS.get(verdict, theme.score_color(score))
        self._score.setText(f"{score:.0f}")
        self._score.setStyleSheet(
            f"font-size: 40px; font-weight: 800; color: {color};"
        )
        self._verdict.set_status(verdict, color)
        self._bar.setValue(int(round(score)))
        self._bar.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {color}; border-radius: 7px; }}"
        )
        self._detail.setText(f"{label} — confiance de l'analyse : {confidence * 100:.0f} %")

    def reset(self) -> None:
        self._score.setText("—")
        self._bar.setValue(0)
        self._verdict.set_status("EN ATTENTE", theme.TEXT_MUTED)
        self._detail.setText("Aucune analyse effectuee.")


class DataTable(QTableWidget):
    """Tableau en lecture seule préconfiguré."""

    def __init__(self, headers: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

    def fill(self, rows: Sequence[Sequence[Any]], colors: Sequence[str | None] = ()) -> None:
        """Remplit le tableau ; ``colors`` colore la première colonne par ligne."""
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if column_index > 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column_index == 0 and row_index < len(colors) and colors[row_index]:
                    item.setForeground(QColor(colors[row_index]))
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                self.setItem(row_index, column_index, item)

    def clear_rows(self) -> None:
        self.setRowCount(0)


class SectionHeader(QWidget):
    """En-tête de page : titre + sous-titre."""

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("PageSubtitle")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)


def tile_row(tiles: Sequence[StatTile]) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for tile in tiles:
        layout.addWidget(tile)
    layout.addStretch(1)
    return container


def _with_alpha(hex_color: str, alpha: float) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return hex_color
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"
