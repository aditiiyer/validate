"""Review Performance tab: placeholder.

Will load per-patient predicted-vs-observed results and show
calibration/performance (AUC, Brier score, calibration curve).
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt

from validate.gui import theme


class PerformanceTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("Coming soon.")
        label.setFont(theme.headingFont(label))
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
