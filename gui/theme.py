"""Dark theme, with an accent color nodding to CERR ROE's teal
(cerr/CERR_core/PlanAnalysis/ROE.m: figColor [.6 .75 .75]).

Design principles applied:
    - Contrast: light text on dark surfaces (~13:1), muted secondary text
      for de-emphasis (placeholders, disabled controls) without hiding it.
    - Consistency: one spacing unit (4px) and one corner radius (4px) reused
      throughout; identical treatment for all buttons/inputs/tables.
    - Hierarchy: primary actions (Run, Next) are filled teal; the other buttons
      are gray. Sections are separated by space rather than boxes, with small,
      muted, uppercase titles; the selected tab is raised and underlined in teal.
    - Legibility: font sizes scale from the platform's default font (13pt on
      macOS, ~9-10pt on Linux/Windows, where Qt maps points to pixels
      differently), with a 10pt floor, since smaller defaults read small.
"""

import os

from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import Qt

MIN_BASE_POINT_SIZE = 10
# Point sizes relative to the base (the platform's default font size)
HEADING_OFFSET = 1
GROUP_TITLE_OFFSET = -1
TAB_OFFSET = 1
_baseSize = MIN_BASE_POINT_SIZE   # set by apply()

BG = "#1e2222"            # window background
SURFACE = "#282e2e"        # panels / group boxes
FIELD = "#323a3a"          # inputs, table cells
FIELD_ALT = "#3a4343"      # alternating table rows
BORDER = "#454f4f"
TEXT = "#e8efef"
TEXT_MUTED = "#9fb0b0"
ACCENT = "#4fb8ac"         # ROE-teal-derived accent
ACCENT_HOVER = "#63ccc0"
ACCENT_TEXT = "#0d1a19"
PRIMARY = "#2a7f76"         # primary buttons: a darker teal, with a lighter edge
PRIMARY_HOVER = "#31938a"
PRIMARY_PRESSED = "#226a63"
PRIMARY_BORDER = "#3fa197"
PRIMARY_BORDER_TOP = "#5cbcb1"
PRIMARY_TEXT = "#f2f7f7"
TAB_HOVER = "#242a2a"
DISABLED_TEXT = "#5c6868"
DISABLED_BORDER = "#353d3d"
SECTION_SPACING = 32        # px between sections
ROW_SPACING = 10            # px between rows in a section
CHECK_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check.svg").replace(os.sep, "/")

def styleSheet(groupTitleSize):
    """The app stylesheet, with group titles at groupTitleSize (pt)."""
    return f"""
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}

QGroupBox {{
    background: transparent;
    border: none;
    margin-top: 18px;
    padding: 8px 0 0 0;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 0;
    padding: 0;
    color: {TEXT_MUTED};
    font-size: {groupTitleSize}pt;
    font-weight: 600;
}}

QFrame#divider {{ background: {BORDER}; border: none; min-height: 1px; max-height: 1px; }}

QLabel {{ background: transparent; }}
QLabel:disabled {{ color: {TEXT_MUTED}; }}

QLineEdit, QComboBox {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 7px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled {{ color: {TEXT_MUTED}; background: {SURFACE}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {FIELD}; color: {TEXT}; selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT}; border: 1px solid {BORDER};
}}

QPushButton {{
    background: {FIELD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 16px;
}}
QPushButton:hover {{ background: {FIELD_ALT}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT}; color: {ACCENT_TEXT}; border-color: {ACCENT}; }}
/* "Primary" (theme.markPrimary) buttons: filled teal, bolder and roomier, as the CTA. */
QPushButton#primaryButton {{
    background: {PRIMARY};
    color: {PRIMARY_TEXT};
    border: 1px solid {PRIMARY_BORDER};
    border-top-color: {PRIMARY_BORDER_TOP};
    font-weight: 600;
    padding: 8px 22px;
}}
QPushButton#primaryButton:hover {{ background: {PRIMARY_HOVER}; }}
QPushButton#primaryButton:pressed {{ background: {PRIMARY_PRESSED}; }}
/* Notify when done: a teal outline, quieter than the filled primary buttons */
QPushButton#notifyButton {{
    background: transparent;
    color: {ACCENT};
    border: 1px solid {PRIMARY_BORDER};
}}
QPushButton#notifyButton:hover {{ background: {TAB_HOVER}; border-color: {ACCENT}; }}
QPushButton#notifyButton:pressed {{ background: {PRIMARY_PRESSED}; color: {PRIMARY_TEXT}; }}
QPushButton:disabled, QPushButton#primaryButton:disabled {{
    background: transparent;
    color: {DISABLED_TEXT};
    border: 1px solid {DISABLED_BORDER};
}}

QRadioButton, QCheckBox {{ background: transparent; spacing: 8px; }}

QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 9px;
    border: 2px solid {TEXT_MUTED};
    background: {FIELD};
}}
QRadioButton::indicator:hover {{ border-color: {ACCENT_HOVER}; }}
QRadioButton::indicator:checked {{
    border: 2px solid {ACCENT};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        fx:0.5, fy:0.5, stop:0 {ACCENT}, stop:0.55 {ACCENT}, stop:0.65 {FIELD}, stop:1 {FIELD});
}}
QRadioButton::indicator:checked:hover {{ border-color: {ACCENT_HOVER}; }}
QRadioButton::indicator:disabled {{ border-color: {BORDER}; background: {SURFACE}; }}
QRadioButton::indicator:checked:disabled {{
    border-color: {BORDER};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        fx:0.5, fy:0.5, stop:0 {TEXT_MUTED}, stop:0.55 {TEXT_MUTED}, stop:0.65 {SURFACE}, stop:1 {SURFACE});
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 2px solid {TEXT_MUTED};
    background: {FIELD};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT_HOVER}; }}
QCheckBox::indicator:checked {{ border: 2px solid {ACCENT}; background: {ACCENT}; image: url({CHECK_ICON}); }}
QCheckBox::indicator:disabled {{ border-color: {BORDER}; background: {SURFACE}; }}
QCheckBox::indicator:checked:disabled {{ border-color: {BORDER}; background: {BORDER}; image: url({CHECK_ICON}); }}

/* Grayed-out (disabled) controls keep their state visible, in muted text */
QRadioButton:disabled, QCheckBox:disabled, QTableWidget:disabled, QHeaderView::section:disabled {{
    color: {TEXT_MUTED};
}}

QTableWidget {{
    background: {FIELD};
    alternate-background-color: {FIELD_ALT};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}
QTableWidget::item {{ padding: 4px; }}
QTableWidget::item:selected {{ background: {ACCENT}; color: {ACCENT_TEXT}; }}
QHeaderView::section {{
    background: {SURFACE};
    color: {TEXT};
    padding: 7px 8px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}

QProgressBar {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT};
    min-height: 18px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

QTabWidget::pane {{ background: {BG}; border: none; border-top: 1px solid {BORDER}; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 10px 22px;
    margin-right: 4px;
    border: none;
    border-bottom: 3px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{ background: {SURFACE}; color: {TEXT}; border-bottom: 3px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ background: {TAB_HOVER}; color: {TEXT}; }}

QScrollBar:vertical {{ background: {SURFACE}; width: 12px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QMessageBox {{ background: {SURFACE}; }}
"""


def palette():
    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor(BG))
    pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor(FIELD))
    pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(FIELD_ALT))
    pal.setColor(QtGui.QPalette.Text, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor(TEXT_MUTED))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor(FIELD))
    pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(SURFACE))
    pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(TEXT))
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(ACCENT))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(ACCENT_TEXT))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(TEXT_MUTED))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(TEXT_MUTED))
    return pal


def apply(app):
    """Apply the dark theme + base font size application-wide.

    The base size is the platform's default font size, at least MIN_BASE_POINT_SIZE.
    """
    global _baseSize
    font = QtGui.QFont(app.font())
    # pointSize() is -1 if the default font is sized in pixels
    _baseSize = max(font.pointSize(), MIN_BASE_POINT_SIZE)

    app.setStyle("Fusion")
    app.setPalette(palette())
    app.setStyleSheet(styleSheet(_baseSize + GROUP_TITLE_OFFSET))

    font.setPointSize(_baseSize)
    app.setFont(font)


def headingFont(widget):
    """Bold, slightly larger font for a section-heading QLabel."""
    font = QtGui.QFont(widget.font())
    font.setPointSize(_baseSize + HEADING_OFFSET)
    font.setBold(True)
    return font


# Tab weights, set on the tab bar itself (see main_window)
TAB_BAR_STYLE = "QTabBar::tab { font-weight: normal; } QTabBar::tab:selected { font-weight: 600; }"


def tabFont(widget):
    """The tab bar's font: a step up from body text, and semibold, the selected tab's
    weight, so Qt sizes the tabs to fit it (TAB_BAR_STYLE sets the others' weight)."""
    font = QtGui.QFont(widget.font())
    font.setPointSize(_baseSize + TAB_OFFSET)
    font.setWeight(QtGui.QFont.DemiBold)
    return font


def section(title):
    """A section: a QGroupBox with an uppercase title (Qt stylesheets can't
    transform text), and its QVBoxLayout at the theme's row spacing."""
    group = QtWidgets.QGroupBox(title.upper())
    layout = QtWidgets.QVBoxLayout(group)
    layout.setSpacing(ROW_SPACING)
    layout.setContentsMargins(0, 4, 0, 0)
    return group, layout


def divider():
    """A thin horizontal line between sections."""
    line = QtWidgets.QFrame()
    line.setObjectName("divider")
    return line


def markPrimary(button):
    """Style a QPushButton as the primary (accent-colored) action."""
    button.setObjectName("primaryButton")
