from PyQt5.QtWidgets import QMainWindow, QTabWidget

from validate.gui.model_tab import ModelTab
from validate.gui.performance_tab import PerformanceTab
from validate.gui import theme


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VALIDATE v0.1.0")
        self.resize(1150, 800)

        tabs = QTabWidget()
        # Set the tab bar's actual font (not just a QSS font-size) so Qt's
        # tab-size-hint calculation matches what's rendered -- otherwise the
        # reserved tab width lags the larger stylesheet font and clips text.
        tabs.tabBar().setFont(theme.headingFont(tabs.tabBar()))
        self.modelTab = ModelTab()
        tabs.addTab(self.modelTab, "Apply Model")
        tabs.addTab(PerformanceTab(), "Review Performance")
        self.setCentralWidget(tabs)

    def setCohortDir(self, cohortDir):
        """Pre-fill the Apply Model tab's Data Dir field (see __main__.py's
        optional command-line argument).
        """
        self.modelTab.cohortDirEdit.setText(cohortDir)
