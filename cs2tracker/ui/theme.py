"""Thème sombre de l'interface : palette, typographie et feuille de style Qt."""

from __future__ import annotations

from typing import Final

# --- Palette -----------------------------------------------------------------
BG_DEEP: Final = "#0d1117"
BG_BASE: Final = "#131a23"
BG_PANEL: Final = "#182029"
BG_ELEVATED: Final = "#1e2732"
BORDER: Final = "#2a3441"
BORDER_STRONG: Final = "#3a4756"

TEXT_PRIMARY: Final = "#e6edf3"
TEXT_SECONDARY: Final = "#9aa7b4"
TEXT_MUTED: Final = "#6b7785"

ACCENT: Final = "#f0932b"
ACCENT_HOVER: Final = "#ffa940"
ACCENT_SOFT: Final = "#3a2a12"

CT_BLUE: Final = "#5aa9e6"
T_YELLOW: Final = "#e8b33a"

SUCCESS: Final = "#3fb950"
INFO: Final = "#58a6ff"
WARNING: Final = "#d29922"
DANGER: Final = "#f85149"
CRITICAL: Final = "#ff5c5c"

VERDICT_COLORS: Final[dict[str, str]] = {
    "CLEAN": SUCCESS,
    "LOW": INFO,
    "MODERATE": WARNING,
    "HIGH": DANGER,
    "CRITICAL": CRITICAL,
    "INDETERMINE": TEXT_MUTED,
}

SEVERITY_COLORS: Final[dict[str, str]] = {
    "critique": CRITICAL,
    "eleve": DANGER,
    "moyen": WARNING,
    "faible": INFO,
    "info": TEXT_MUTED,
}

FONT_FAMILY: Final = "Segoe UI, Inter, Roboto, sans-serif"
MONO_FAMILY: Final = "Cascadia Mono, Consolas, monospace"


def score_color(score: float) -> str:
    """Couleur associée à un score de suspicion 0..100."""
    if score >= 85:
        return CRITICAL
    if score >= 70:
        return DANGER
    if score >= 50:
        return WARNING
    if score >= 30:
        return INFO
    return SUCCESS


STYLESHEET: Final = f"""
QWidget {{
    background-color: {BG_BASE};
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}

QMainWindow, QDialog {{ background-color: {BG_DEEP}; }}

/* --- Navigation laterale ------------------------------------------------- */
#Sidebar {{
    background-color: {BG_DEEP};
    border-right: 1px solid {BORDER};
}}
#SidebarTitle {{
    color: {ACCENT};
    font-size: 17px;
    font-weight: 700;
    padding: 18px 16px 4px 16px;
}}
#SidebarSubtitle {{
    color: {TEXT_MUTED};
    font-size: 11px;
    padding: 0 16px 16px 16px;
}}
QPushButton#NavButton {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-left: 3px solid transparent;
    padding: 11px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#NavButton:hover {{
    background-color: {BG_PANEL};
    color: {TEXT_PRIMARY};
}}
QPushButton#NavButton:checked {{
    background-color: {BG_PANEL};
    color: {ACCENT};
    border-left: 3px solid {ACCENT};
    font-weight: 600;
}}

/* --- Cartes et panneaux --------------------------------------------------- */
QFrame#Card {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#CardElevated {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER_STRONG};
    border-radius: 10px;
}}
QLabel#CardTitle {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#StatValue {{
    color: {TEXT_PRIMARY};
    font-size: 24px;
    font-weight: 700;
}}
QLabel#StatLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QLabel#PageTitle {{
    color: {TEXT_PRIMARY};
    font-size: 21px;
    font-weight: 700;
}}
QLabel#PageSubtitle {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#Muted {{ color: {TEXT_MUTED}; }}
QLabel#Mono {{ font-family: {MONO_FAMILY}; color: {TEXT_SECONDARY}; }}

/* --- Champs --------------------------------------------------------------- */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {BG_DEEP};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit::placeholder {{ color: {TEXT_MUTED}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_SOFT};
}}

/* --- Boutons -------------------------------------------------------------- */
QPushButton {{
    background-color: {BG_ELEVATED};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 8px 16px;
    color: {TEXT_PRIMARY};
    font-weight: 500;
}}
QPushButton:hover {{ background-color: {BORDER}; }}
QPushButton:pressed {{ background-color: {BG_PANEL}; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; background-color: {BG_PANEL}; }}
QPushButton#Primary {{
    background-color: {ACCENT};
    color: #1a1206;
    border: none;
    font-weight: 700;
}}
QPushButton#Primary:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton#Primary:disabled {{ background-color: {ACCENT_SOFT}; color: {TEXT_MUTED}; }}
QPushButton#Danger {{
    background-color: transparent;
    border: 1px solid {DANGER};
    color: {DANGER};
}}
QPushButton#Danger:hover {{ background-color: rgba(248, 81, 73, 0.12); }}

/* --- Tableaux ------------------------------------------------------------- */
QTableWidget, QTableView {{
    background-color: {BG_PANEL};
    alternate-background-color: {BG_ELEVATED};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background-color: {BG_DEEP};
    color: {TEXT_SECONDARY};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
    font-size: 11px;
}}
QTableWidget::item {{ padding: 6px; }}

/* --- Barres et onglets ---------------------------------------------------- */
QProgressBar {{
    background-color: {BG_DEEP};
    border: 1px solid {BORDER};
    border-radius: 8px;
    height: 16px;
    text-align: center;
    color: {TEXT_PRIMARY};
    font-size: 11px;
}}
QProgressBar::chunk {{ border-radius: 7px; }}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background-color: {BG_PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    padding: 9px 18px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover {{ color: {TEXT_PRIMARY}; }}

/* --- Divers --------------------------------------------------------------- */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG}; border-radius: 5px; min-width: 30px;
}}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 4px;
    background-color: {BG_DEEP};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QStatusBar {{
    background-color: {BG_DEEP};
    color: {TEXT_MUTED};
    border-top: 1px solid {BORDER};
}}
QToolTip {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_STRONG};
    padding: 6px;
    border-radius: 4px;
}}
QSplitter::handle {{ background-color: {BORDER}; }}
"""
