"""Model tab: derive the structures the dosimetric model needs (or use existing ones),
then compute NTCP for every patient, and export the per-patient predictions to CSV.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QMessageBox, QRadioButton, QButtonGroup, QGroupBox,
    QHeaderView, QAbstractItemView, QToolButton
)

from validate.gui.progress_and_logging import ManageRun, LABEL_WIDTH
from validate.gui.worker import ModelWorker
from validate.gui import theme
from validate.seg import structures
from validate.seg.structures import getRequiredStructures
from validate import logs

# (settings key, label, help, details shown by the "i" button)
CSV_FIELDS = [
    ("plan_structures_csv", "Plan info:",
     "Optional. Plan names, fractionation, existing structures (per case).",
     "One row per patient. Only ID is required.\n\n"
     "ID: patient folder name.\n"
     "Plan name: RTDOSE file name, if a patient has more than one dose (DICOM).\n"
     "Prescribed dose (Gy), Fraction size (Gy), Fraction number: any two, if the model "
     "needs fractionation correction.\n"
     "Scan file, Dose file: file name or pattern (NIfTI/NRRD).\n"
     "<structure>: one column per structure the model needs, giving its name in the "
     "RTSTRUCT (DICOM), or its mask file or \"file:label\" (NIfTI/NRRD)."),
    ("predictors_csv", "Predictor values:",
     "Optional input. Pass patient-specific clinical factors (age, gender etc.) or pre-computed predictors.",
     "One row per patient. Only ID is required.\n\n"
     "ID: patient ID.\n"
     "<structure> <metric>: one column per dose metric, named as in the model "
     "(e.g. \"Esophagus meanDose\"), already fractionation-corrected if the model needs it.\n"
     "<predictor>: one column per clinical predictor in the model (e.g. concurrentChemo), "
     "as the numeric codes in the model file.\n\n"
     "With Data set, only the clinical predictors are read; dose metrics are computed from the images."),
]


class ModelTab(ManageRun):
    """Derive or select each structure the model needs, then compute NTCP."""
    TAB = "model"
    RESULTS_LABEL = "NTCP results"

    def __init__(self, host, parent=None):
        super().__init__(host, parent)
        self.resultsDf = None
        self._structRows = []
        self._buildUi()

    def _buildUi(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        inputsGroup = QGroupBox("Inputs")
        inputsLayout = QVBoxLayout(inputsGroup)
        inputsLayout.setSpacing(10)

        structHeading = QLabel("Structures")
        structHeading.setFont(theme.headingFont(structHeading))
        inputsLayout.addWidget(structHeading)
        self.structTable = QTableWidget(0, 2)
        self.structTable.setHorizontalHeaderLabels(["Expected", "Source"])
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
        inputsLayout.addWidget(self.structTable)

        self.csvEdits = {}
        for key, label, helpText, details in CSV_FIELDS:
            row = QHBoxLayout()
            rowLabel = QLabel(label)
            rowLabel.setMinimumWidth(LABEL_WIDTH)
            edit = QLineEdit()
            edit.setPlaceholderText(helpText)
            edit.setToolTip(helpText)
            selectBtn = QPushButton("Select CSV")
            selectBtn.clicked.connect(lambda _, e=edit: self._browseCsv(e))
            infoBtn = QToolButton()
            infoBtn.setText("i")
            infoBtn.setToolTip(details)
            row.addWidget(rowLabel)
            row.addWidget(edit)
            row.addWidget(selectBtn)
            row.addWidget(infoBtn)
            inputsLayout.addLayout(row)
            self.csvEdits[key] = edit
        layout.addWidget(inputsGroup)

        self.exportBtn = QPushButton("Export CSV...")
        self.exportBtn.clicked.connect(self._exportCsv)
        self.exportBtn.setEnabled(False)
        layout.addWidget(self._buildRunGroup([self.exportBtn]))
        layout.addStretch()

    # Settings

    def setModel(self, modelFile, structureSettings=None):
        """One row per structure the model needs: "Use existing: [name]" or "Derive"
        (only where a recipe is registered). structureSettings: the settings'
        structures section; without an entry, Derive is chosen."""
        try:
            requiredStructs = getRequiredStructures(modelFile) if modelFile else []
        except Exception:
            requiredStructs = []
        structureSettings = structureSettings or {}

        self.structTable.setRowCount(len(requiredStructs))
        self._structRows = []
        for row, structName in enumerate(requiredStructs):
            nameItem = QTableWidgetItem(structName)
            nameItem.setFlags(nameItem.flags() & ~Qt.ItemIsEditable)
            self.structTable.setItem(row, 0, nameItem)

            sourceWidget = QWidget()
            sourceLayout = QHBoxLayout(sourceWidget)
            sourceLayout.setContentsMargins(4, 0, 4, 0)
            existingRadio = QRadioButton("Use existing:")
            nameEdit = QLineEdit(structName)
            nameEdit.setToolTip("Enter name")
            deriveRadio = QRadioButton("Derive")
            derivation = structures.getDerivation(structName)
            deriveRadio.setEnabled(derivation is not None)

            group = QButtonGroup(sourceWidget)
            group.addButton(existingRadio)
            group.addButton(deriveRadio)
            existingRadio.toggled.connect(nameEdit.setEnabled)
            entry = structureSettings.get(structName)
            if entry is not None:
                derive = entry.get("source") == "derive" and derivation is not None
                if entry.get("name"):
                    nameEdit.setText(entry["name"])
            else:
                derive = derivation is not None
            (deriveRadio if derive else existingRadio).setChecked(True)
            nameEdit.setEnabled(not derive)

            sourceLayout.addWidget(existingRadio)
            sourceLayout.addWidget(nameEdit)
            sourceLayout.addWidget(deriveRadio)
            self.structTable.setCellWidget(row, 1, sourceWidget)
            # Keep the QButtonGroup alive (setCellWidget's parenting isn't
            # enough on its own) and the widgets reachable for settingsPart.
            self._structRows.append({"structName": structName, "group": group,
                                     "deriveRadio": deriveRadio, "nameEdit": nameEdit})

    def loadSettings(self, settings):
        inputs = settings.get("input") or {}
        for key, edit in self.csvEdits.items():
            edit.setText(inputs.get(key) or "")

    def settingsPart(self):
        """This tab's part of analysis.yaml: the CSV inputs and structures."""
        structureSettings = {}
        for entry in self._structRows:
            if entry["deriveRadio"].isChecked():
                structureSettings[entry["structName"]] = {"source": "derive"}
            else:
                name = entry["nameEdit"].text().strip() or entry["structName"]
                structureSettings[entry["structName"]] = {"source": "existing", "name": name}
        return {"input": {key: edit.text().strip() or None for key, edit in self.csvEdits.items()},
                "structures": structureSettings}

    def _browseCsv(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "Select CSV", "", "CSV files (*.csv)")
        if path:
            edit.setText(path)

    # Run

    def _makeWorker(self, analysisDir):
        if not self._confirmSegmented(analysisDir):
            return None
        self.exportBtn.setEnabled(False)
        return ModelWorker(analysisDir)

    def _confirmSegmented(self, analysisDir):
        """If structures to derive need AI outputs that some patients don't have,
        direct the user to Segment first. Returns False to cancel the run."""
        aiModels = sorted({structures.getDerivation(entry["structName"]).aiModelName
                           for entry in self._structRows if entry["deriveRadio"].isChecked()} - {None})
        patients = self.host.patients()
        if not aiModels or not patients:
            return True
        taskLog = self.host.taskLog()
        ready = [patientId for patientId in patients
                 if all(logs.isSegmented(analysisDir, taskLog, patientId, name) for name in aiModels)]
        if len(ready) == len(patients):
            return True

        derived = [entry["structName"] for entry in self._structRows if entry["deriveRadio"].isChecked()
                   and structures.getDerivation(entry["structName"]).aiModelName in aiModels]
        box = QMessageBox(self)
        box.setWindowTitle("Run Segment first")
        if not ready:
            box.setText(f"{' and '.join(derived)} {'is' if len(derived) == 1 else 'are'} derived from "
                        f"{', '.join(aiModels)}, which hasn't been run yet (0 of {len(patients)} patients).\n\n"
                        f"Run Segment first, or choose \"Use existing\" for these structures.")
        else:
            box.setText(f"{', '.join(aiModels)} outputs are missing for {len(patients) - len(ready)} of "
                        f"{len(patients)} patients.\nThose patients will fail with \"run Segment first\".")
        goBtn = box.addButton("Go to Segment", QMessageBox.AcceptRole)
        runBtn = box.addButton(f"Run anyway ({len(ready)} patients ready)", QMessageBox.AcceptRole) if ready else None
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is goBtn:
            self.host.goToTab("segment")
        return runBtn is not None and clicked is runBtn

    def _onFinished(self, resultsDf, errorLogPath):
        self.resultsDf = resultsDf
        self.exportBtn.setEnabled(True)
        super()._onFinished(resultsDf, errorLogPath)

    def _exportCsv(self):
        if self.resultsDf is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export results", "ntcp_results.csv", "CSV files (*.csv)")
        if path:
            self.resultsDf.to_csv(path, index=False)
