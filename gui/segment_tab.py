"""Segment tab: run the AI models the dosimetric model's structures are derived from
(installing them first if needed). Structures are derived later, in the Model tab.
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QGroupBox, QCheckBox, QRadioButton, QButtonGroup, QWidget, QProgressBar
)

from cerr.ai_models import model_list

from validate.gui.progress_and_logging import ManageRun, LABEL_WIDTH, buttonRow
from validate.gui.worker import InstallWorker, SegmentWorker
from validate.seg import model_registry
from validate.seg.structures import listReqdAISegModels
from validate import logs

STATUS_TEXT = {"installed": ("Installed", "#3ecf8e"),
               "no weights": ("Weights not installed", "#e0b35f"),
               "not installed": ("Not installed", "#e07a5f")}


class SegmentTab(ManageRun):
    """Run the AI models needed by the dosimetric model on every patient in the cohort."""
    TAB = "segment"
    RESULTS_LABEL = "Segment results"

    def __init__(self, host, parent=None):
        super().__init__(host, parent)
        self.installWorker = None
        self._modelRows = {}   # AI model name -> {"check": QCheckBox, "status": QLabel, "num": int}
        self._buildUi()

    def _buildUi(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        self.modelsGroup = QGroupBox("AI models")
        modelsLayout = QVBoxLayout(self.modelsGroup)
        modelsLayout.setSpacing(10)
        self.modelsHeading = QLabel("")
        modelsLayout.addWidget(self.modelsHeading)
        self.modelRowsLayout = QVBoxLayout()
        modelsLayout.addLayout(self.modelRowsLayout)

        self.useExistingRadio = QRadioButton("Use existing install:")
        self.installRadio = QRadioButton("Install to:")
        installGroup = QButtonGroup(self)
        installGroup.addButton(self.useExistingRadio)
        installGroup.addButton(self.installRadio)
        self.useExistingRadio.setChecked(True)
        defaultDir = model_registry.getDefaultInstallDir() or ""
        self.existingDirEdit = QLineEdit(defaultDir)
        self.installDirEdit = QLineEdit(defaultDir)
        for radio, edit in ((self.useExistingRadio, self.existingDirEdit), (self.installRadio, self.installDirEdit)):
            row = QHBoxLayout()
            radio.setMinimumWidth(LABEL_WIDTH)
            browseBtn = QPushButton("Browse...")
            browseBtn.clicked.connect(lambda _, e=edit: self._browseDir(e))
            row.addWidget(radio)
            row.addWidget(edit)
            row.addWidget(browseBtn)
            if radio is self.installRadio:
                self.installBtn = QPushButton("Install")
                self.installBtn.clicked.connect(self._install)
                row.addWidget(self.installBtn)
            modelsLayout.addLayout(row)
            edit.editingFinished.connect(self._refreshStatus)
        self.useExistingRadio.toggled.connect(self._refreshStatus)

        # Shown while installing; pyCERR's installer doesn't report how far along it is
        self.installProgress = QProgressBar()
        self.installProgress.setRange(0, 0)
        self.installProgress.setFormat("Installing...")
        self.installProgress.setVisible(False)
        modelsLayout.addWidget(self.installProgress)

        deviceRow = QHBoxLayout()
        deviceLabel = QLabel("Device:")
        deviceLabel.setMinimumWidth(LABEL_WIDTH)
        self.gpuRadio = QRadioButton("GPU")
        self.cpuRadio = QRadioButton("CPU")
        deviceGroup = QButtonGroup(self)
        deviceGroup.addButton(self.gpuRadio)
        deviceGroup.addButton(self.cpuRadio)
        self.gpuRadio.setChecked(True)
        deviceRow.addWidget(deviceLabel)
        deviceRow.addWidget(self.gpuRadio)
        deviceRow.addWidget(self.cpuRadio)
        deviceRow.addStretch()
        layout.addWidget(self.modelsGroup)

        runGroup = QGroupBox("Run")
        runLayout = QVBoxLayout(runGroup)
        runLayout.setSpacing(10)
        runLayout.addLayout(deviceRow)
        runLayout.addLayout(buttonRow(self._buildRunButtons()))
        self._addProgress(runLayout)
        layout.addWidget(runGroup)

        reviewGroup = QGroupBox("Review")
        viewOutputsBtn = QPushButton("View outputs")
        viewOutputsBtn.clicked.connect(self._openOutputFolder)
        QVBoxLayout(reviewGroup).addLayout(buttonRow(self._buildLogButtons() + [viewOutputsBtn]))
        layout.addWidget(reviewGroup)

        nextGroup = QGroupBox("Finish")
        summaryBtn = QPushButton("Generate summary")
        summaryBtn.setToolTip("Write segment_summary.csv: one row per patient, AI model, output file and label.")
        summaryBtn.clicked.connect(self._generateSummary)
        nextBtn = QPushButton("Next")
        nextBtn.setToolTip("Go to the Model tab.")
        nextBtn.clicked.connect(lambda: self.host.goToTab("model"))
        nextRow = buttonRow([summaryBtn])
        nextRow.addWidget(nextBtn)      # after the stretch, so Next sits on the right
        QVBoxLayout(nextGroup).addLayout(nextRow)
        layout.addWidget(nextGroup)
        layout.addStretch()

    # Settings

    def setModel(self, modelFile, aiModels=None):
        """List the AI models the dosimetric model's structures are derived from,
        plus any others in the settings. aiModels: the ticked ones (all if None)."""
        for row in self._modelRows.values():
            row["widget"].deleteLater()
        self._modelRows = {}
        try:
            names = listReqdAISegModels(modelFile) if modelFile else []
        except Exception:
            names = []
        names += [name for name in (aiModels or []) if name not in names]

        modelName = self.host.modelName()
        if names:
            self.modelsHeading.setText(f"AI models for {modelName}:")
        else:
            self.modelsHeading.setText(f"{modelName} needs no AI models. Go to the Model tab.")
        for name in names:
            widget = QWidget()
            rowLayout = QHBoxLayout(widget)
            rowLayout.setContentsMargins(0, 0, 0, 0)
            check = QCheckBox(name)
            check.setChecked(aiModels is None or name in aiModels)
            check.toggled.connect(self._refreshStatus)
            status = QLabel("")
            rowLayout.addWidget(check)
            rowLayout.addWidget(status)
            rowLayout.addStretch()
            self.modelRowsLayout.addWidget(widget)
            try:
                num = model_list.resolveModel(name)[0]
            except ValueError:
                num = None
            self._modelRows[name] = {"widget": widget, "check": check, "status": status, "num": num}
        self._refreshStatus()

    def resetSettings(self):
        """Back to the defaults for a new analysis; the install folder is kept."""
        self.gpuRadio.setChecked(True)

    def loadSettings(self, settings):
        compute = settings.get("compute") or {}
        (self.gpuRadio if compute.get("device") == "gpu" else self.cpuRadio).setChecked(True)
        installDir = (settings.get("segment") or {}).get("install_dir")
        if installDir:
            self.existingDirEdit.setText(installDir)
            self.useExistingRadio.setChecked(True)

    def settingsPart(self):
        """This tab's part of analysis.yaml: compute.device and segment."""
        tickedModels = self._tickedModels()
        installDir = self._selectedInstallDir()
        return {"compute": {"device": "gpu" if self.gpuRadio.isChecked() else "cpu"},
                "segment": {"ai_models": tickedModels,
                            "install_dir": installDir or None}}

    def _tickedModels(self):
        return [name for name, row in self._modelRows.items() if row["check"].isChecked()]

    def _selectedInstallDir(self):
        edit = self.existingDirEdit if self.useExistingRadio.isChecked() else self.installDirEdit
        return edit.text().strip()

    def _browseDir(self, edit):
        path = QFileDialog.getExistingDirectory(self, "Select AI model install folder", edit.text())
        if path:
            edit.setText(path)
            self._refreshStatus()

    # Install

    def _statuses(self, installDir):
        """{AI model name: install status in installDir}."""
        statuses = {}
        for name, row in self._modelRows.items():
            try:
                statuses[name] = model_registry.installStatus(row["num"], installDir) if row["num"] else "not installed"
            except ValueError:
                statuses[name] = "not installed"
        return statuses

    def _refreshStatus(self, *args):
        installDir = self._selectedInstallDir()
        for name, status in self._statuses(installDir).items():
            text, color = STATUS_TEXT[status]
            self._modelRows[name]["status"].setText(f"<span style='color:{color};'>●</span> {text}")
        ticked = self._tickedModels()
        self.installBtn.setEnabled(self.installRadio.isChecked() and bool(ticked))

    def _install(self):
        installDir = self.installDirEdit.text().strip()
        ticked = self._tickedModels()
        if not installDir or not ticked:
            QMessageBox.warning(self, "Install", "Choose the folder to install into and the AI models to install.")
            return
        statuses = self._statuses(installDir)
        names = [name for name in ticked if statuses[name] != "installed"]
        reinstall = not names
        if reinstall:
            answer = QMessageBox.question(
                self, "Install", f"Already installed in {installDir}:\n" + "\n".join(ticked) + "\n\nRe-install?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Yes:
                self.existingDirEdit.setText(installDir)
                self.useExistingRadio.setChecked(True)
                self._refreshStatus()
                return
            names = ticked
        nums = [self._modelRows[name]["num"] for name in names]
        self.installBtn.setEnabled(False)
        self.runBtn.setEnabled(False)
        self.progressBar.reset()        # clear the last run's progress
        self.stageLabel.setText("Starting install...")
        self.installProgress.setVisible(True)
        self.installWorker = InstallWorker(nums, installDir, force=reinstall)
        self.installWorker.stage.connect(self.stageLabel.setText)
        self.installWorker.finishedOk.connect(lambda results: self._onInstallFinished(results, installDir))
        self.installWorker.failed.connect(self._onInstallFailed)
        self.installWorker.start()

    def _onInstallFinished(self, results, installDir):
        self.installProgress.setVisible(False)
        self.runBtn.setEnabled(True)
        failed = [(num, msg) for num, ok, msg in results if not ok]
        if failed:
            self.stageLabel.setText("Install failed.")
            self._refreshStatus()
            QMessageBox.critical(self, "Install failed",
                                 "\n".join(f"Model {num}: {msg}" for num, msg in failed))
            return
        self.stageLabel.setText("Installed.")
        self.existingDirEdit.setText(installDir)
        self.useExistingRadio.setChecked(True)
        self._refreshStatus()

    def _onInstallFailed(self, message):
        self.installProgress.setVisible(False)
        self.runBtn.setEnabled(True)
        self.stageLabel.setText("Install failed.")
        self._refreshStatus()
        QMessageBox.critical(self, "Install failed", message)

    # Run

    def _makeWorker(self, analysisDir):
        ticked = self._tickedModels()
        if not ticked:
            QMessageBox.warning(self, "Segment", "No AI models to run.")
            return None
        installDir = self._selectedInstallDir()
        notInstalled = [name for name, status in self._statuses(installDir).items()
                        if name in ticked and status != "installed"]
        if notInstalled:
            QMessageBox.warning(self, "Segment", f"Not installed in {installDir or '(no folder)'}: "
                                                 f"{', '.join(notInstalled)}. Install them first.")
            return None
        overwrite = self._askOverwrite(analysisDir, ticked)
        if overwrite is None:
            return None
        return SegmentWorker(analysisDir, overwrite=overwrite)

    def _askOverwrite(self, analysisDir, aiModels):
        """If any patient already has outputs for aiModels, ask whether to keep
        them or run again. Returns the overwrite flag, or None if cancelled."""
        taskLog = self.host.taskLog()
        patients = self.host.patients()
        done = sum(1 for patientId in patients
                   if any(logs.isSegmented(analysisDir, taskLog, patientId, name) for name in aiModels))
        if not done:
            return False
        box = QMessageBox(self)
        box.setWindowTitle("Already segmented")
        box.setText(f"{done} of {len(patients)} patients already have outputs for "
                    f"{', '.join(aiModels)}.")
        continueBtn = box.addButton("Continue (use existing)", QMessageBox.AcceptRole)
        rerunBtn = box.addButton("Re-run and overwrite", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        clicked = box.clickedButton()
        if clicked not in (continueBtn, rerunBtn):
            return None
        return clicked is rerunBtn

    def _openOutputFolder(self):
        analysisDir = self.host.analysisDir()
        if not analysisDir:
            QMessageBox.information(self, "Output folder", "Choose an analysis folder first.")
            return
        self._openPath(analysisDir)

    def _generateSummary(self):
        analysisDir = self.host.analysisDir()
        try:
            path = logs.generateSummary(analysisDir) if analysisDir else None
        except (FileNotFoundError, ValueError) as exc:
            QMessageBox.information(self, "Generate summary", str(exc))
            return
        if path is None:
            QMessageBox.information(self, "Generate summary", "Choose an analysis folder first.")
            return
        self._openPath(path)
