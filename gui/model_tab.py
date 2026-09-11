"""Apply dosimetric model to a patient cohort and export the resulting NTCP/TCP values.
Supported models are in cerr.roe.
Inputs: DICOM directories (1 per patient).
        [Optional] CSV file listing "ID" "Plan name" "Prescribed dose" "Fraction size" "Fraction number".
"""

import os

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QProgressBar, QTableWidget, QTableWidgetItem,
    QMessageBox, QRadioButton, QButtonGroup, QGroupBox, QHeaderView,
    QDialog, QDialogButtonBox, QToolButton, QAbstractItemView
)

from cerr.roe import dosimetric_models as doseModels

from validate.gui.worker import RunPipelineWorker
from validate.gui import theme
from validate.src.structures import getRequiredStructures
from validate.src import model_registry, logging as autoseg_log, autoseg_pipeline
from validate.src.data_import import discoverPatients, getFractionCorrectionType

LABEL_WIDTH = 150


class ModelTab(QWidget):
    """Point at a cohort directory, pick a dosimetric model, run it over
    every patient, and export the per-patient predictions to CSV.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resultsDf = None
        self.worker = None
        self._configChecked = True
        self._installBaseDir = model_registry.getDefaultInstallDir()
        self._taskLogPath = None
        self._buildUi()

    def _buildUi(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        cohortGroup = QGroupBox("Model")
        cohortLayout = QVBoxLayout(cohortGroup)
        cohortLayout.setSpacing(10)

        dirRow = QHBoxLayout()
        dirLabel = QLabel("Data Dir:")
        dirLabel.setFont(theme.headingFont(dirLabel))
        dirLabel.setMinimumWidth(LABEL_WIDTH)
        self.cohortDirEdit = QLineEdit()
        self.cohortDirEdit.setPlaceholderText(
            "Cohort directory (one DICOM subdirectory per patient)")
        browseBtn = QPushButton("Browse...")
        browseBtn.clicked.connect(self._browseCohortDir)
        dirRow.addWidget(dirLabel)
        dirRow.addWidget(self.cohortDirEdit)
        dirRow.addWidget(browseBtn)
        cohortLayout.addLayout(dirRow)

        modelRow = QHBoxLayout()
        modelLabel = QLabel("Model:")
        modelLabel.setFont(theme.headingFont(modelLabel))
        modelLabel.setMinimumWidth(LABEL_WIDTH)
        self.modelCombo = QComboBox()
        self.modelCombo.addItems(doseModels.listModels())
        defaultIdx = self.modelCombo.findText("Xerostomia (grade 2+)")
        if defaultIdx >= 0:
            self.modelCombo.setCurrentIndex(defaultIdx)
        self.modelCombo.currentTextChanged.connect(self._onModelChanged)
        viewRequirementsBtn = QPushButton("View Requirements")
        viewRequirementsBtn.clicked.connect(self._viewRequirements)
        modelRow.addWidget(modelLabel)
        modelRow.addWidget(self.modelCombo)
        modelRow.addWidget(viewRequirementsBtn)
        modelRow.addStretch()
        cohortLayout.addLayout(modelRow)

        infoCsvRow = QHBoxLayout()
        infoCsvLabel = QLabel("Plan (optional):")
        infoCsvLabel.setMinimumWidth(LABEL_WIDTH)
        self.infoCsvEdit = QLineEdit()
        self.infoCsvEdit.setPlaceholderText(
            "ID | Plan name | "
            "Prescribed dose | Fraction size | Fraction number "
            "(if the model needs fractionation correction)")
        infoCsvBrowseBtn = QPushButton("Select CSV")
        infoCsvBrowseBtn.clicked.connect(self._browsePatientInfoCsv)
        infoBtn = QToolButton()
        infoBtn.setText("i")
        infoBtn.setToolTip(
            "By default, the first available plan is used. If multiple "
            "plans are available, input a CSV listing 'ID | Plan name'. "
            "Select View Requirements for other model-specific inputs.")
        infoCsvRow.addWidget(infoCsvLabel)
        infoCsvRow.addWidget(self.infoCsvEdit)
        infoCsvRow.addWidget(infoCsvBrowseBtn)
        infoCsvRow.addWidget(infoBtn)
        cohortLayout.addLayout(infoCsvRow)

        structHeading = QLabel("Select structures")
        structHeading.setFont(theme.headingFont(structHeading))
        cohortLayout.addWidget(structHeading)

        self.structTable = QTableWidget(0, 2)
        self.structTable.setHorizontalHeaderLabels(
            ["Expected", "Available"])
        structHeader = self.structTable.horizontalHeader()
        structHeader.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        structHeader.setMinimumSectionSize(160)
        structHeader.setStretchLastSection(True)
        structHeader.setMinimumHeight(32)
        self.structTable.verticalHeader().setDefaultSectionSize(38)
        self.structTable.verticalHeader().setVisible(False)
        self.structTable.setAlternatingRowColors(True)
        self.structTable.setMaximumHeight(220)
        # Rows hold interactive widgets (radio buttons, a text field) --
        # cell/row selection highlight is just visual noise here.
        self.structTable.setSelectionMode(QAbstractItemView.NoSelection)
        cohortLayout.addWidget(self.structTable)

        layout.addWidget(cohortGroup)

        runGroup = QGroupBox("Run")
        runLayout = QVBoxLayout(runGroup)
        runLayout.setSpacing(10)

        runBtnRow = QHBoxLayout()
        self.checkBtn = QPushButton("Check Config")
        self.checkBtn.clicked.connect(self._checkConfig)
        self.runBtn = QPushButton("Run")
        theme.markPrimary(self.runBtn)
        self.runBtn.clicked.connect(self._runModel)
        self.viewLogBtn = QPushButton("View Task Log")
        self.viewLogBtn.clicked.connect(self._viewTaskLog)
        self.viewLogBtn.setEnabled(False)
        runBtnRow.addWidget(self.checkBtn)
        runBtnRow.addWidget(self.runBtn)
        runBtnRow.addWidget(self.viewLogBtn)
        runBtnRow.addStretch()
        runLayout.addLayout(runBtnRow)

        self.stageLabel = QLabel("")
        runLayout.addWidget(self.stageLabel)

        self.progressBar = QProgressBar()
        runLayout.addWidget(self.progressBar)

        layout.addWidget(runGroup)

        resultsGroup = QGroupBox("Results")
        resultsLayout = QVBoxLayout(resultsGroup)
        resultsLayout.setSpacing(10)

        self.resultsTable = QTableWidget(0, 4)
        self.resultsTable.setHorizontalHeaderLabels(
            ["Patient", "NTCP", "Status", "Message"])
        resultsHeader = self.resultsTable.horizontalHeader()
        for col in (0, 1, 2):
            resultsHeader.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        resultsHeader.setStretchLastSection(True)
        resultsHeader.setMinimumHeight(32)
        self.resultsTable.verticalHeader().setDefaultSectionSize(30)
        self.resultsTable.verticalHeader().setVisible(False)
        self.resultsTable.setAlternatingRowColors(True)
        resultsLayout.addWidget(self.resultsTable)

        exportRow = QHBoxLayout()
        exportRow.addStretch()
        self.exportBtn = QPushButton("Export CSV...")
        self.exportBtn.clicked.connect(self._exportCsv)
        self.exportBtn.setEnabled(False)
        exportRow.addWidget(self.exportBtn)
        resultsLayout.addLayout(exportRow)

        layout.addWidget(resultsGroup, stretch=1)

        self._onModelChanged(self.modelCombo.currentText())

    def _onModelChanged(self, modelName):
        try:
            requiredStructs = getRequiredStructures(modelName) if modelName else []
        except Exception:
            requiredStructs = []

        self.structTable.setRowCount(len(requiredStructs))
        self._structRows = []
        for row, structName in enumerate(requiredStructs):
            nameItem = QTableWidgetItem(structName)
            nameItem.setFlags(nameItem.flags() & ~Qt.ItemIsEditable)
            self.structTable.setItem(row, 0, nameItem)

            sourceWidget = QWidget()
            sourceLayout = QHBoxLayout(sourceWidget)
            sourceLayout.setContentsMargins(4, 0, 4, 0)

            autoRadio = QRadioButton("Auto-segment")
            nameRadio = QRadioButton("Use existing:")
            nameEdit = QLineEdit(structName)
            nameEdit.setToolTip("Enter name")

            group = QButtonGroup(sourceWidget)
            group.addButton(autoRadio)
            group.addButton(nameRadio)
            nameRadio.setChecked(True)
            nameRadio.toggled.connect(nameEdit.setEnabled)
            autoRadio.toggled.connect(self._refreshRunGate)

            sourceLayout.addWidget(autoRadio)
            sourceLayout.addWidget(nameRadio)
            sourceLayout.addWidget(nameEdit)
            self.structTable.setCellWidget(row, 1, sourceWidget)

            # Keep the QButtonGroup alive (setCellWidget's parenting isn't
            # enough on its own) and the widgets reachable for _runModel.
            self._structRows.append({"structName": structName, "group": group,
                                     "autoRadio": autoRadio, "nameEdit": nameEdit})

        self._refreshRunGate()

    def _viewRequirements(self):
        """Show what validate needs to run the selected model, computed
        live from the model's own parameter JSON (see structures.py /
        fractionation.py) rather than a separately maintained file.
        """
        modelName = self.modelCombo.currentText()
        if not modelName:
            return

        try:
            requiredStructs = getRequiredStructures(modelName)
        except Exception as exc:
            QMessageBox.critical(self, "Requirements", f"Could not read model: {exc}")
            return

        try:
            correctionType = getFractionCorrectionType(modelName)
        except Exception as exc:
            correctionType = None
            correctionNote = f"Could not determine ({exc})"
        else:
            if correctionType is None:
                correctionNote = "Not required for this model."
            else:
                field = "Fraction size" if correctionType == "frxSize" else "Fraction number"
                correctionNote = f"Required — provide '{field}' via the Plan CSV."

        structList = "\n".join(f"  - {s}" for s in requiredStructs) or "  (none)"
        message = (
            f"Requirements for {modelName!r}:\n\n"
            f"Structures:\n{structList}\n\n"
            f"Plan selection: if this cohort has patients with more than "
            f"one dose, provide 'ID | Plan name' via the Plan CSV.\n\n"
            f"Fractionation correction: {correctionNote}")
        QMessageBox.information(self, "Model requirements", message)

    def _getStructSelections(self):
        """Return (structNameMap, autoSegmentStructs) from the structures
        table: structNameMap covers rows set to "Use existing", autoSegmentStructs
        lists the model structure names set to "Auto-segment".
        """
        structNameMap = {}
        autoSegmentStructs = []
        for entry in self._structRows:
            if entry["autoRadio"].isChecked():
                autoSegmentStructs.append(entry["structName"])
            else:
                datasetName = entry["nameEdit"].text().strip()
                structNameMap[entry["structName"]] = datasetName or entry["structName"]
        return structNameMap, autoSegmentStructs

    def _refreshRunGate(self):
        """Lock Run whenever any structure is set to Auto-segment, until
        Check Config succeeds for the current selection; unlock immediately
        if nothing needs auto-segmentation.
        """
        _, autoSegmentStructs = self._getStructSelections()
        self._configChecked = not autoSegmentStructs
        self.runBtn.setEnabled(self._configChecked)
        self.viewLogBtn.setEnabled(False)
        self._taskLogPath = None
        self.stageLabel.setText("")

    def _browseCohortDir(self):
        path = QFileDialog.getExistingDirectory(self, "Select cohort directory")
        if path:
            self.cohortDirEdit.setText(path)

    def _browsePatientInfoCsv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select patient info CSV", "", "CSV files (*.csv)")
        if path:
            self.infoCsvEdit.setText(path)

    def _checkConfig(self):
        _, autoSegmentStructs = self._getStructSelections()
        if not autoSegmentStructs:
            self._configChecked = True
            self.runBtn.setEnabled(True)
            return

        models, missingRecipe = autoseg_pipeline.checkModelsForStructures(autoSegmentStructs)
        if missingRecipe:
            QMessageBox.warning(
                self, "No auto-segmentation recipe",
                "No auto-segmentation recipe is registered yet for:\n\n"
                + "\n".join(missingRecipe) +
                "\n\nSelect 'Use existing' and enter the dataset's structure name "
                "for these instead, or add a recipe in "
                "validate/src/derivations.py.")
            return

        if all(info["installed"] for info in models.values()):
            self._configChecked = True
            self.runBtn.setEnabled(True)
            return

        if not self._showModelStatusDialog(models):
            return  # user cancelled

        installBaseDir = self._ensureInstallBaseDir()
        if not installBaseDir:
            return

        missingNums = [num for num, info in models.items() if not info["installed"]]
        results = autoseg_pipeline.installMissingModels(missingNums, installBaseDir)
        failed = [(num, msg) for num, ok, msg in results if not ok]
        if failed:
            QMessageBox.critical(
                self, "Install failed",
                "\n".join(f"Model {num}: {msg}" for num, msg in failed))
            return

        self._configChecked = True
        self.runBtn.setEnabled(True)
        QMessageBox.information(self, "Ready",
                                "All required AI models are installed. Run is now enabled.")

    def _showModelStatusDialog(self, models):
        """Popup listing each needed AI model + install status.
        Returns True if the user chose Proceed, False for Cancel.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("AI models required for auto-segmentation")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("The following AI models are needed:"))
        for modelNum, info in sorted(models.items()):
            statusText = "Installed" if info["installed"] else "Missing"
            color = "#3ecf8e" if info["installed"] else "#e07a5f"
            row = QLabel(f"●  {info['name']} (model {modelNum}) — "
                        f"<span style='color:{color};'>{statusText}</span>")
            layout.addWidget(row)

        buttons = QDialogButtonBox()
        proceedBtn = buttons.addButton("Proceed", QDialogButtonBox.AcceptRole)
        buttons.addButton("Cancel", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if all(info["installed"] for info in models.values()):
            proceedBtn.setText("OK")

        return dialog.exec_() == QDialog.Accepted

    def _ensureInstallBaseDir(self):
        if self._installBaseDir and os.path.isdir(self._installBaseDir):
            return self._installBaseDir
        path = QFileDialog.getExistingDirectory(
            self, "Select directory to install AI models into")
        if path:
            self._installBaseDir = path
        return path or None

    def _checkExistingAvailability(self, cohortDir, autoSegmentStructs):
        """Ask Continue/Re-run-and-overwrite if any patient already has a
        logged auto-segmentation result for these structures.

        Returns:
            bool overwrite flag, or None if the user cancelled the run.
        """
        if not autoSegmentStructs:
            return False

        patients = discoverPatients(cohortDir)
        anyAvailable = False
        for structName in autoSegmentStructs:
            derivation = autoseg_pipeline.derivations.getDerivation(structName)
            if derivation is None:
                continue
            for patientId, _ in patients:
                if autoseg_log.isAvailable(cohortDir, derivation.aiModelName,
                                           patientId, structName):
                    anyAvailable = True
                    break
            if anyAvailable:
                break

        if not anyAvailable:
            return False

        box = QMessageBox(self)
        box.setWindowTitle("Existing auto-segmentation found")
        box.setText("Some structures already have auto-segmentation results "
                    "logged for this cohort.")
        continueBtn = box.addButton("Continue (use existing)", QMessageBox.AcceptRole)
        rerunBtn = box.addButton("Re-run and overwrite", QMessageBox.DestructiveRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        clicked = box.clickedButton()
        if clicked not in (continueBtn, rerunBtn):
            return None
        return clicked is rerunBtn

    def _runModel(self):
        if not self._configChecked:
            return

        cohortDir = self.cohortDirEdit.text().strip()
        if not cohortDir or not os.path.isdir(cohortDir):
            QMessageBox.warning(self, "Invalid directory",
                                "Please select a valid cohort directory.")
            return

        modelName = self.modelCombo.currentText()
        if not modelName:
            return

        structNameMap, autoSegmentStructs = self._getStructSelections()

        overwrite = self._checkExistingAvailability(cohortDir, autoSegmentStructs)
        if overwrite is None:
            return  # user cancelled

        patientInfoCsv = self.infoCsvEdit.text().strip() or None

        self.checkBtn.setEnabled(False)
        self.runBtn.setEnabled(False)
        self.exportBtn.setEnabled(False)
        self.viewLogBtn.setEnabled(False)
        self.resultsTable.setRowCount(0)
        self.progressBar.setValue(0)
        self.stageLabel.setText("Starting...")

        self.worker = RunPipelineWorker(
            cohortDir, modelName, structNameMap, autoSegmentStructs,
            installBaseDir=self._installBaseDir, overwrite=overwrite,
            patientInfoCsv=patientInfoCsv)
        self.worker.stage.connect(self.stageLabel.setText)
        self.worker.progress.connect(self._onProgress)
        self.worker.finishedOk.connect(self._onFinished)
        self.worker.failed.connect(self._onFailed)
        self.worker.start()

    def _onProgress(self, done, total, patientId):
        self.progressBar.setMaximum(total)
        self.progressBar.setValue(done)
        self.progressBar.setFormat(f"{done}/{total}  {patientId}")

    def _onFinished(self, resultsDf, taskLogPath):
        self.resultsDf = resultsDf
        self._taskLogPath = taskLogPath
        self.resultsTable.setRowCount(len(resultsDf))
        for row, record in enumerate(resultsDf.itertuples(index=False)):
            self.resultsTable.setItem(row, 0, QTableWidgetItem(str(record.patient_id)))
            ntcpText = "" if record.ntcp is None else f"{record.ntcp:.4f}"
            self.resultsTable.setItem(row, 1, QTableWidgetItem(ntcpText))
            self.resultsTable.setItem(row, 2, QTableWidgetItem(record.status))
            self.resultsTable.setItem(row, 3, QTableWidgetItem(record.message))
        self.checkBtn.setEnabled(True)
        self.runBtn.setEnabled(self._configChecked)
        self.exportBtn.setEnabled(True)
        self.viewLogBtn.setEnabled(True)
        self.stageLabel.setText("Done.")

    def _onFailed(self, message, taskLogPath):
        self._taskLogPath = taskLogPath
        QMessageBox.critical(self, "Run failed", message)
        self.checkBtn.setEnabled(True)
        self.runBtn.setEnabled(self._configChecked)
        self.viewLogBtn.setEnabled(bool(taskLogPath))
        self.stageLabel.setText("Failed.")

    def _viewTaskLog(self):
        if self._taskLogPath:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._taskLogPath))

    def _exportCsv(self):
        if self.resultsDf is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export results", "ntcp_results.csv", "CSV files (*.csv)")
        if path:
            self.resultsDf.to_csv(path, index=False)
