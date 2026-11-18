"""Dark theme, with an accent color nodding to CERR ROE's teal
(cerr/CERR_core/PlanAnalysis/ROE.m: figColor [.6 .75 .75]).

Design principles applied:
    - Contrast: light text on dark surfaces (~13:1), muted secondary text
      for de-emphasis (placeholders, disabled controls) without hiding it.
    - Consistency: one spacing unit (4px) and one corner radius (4px) reused
      throughout; identical treatment for all buttons/inputs/tables.
    - Hierarchy: the one primary action (Run) is accent-colored and larger
      than secondary buttons (Browse/Export); section headings are bold and
      a step up in size from body text.
    - Legibility: a larger-than-default base point size app-wide, since the
      Qt/platform default (~9pt) reads small on modern displays.
"""

from PyQt5 import QtGui
from PyQt5.QtCore import Qt

BASE_POINT_SIZE = 10
HEADING_POINT_SIZE = 11
GROUP_TITLE_POINT_SIZE = 14
APP_TITLE_POINT_SIZE = 14

BG = "#1e2222"            # window background
SURFACE = "#282e2e"        # panels / group boxes
FIELD = "#323a3a"          # inputs, table cells
FIELD_ALT = "#3a4343"      # alternating table rows
BORDER = "#454f4f"
TEXT = "#e8efef"
TEXT_MUTED = "#9fb0b0"
ACCENT = "#4fb8ac"         # ROE-teal-derived accent
ACCENT_HOVER = "#63ccc0"
ACCENT_PRESSED = "#3c9187"
ACCENT_TEXT = "#0d1a19"
TAB_SELECTED = "#ffffff"   # tabs invert the theme: teal, dark text, selected white

STYLESHEET = f"""
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; }}

QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {ACCENT};
    font-size: {GROUP_TITLE_POINT_SIZE}pt;
    font-weight: 700;
}}

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
    border-radius: 4px;
    padding: 6px 16px;
}}
QPushButton:hover {{ background: {FIELD_ALT}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT}; color: {ACCENT_TEXT}; border-color: {ACCENT}; }}
QPushButton:disabled {{
    background: {SURFACE};
    color: {TEXT_MUTED};
    border: 1px dashed {BORDER};
}}

/* "Primary" (theme.markPrimary) buttons are the same gray-idle/teal-pressed
   states as any other button -- just bolder and roomier, as the CTA. */
QPushButton#primaryButton {{
    font-weight: 600;
    padding: 8px 22px;
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

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 2px solid {TEXT_MUTED};
    background: {FIELD};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT_HOVER}; }}
QCheckBox::indicator:checked {{ border: 2px solid {ACCENT}; background: {ACCENT}; }}
QCheckBox::indicator:disabled {{ border-color: {BORDER}; background: {SURFACE}; }}

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

QTabWidget::pane {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 4px; }}
QTabBar::tab {{
    background: {ACCENT};
    color: {ACCENT_TEXT};
    font-weight: 600;
    padding: 10px 28px;
    margin-right: 4px;
    min-width: 110px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{ background: {TAB_SELECTED}; color: {ACCENT_TEXT}; }}
QTabBar::tab:hover:!selected {{ background: {ACCENT_HOVER}; }}

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
    """Apply the dark theme + base font size application-wide."""
    app.setStyle("Fusion")
    app.setPalette(palette())
    app.setStyleSheet(STYLESHEET)

    font = QtGui.QFont(app.font())
    font.setPointSize(BASE_POINT_SIZE)
    app.setFont(font)


def headingFont(widget):
    """Bold, slightly larger font for a section-heading QLabel."""
    font = QtGui.QFont(widget.font())
    font.setPointSize(HEADING_POINT_SIZE)
    font.setBold(True)
    return font


def appTitleFont(widget):
    """Bold, large font for the app's own header label."""
    font = QtGui.QFont(widget.font())
    font.setPointSize(APP_TITLE_POINT_SIZE)
    font.setBold(True)
    return font


def markPrimary(button):
    """Style a QPushButton as the primary (accent-colored) action."""
    button.setObjectName("primaryButton")
