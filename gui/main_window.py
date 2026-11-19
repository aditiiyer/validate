"""Main window: the shared settings (data folder, plan info, dosimetric model, analysis
folder) above the Segment, Model and Review tabs.

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
    QPushButton, QComboBox, QFileDialog, QMessageBox, QDialog, QDialogButtonBox, QToolButton,
    QRadioButton, QButtonGroup
)

from cerr.roe import dosimetric_models as doseModels

from validate.gui.segment_tab import SegmentTab
from validate.gui.model_tab import ModelTab
from validate.gui.performance_tab import PerformanceTab
from validate.gui import theme
from validate.core import analysis
from validate.data_io.read_inputs import discoverPatients, inferFileFormat
from validate import logs

TAB_NAMES = ["segment", "model", "review"]
HEADER_LABEL_WIDTH = 80     # Start from / Data / Plan info / Model / Output labels
PLAN_INFO_HELP = "Optional. Plan names, fractionation, scan files, existing structures (per case)."
PLAN_INFO_DETAILS = (
    "One row per patient. Only ID is required.\n\n"
    "ID: patient folder name.\n"
    "Plan name: RTDOSE file name, if a patient has more than one dose (DICOM).\n"
    "Prescribed dose (Gy), Fraction size (Gy), Fraction number: any two, if the model "
    "needs fractionation correction.\n"
    "Scan file, Dose file: file name or pattern (NIfTI/NRRD). Segment needs Scan file.\n"
    "<structure>: one column per structure the model needs, giving its name in the "
    "RTSTRUCT (DICOM), or its mask file or \"file:label\" (NIfTI/NRRD).")


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
        self._closePending = False   # closing once the run in progress stops

        central = QWidget()
        centralLayout = QVBoxLayout(central)
        centralLayout.setSpacing(24)
        centralLayout.addWidget(self._buildHeader())

        self.tabs = QTabWidget()
        # Set the tab bar's actual font (not just a QSS font-size) so Qt's
        # tab-size-hint calculation matches what's rendered -- otherwise the
        # reserved tab width lags the larger stylesheet font and clips text.
        self.tabs.tabBar().setFont(theme.tabFont(self.tabs.tabBar()))
        self.tabs.tabBar().setStyleSheet(theme.TAB_BAR_STYLE)
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
        header, headerLayout = theme.section("Analysis")

        self.dataDirEdit = QLineEdit()
        self.dataDirEdit.setPlaceholderText("Cohort directory (one subdirectory per patient).")
        self.dataDirEdit.editingFinished.connect(self._onDataDirChanged)
        self.analysisDirEdit = QLineEdit()
        self.analysisDirEdit.setPlaceholderText("Holds analysis settings, logs, and results.")
        self.analysisDirEdit.editingFinished.connect(self._loadSettings)
        dataRow = self._folderRow("Data:", self.dataDirEdit, self._browseDataDir)
        outputRow = self._folderRow("Output:", self.analysisDirEdit, self._browseAnalysisDir)

        # Plan info is used by both tabs (Segment reads the scan file names from it)
        self.planInfoEdit = QLineEdit()
        self.planInfoEdit.setPlaceholderText(PLAN_INFO_HELP)
        self.planInfoEdit.setToolTip(PLAN_INFO_HELP)
        planRow = self._folderRow("Plan info:", self.planInfoEdit, self._browsePlanInfo, "Select CSV")
        planInfoBtn = QToolButton()
        planInfoBtn.setText("i")
        planInfoBtn.setToolTip(PLAN_INFO_DETAILS)
        planRow.addWidget(planInfoBtn)

        # Start from images (Data, Plan info, Segment, structures) or pre-computed predictors
        startRow = QHBoxLayout()
        startLabel = QLabel("Start from:")
        startLabel.setFixedWidth(HEADER_LABEL_WIDTH)
        self.imagesRadio = QRadioButton("Data (DICOM/NIfTI)")
        self.predictorsRadio = QRadioButton("Pre-computed predictors")
        startGroup = QButtonGroup(header)
        startGroup.addButton(self.imagesRadio)
        startGroup.addButton(self.predictorsRadio)
        self.imagesRadio.setChecked(True)
        self.predictorsRadio.toggled.connect(self._onStartFromToggled)
        startRow.addWidget(startLabel)
        startRow.addWidget(self.imagesRadio)
        startRow.addSpacing(16)
        startRow.addWidget(self.predictorsRadio)
        startRow.addStretch()
        self._imageRows = (dataRow, planRow)

        headerLayout.addLayout(startRow)
        headerLayout.addLayout(dataRow)
        headerLayout.addLayout(planRow)
        modelRow = QHBoxLayout()
        modelLabel = QLabel("Model:")
        modelLabel.setFixedWidth(HEADER_LABEL_WIDTH)
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

    def _folderRow(self, label, edit, onBrowse, buttonText="Browse..."):
        row = QHBoxLayout()
        rowLabel = QLabel(label)
        rowLabel.setFixedWidth(HEADER_LABEL_WIDTH)
        browseBtn = QPushButton(buttonText)
        browseBtn.clicked.connect(onBrowse)
        row.addWidget(rowLabel)
        row.addWidget(edit)
        row.addWidget(browseBtn)
        return row

    # Shared settings, used by the tabs

    def analysisDir(self):
        return self.analysisDirEdit.text().strip() or None

    def fromPredictors(self):
        """True when starting from pre-computed predictors rather than images."""
        return self.predictorsRadio.isChecked()

    def dataDir(self):
        """The cohort folder; None when starting from pre-computed predictors."""
        return None if self.fromPredictors() else (self.dataDirEdit.text().strip() or None)

    def planInfo(self):
        """The plan info CSV; None when starting from pre-computed predictors."""
        return None if self.fromPredictors() else (self.planInfoEdit.text().strip() or None)

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

    def runningTask(self):
        """(label, thread, tab) for the run or AI model install in progress, or None.
        Only one runs at a time, since each run rewrites task_log.yaml."""
        for label, thread, tab in (("A Segment run", self.segmentTab.worker, self.segmentTab),
                                   ("A Model run", self.modelTab.worker, self.modelTab),
                                   ("An AI model install", self.segmentTab.installWorker, self.segmentTab)):
            if thread is not None and thread.isRunning():
                return label, thread, tab
        return None

    def checkIdle(self):
        """True if nothing is running; otherwise say what is, and return False."""
        task = self.runningTask()
        if task is None:
            return True
        QMessageBox.information(self, "Run in progress",
                                f"{task[0]} is in progress. Wait for it to finish, or stop it.")
        return False

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

    def _browsePlanInfo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select plan info CSV", self.dataDir() or "",
                                              "CSV files (*.csv)")
        if path:
            self.planInfoEdit.setText(path)

    def _defaultAnalysisDir(self, modelName=None):
        """<Data Dir>/analysis_<model>, or <predictors CSV folder>/analysis_<model> when
        starting from pre-computed predictors; None without either."""
        if self.fromPredictors():
            predictorsCsv = self.modelTab.predictorsCsv()
            baseDir = os.path.dirname(os.path.abspath(predictorsCsv)) if predictorsCsv else None
        else:
            baseDir = self.dataDir()
        return os.path.join(baseDir, f"analysis_{modelName or self.modelName()}") if baseDir else None

    def _onStartFromToggled(self):
        self._applyStartFrom()
        self._onDataDirChanged()

    def _applyStartFrom(self):
        """Starting from pre-computed predictors grays out Data, Plan info, the Segment
        tab and the Model tab's structures (their contents are kept, but not saved)."""
        fromPredictors = self.fromPredictors()
        for row in self._imageRows:
            for i in range(row.count()):
                widget = row.itemAt(i).widget()
                if widget is not None:
                    widget.setEnabled(not fromPredictors)
        segmentIndex = TAB_NAMES.index("segment")
        if fromPredictors and self.tabs.currentIndex() == segmentIndex:
            # Switch without the save prompt: the mode change isn't a tab switch by the user
            self.tabs.blockSignals(True)
            self.goToTab("model")
            self.tabs.blockSignals(False)
            self._currentTab = self.tabs.currentIndex()
        self.tabs.setTabEnabled(segmentIndex, not fromPredictors)
        self.modelTab.setFromPredictors(fromPredictors)

    def onPredictorsCsvChanged(self):
        """Called by the Model tab: the predictors CSV sets the default analysis
        folder when starting from pre-computed predictors."""
        if self.fromPredictors():
            self._onDataDirChanged()

    def _onDataDirChanged(self):
        """The analysis folder defaults to <Data Dir>/analysis_<model> (see
        _defaultAnalysisDir), unless one was chosen."""
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
            if self.analysisDirEdit.text().strip() in ("", self._prevDefaultDir) and self._defaultAnalysisDir(modelName):
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
        self.predictorsRadio.blockSignals(True)
        (self.predictorsRadio if inputs.get("start_from") == "predictors" else self.imagesRadio).setChecked(True)
        self.predictorsRadio.blockSignals(False)
        self._applyStartFrom()
        self.dataDirEdit.setText(inputs.get("data_dir") or "")
        self.planInfoEdit.setText(inputs.get("plan_structures_csv") or "")
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
        fromPredictors = self.fromPredictors()
        return {
            "input": {"start_from": "predictors" if fromPredictors else self._startFrom(dataDir),
                      "data_dir": dataDir,
                      "plan_structures_csv": self.planInfo(),
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
                QMessageBox.warning(self, "Analysis folder", "Choose an analysis folder first.")
            return not required
        if not self.fromPredictors() and self.dataDir() is None:
            if required:
                QMessageBox.warning(self, "Data", "Select input Data folder.")
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
        task = self.runningTask()
        if task is not None:
            QMessageBox.information(self, "Run in progress", f"{task[0]} is in progress. "
                                    f"Settings can't be saved until it finishes or is stopped.")
            return False

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
        task = self.runningTask()
        if task is not None:
            event.ignore()
            if not self._closePending and self._askAbortAndClose(*task):
                self._closePending = True
                task[1].finished.connect(self.close)    # close once it stops
            return
        # Only an analysis whose settings were saved before is asked about; otherwise just close
        analysisDir = self.analysisDir()
        started = analysisDir is not None and os.path.exists(os.path.join(analysisDir, analysis.FILE_NAME))
        if not started or self.ensureSaved(closing=True):
            event.accept()
        else:
            event.ignore()

    def _askAbortAndClose(self, label, thread, tab):
        """Ask to abort the run or install in progress (its processes are killed;
        the patient being run is recorded as aborted) and close once it stops.
        Returns True to close."""
        box = QMessageBox(self)
        box.setWindowTitle("Run in progress")
        box.setText(f"{label} is in progress.\n\nAbort it and close? It stops immediately"
                    + ("; Install again later to finish it." if tab is self.segmentTab and thread is
                       self.segmentTab.installWorker else "; the current patient is recorded as aborted."))
        abortBtn = box.addButton("Abort and close", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        box.exec_()
        if box.clickedButton() is not abortBtn:
            return False
        tab.stageLabel.setText("Aborting...")
        thread.abort()
        return True


def _hasResults(taskLog, tab):
    section = logs.TAB_SECTIONS[tab]
    return any(section in entry for entry in ((taskLog or {}).get("patients") or {}).values())

