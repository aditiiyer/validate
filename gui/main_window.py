"""Main window: the shared settings (analysis folder, data folder, dosimetric model)
above the Segment, Model and Review tabs.

The settings in the form are written to <analysis folder>/analysis.yaml only after the
user confirms, in a pop-up shown before a run, a tab switch or closing the window
whenever the form differs from the saved file (see ensureSaved).

An analysis holds one dosimetric model: changing the model of a saved analysis begins
a new analysis in another folder (default <Data Dir>/analysis_<model>).
"""

import os
from importlib.metadata import version, PackageNotFoundError

from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFileDialog, QGroupBox, QMessageBox, QDialog, QDialogButtonBox
)

from cerr.roe import dosimetric_models as doseModels

from validate.gui.segment_tab import SegmentTab
from validate.gui.model_tab import ModelTab
from validate.gui.performance_tab import PerformanceTab
from validate.gui.progress_and_logging import LABEL_WIDTH
from validate.gui import theme
from validate.core import analysis
from validate.data_io.read_inputs import discoverPatients, inferFileFormat
from validate import logs

TAB_NAMES = ["segment", "model", "review"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            self.setWindowTitle(f"VALIDATE v{version('validate')}")   # from pyproject.toml
        except PackageNotFoundError:    # run from source without installing
            self.setWindowTitle("VALIDATE")
        self.resize(780, 830)
        self._loaded = None          # settings last read from analysis.yaml
        self._modelFiles = {}        # model name -> file, for models from loaded settings
        self._prevDefaultDir = ""    # the default analysis folder last filled in

        central = QWidget()
        centralLayout = QVBoxLayout(central)
        centralLayout.addWidget(self._buildHeader())

        self.tabs = QTabWidget()
        # Set the tab bar's actual font (not just a QSS font-size) so Qt's
        # tab-size-hint calculation matches what's rendered -- otherwise the
        # reserved tab width lags the larger stylesheet font and clips text.
        self.tabs.tabBar().setFont(theme.headingFont(self.tabs.tabBar()))
        self.segmentTab = SegmentTab(self)
        self.tabs.addTab(self.segmentTab, "Segment")
        self.modelTab = ModelTab(self)
        self.tabs.addTab(self.modelTab, "Model")
        self.tabs.addTab(PerformanceTab(), "Review")
        self._currentTab = 0
        self.tabs.currentChanged.connect(self._onTabChanged)
        centralLayout.addWidget(self.tabs, stretch=1)
        self.setCentralWidget(central)

        self._currentModel = self.modelName()
        self._onModelChanged()

    def _buildHeader(self):
        header = QGroupBox("Analysis")
        headerLayout = QVBoxLayout(header)
        headerLayout.setSpacing(10)

        self.dataDirEdit = QLineEdit()
        self.dataDirEdit.setPlaceholderText("Cohort directory (one DICOM subdirectory per patient); "
                                            "empty for pre-computed predictors.")
        self.dataDirEdit.editingFinished.connect(self._onDataDirChanged)
        self.analysisDirEdit = QLineEdit()
        self.analysisDirEdit.setPlaceholderText("Holds analysis settings, logs, and results.")
        self.analysisDirEdit.editingFinished.connect(self._loadSettings)
        dataRow = self._folderRow("Data:", self.dataDirEdit, self._browseDataDir)
        outputRow = self._folderRow("Output:", self.analysisDirEdit, self._browseAnalysisDir)

        headerLayout.addLayout(dataRow)
        modelRow = QHBoxLayout()
        modelLabel = QLabel("Model:")
        modelLabel.setFont(theme.headingFont(modelLabel))
        modelLabel.setMinimumWidth(LABEL_WIDTH)
        self.modelCombo = QComboBox()
        self.modelCombo.addItems(doseModels.listModels())
        defaultIdx = self.modelCombo.findText("Xerostomia (grade 2+)")
        if defaultIdx >= 0:
            self.modelCombo.setCurrentIndex(defaultIdx)
        self.modelCombo.currentTextChanged.connect(self._onModelSelected)
        modelRow.addWidget(modelLabel)
        modelRow.addWidget(self.modelCombo)
        modelRow.addStretch()
        headerLayout.addLayout(modelRow)
        headerLayout.addLayout(outputRow)
        return header

    def _folderRow(self, label, edit, onBrowse):
        row = QHBoxLayout()
        rowLabel = QLabel(label)
        rowLabel.setFont(theme.headingFont(rowLabel))
        rowLabel.setMinimumWidth(LABEL_WIDTH)
        browseBtn = QPushButton("Browse...")
        browseBtn.clicked.connect(onBrowse)
        row.addWidget(rowLabel)
        row.addWidget(edit)
        row.addWidget(browseBtn)
        return row

    # Shared settings, used by the tabs

    def analysisDir(self):
        return self.analysisDirEdit.text().strip() or None

    def dataDir(self):
        return self.dataDirEdit.text().strip() or None

    def modelName(self):
        return self.modelCombo.currentText()

    def modelFile(self):
        name = self.modelName()
        if not name:
            return None
        return self._modelFiles.get(name) or doseModels.mapModelToFile(name)

    def patients(self):
        """Patient IDs in the data folder ([] if there is none)."""
        try:
            return [patientId for patientId, _ in discoverPatients(self.dataDir())] if self.dataDir() else []
        except OSError:
            return []

    def taskLog(self):
        """The analysis folder's task log, or None if there is none (or it can't be read)."""
        try:
            return logs.readTaskLog(self.analysisDir()) if self.analysisDir() else None
        except ValueError:
            return None

    def goToTab(self, name):
        self.tabs.setCurrentIndex(TAB_NAMES.index(name))

    def setCohortDir(self, cohortDir):
        """Pre-fill Data Dir (see __main__.py's optional command-line argument)."""
        self.dataDirEdit.setText(cohortDir)
        self._onDataDirChanged()

    # Form

    def _browseAnalysisDir(self):
        path = QFileDialog.getExistingDirectory(self, "Select analysis folder", self.analysisDirEdit.text())
        if path:
            self.analysisDirEdit.setText(path)
            self._loadSettings()

    def _browseDataDir(self):
        path = QFileDialog.getExistingDirectory(self, "Select cohort directory", self.dataDirEdit.text())
        if path:
            self.dataDirEdit.setText(path)
            self._onDataDirChanged()

    def _defaultAnalysisDir(self, modelName=None):
        dataDir = self.dataDir()
        return os.path.join(dataDir, f"analysis_{modelName or self.modelName()}") if dataDir else None

    def _onDataDirChanged(self):
        """The analysis folder defaults to <Data Dir>/analysis_<model>, unless one was chosen."""
        default = self._defaultAnalysisDir() or ""
        if self.analysisDirEdit.text().strip() in ("", self._prevDefaultDir) and default != self._prevDefaultDir:
            self._prevDefaultDir = default
            self.analysisDirEdit.setText(default)
            self._loadSettings()
        else:
            self._onModelChanged()

    def _onModelSelected(self, modelName):
        """Changing the model of a saved analysis begins a new analysis, after the
        user confirms and picks its folder. Cancel keeps the current model."""
        if modelName == self._currentModel:
            return
        if self._loaded is None:
            # Nothing saved yet: keep a default analysis folder in step with the model
            self._currentModel = modelName
            if self.analysisDirEdit.text().strip() in ("", self._prevDefaultDir) and self.dataDir():
                self._prevDefaultDir = self._defaultAnalysisDir()
                self.analysisDirEdit.setText(self._prevDefaultDir)
                self._loadSettings()
            else:
                self._onModelChanged()
            return

        folder = self._askNewAnalysis(modelName)
        if folder is None:
            self.modelCombo.blockSignals(True)
            self.modelCombo.setCurrentText(self._currentModel)
            self.modelCombo.blockSignals(False)
            return
        # Keep Data Dir, the CSVs and the install folder; reset everything else
        self._currentModel = modelName
        self._loaded = None
        self.analysisDirEdit.setText(folder)
        self.segmentTab.resetSettings()
        self._loadSettings()      # the folder may already hold an analysis

    def _askNewAnalysis(self, modelName):
        """Ask to begin a new analysis for modelName. Returns its folder, or None if cancelled."""
        dialog = QDialog(self)
        dialog.setWindowTitle("New analysis")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Begin new analysis?"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Select analysis folder:"))
        folderEdit = QLineEdit(self._defaultAnalysisDir(modelName) or "")
        folderEdit.setMinimumWidth(420)
        browseBtn = QPushButton("Browse...")
        browseBtn.clicked.connect(lambda: folderEdit.setText(
            QFileDialog.getExistingDirectory(dialog, "Select analysis folder", folderEdit.text())
            or folderEdit.text()))
        row.addWidget(folderEdit)
        row.addWidget(browseBtn)
        layout.addLayout(row)
        buttons = QDialogButtonBox()
        buttons.addButton("Start new analysis", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() != QDialog.Accepted:
            return None
        folder = folderEdit.text().strip()
        if not folder:
            return None
        if self.analysisDir() and os.path.realpath(folder) == os.path.realpath(self.analysisDir()):
            QMessageBox.warning(self, "New analysis", "Choose a different folder for the new analysis.")
            return None
        return folder

    def _loadSettings(self):
        """Fill the form from the analysis folder's analysis.yaml, if there is one."""
        analysisDir = self.analysisDir()
        try:
            settings = analysis.readSettings(analysisDir) if analysisDir else None
        except Exception as exc:
            QMessageBox.critical(self, "Settings", f"Could not read {analysis.FILE_NAME}: {exc}")
            return
        self._loaded = settings
        if not settings:
            self._onModelChanged()
            return
        inputs = settings.get("input") or {}
        self.dataDirEdit.setText(inputs.get("data_dir") or "")
        model = settings.get("model") or {}
        if model.get("name"):
            if model.get("file"):
                self._modelFiles[model["name"]] = model["file"]
            if self.modelCombo.findText(model["name"]) < 0:
                self.modelCombo.addItem(model["name"])
            self.modelCombo.blockSignals(True)
            self.modelCombo.setCurrentText(model["name"])
            self.modelCombo.blockSignals(False)
            self._currentModel = model["name"]
        self.segmentTab.loadSettings(settings)
        self.modelTab.loadSettings(settings)
        self._onModelChanged(settings)

    def _onModelChanged(self, settings=None):
        modelFile = self.modelFile()
        self.segmentTab.setModel(modelFile, ((settings or {}).get("segment") or {}).get("ai_models")
                                 if settings else None)
        self.modelTab.setModel(modelFile, (settings or {}).get("structures"))

    def formSettings(self):
        """The settings in the form, in analysis.yaml's layout."""
        dataDir = self.dataDir()
        segmentPart = self.segmentTab.settingsPart()
        modelPart = self.modelTab.settingsPart()
        fromPredictors = dataDir is None
        return {
            "input": {"start_from": "predictors" if fromPredictors else self._startFrom(dataDir),
                      "data_dir": dataDir,
                      **modelPart["input"],
                      # Not set in the GUI; kept from the loaded settings
                      "outcomes_csv": ((self._loaded or {}).get("input") or {}).get("outcomes_csv")},
            "compute": segmentPart["compute"],
            "model": {"name": self.modelName(), "file": self.modelFile()},
            "segment": {"ai_models": [], "install_dir": None} if fromPredictors else segmentPart["segment"],
            "structures": {} if fromPredictors else modelPart["structures"],
        }

    def _startFrom(self, dataDir):
        """dicom, nifti or nrrd: kept from the loaded settings for the same data
        folder, else found from the first patient folder with readable data."""
        loadedInputs = (self._loaded or {}).get("input") or {}
        if loadedInputs.get("data_dir") == dataDir and loadedInputs.get("start_from"):
            return loadedInputs["start_from"]
        try:
            for _, patientDir in discoverPatients(dataDir):
                try:
                    fileFormat = inferFileFormat(patientDir)
                except ValueError:
                    continue
                if fileFormat == "dicom":
                    return "dicom"
                hasNrrd = any(name.lower().endswith(".nrrd") for name in os.listdir(patientDir))
                return "nrrd" if hasNrrd else "nifti"
        except OSError:
            pass
        return "dicom"

    # Saving

    def ensureSaved(self, required=False, closing=False):
        """Make sure analysis.yaml holds the form's settings, asking the user first.

        If the form differs from the saved settings, a pop-up asks to save them
        (noting any results they will clear) with Save and continue / Cancel.

        Args:
            required (bool): True before a run, which needs an analysis folder;
                False for a tab switch or closing, which go ahead without one.
            closing (bool): True when closing the window; the pop-up then also
                offers Close without saving.

        Returns:
            bool: True to continue, False if the user cancelled.
        """
        analysisDir = self.analysisDir()
        if analysisDir is None:
            if required:
                QMessageBox.warning(self, "Analysis folder", "Choose an analysis folder (or a Data Dir) first.")
            return not required
        try:
            old = analysis.readSettings(analysisDir)
            taskLog = logs.readTaskLog(analysisDir)
        except Exception as exc:
            QMessageBox.critical(self, "Settings", str(exc))
            return False
        new = self.formSettings()
        if old == new:
            return True

        lines = []
        clearedTabs = [tab for tab in logs.TABS
                       if old is not None and _hasResults(taskLog, tab)
                       and analysis.tabSettings(old, tab) != analysis.tabSettings(new, tab)]
        for tab in clearedTabs:
            label = self.segmentTab.RESULTS_LABEL if tab == "segment" else self.modelTab.RESULTS_LABEL
            lines.append(f"⚠ This will clear the {label} already computed.")

        target = os.path.join(analysisDir, analysis.FILE_NAME) if old is not None else analysisDir
        box = QMessageBox(self)
        box.setWindowTitle("Save settings")
        box.setText("\n\n".join([f"Save settings to {target}?"] + lines))
        saveBtn = box.addButton("Save and continue", QMessageBox.AcceptRole)
        discardBtn = box.addButton("Close without saving", QMessageBox.DestructiveRole) if closing else None
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        if discardBtn is not None and box.clickedButton() is discardBtn:
            return True
        if box.clickedButton() is not saveBtn:
            return False
        try:
            analysis.saveSettings(new, analysisDir)
        except Exception as exc:
            QMessageBox.critical(self, "Settings not saved", str(exc))
            return False
        for tab in clearedTabs:
            logs.clearResults(analysisDir, tab)
        self._loaded = analysis.readSettings(analysisDir)
        return True

    def _onTabChanged(self, index):
        if index == self._currentTab:
            return
        if not self.ensureSaved():
            # Stay on the tab the user was on
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(self._currentTab)
            self.tabs.blockSignals(False)
            return
        self._currentTab = index

    def closeEvent(self, event):
        # Only an analysis whose settings were saved before is asked about; otherwise just close
        analysisDir = self.analysisDir()
        started = analysisDir is not None and os.path.exists(os.path.join(analysisDir, analysis.FILE_NAME))
        if not started or self.ensureSaved(closing=True):
            event.accept()
        else:
            event.ignore()


def _hasResults(taskLog, tab):
    section = logs.TAB_SECTIONS[tab]
    return any(section in entry for entry in ((taskLog or {}).get("patients") or {}).values())

