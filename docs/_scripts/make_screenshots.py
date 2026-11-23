"""Regenerate the GUI screenshots used in the User Guide.

Run from the repository root, in Validate's environment:

    python docs/_scripts/make_screenshots.py

The real GUI is built off screen (nothing appears on the desktop) and saved to
docs/_static/images/. It uses a demo cohort of empty patient folders and the example
CSVs in docs/_static/examples/, created in a temporary folder. No patient data is
read, and no AI model or NTCP run is executed: the install status and the run
progress are set directly, so the images don't depend on what is installed here.
Paths are shown under ~/validate_tutorial.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt, QEvent, QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QWidget

DOCS = Path(__file__).resolve().parent.parent
IMAGES = DOCS / "_static" / "images"
EXAMPLES = DOCS / "_static" / "examples"
DISPLAY_ROOT = "~/validate_tutorial"
PATIENTS = [f"pt_{i:03d}" for i in range(1, 6)]
AI_MODEL = "CT_HN_SMIT"

ROOT = Path(tempfile.mkdtemp(prefix="validate_docs_"))
INSTALL_DIR = ROOT / "ai_models"
INSTALL_STATUS = {"value": "not installed"}   # what the Segment tab reports for every AI model
SEGMENTED = {"value": False}                  # whether every patient counts as segmented
DIALOGS = []                                  # [(image name or None, button text)] for the next dialogs


def setUpDemo():
    for cohort in ("hn_cohort", "lung_cohort"):
        for patientId in PATIENTS:
            (ROOT / cohort / patientId).mkdir(parents=True)
    INSTALL_DIR.mkdir()
    (ROOT / "csv").mkdir()
    for path in EXAMPLES.glob("*.csv"):
        shutil.copy(path, ROOT / "csv" / path.name)


def mask(text):
    return text.replace(str(ROOT), DISPLAY_ROOT)


def pump():
    """Process pending events, including deleteLater (which processEvents skips)."""
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()


def save(widget, name):
    """Save widget as <name>.png, with paths shown under DISPLAY_ROOT."""
    pump()
    edits = widget.findChildren(QLineEdit)
    original = [edit.text() for edit in edits]
    for edit in edits:
        edit.setText(mask(edit.text()))
        edit.setCursorPosition(0)
        edit.deselect()
    QApplication.processEvents()
    widget.grab().save(str(IMAGES / f"{name}.png"))
    for edit, text in zip(edits, original):
        edit.setText(text)


# Off-screen dialogs: each one is saved (if named) and answered with the queued button

def _answer(dialog):
    name, buttonText = DIALOGS.pop(0)
    if isinstance(dialog, QMessageBox):
        dialog.setText(mask(dialog.text()))
    dialog.setAttribute(Qt.WA_DontShowOnScreen)
    dialog.show()
    QApplication.processEvents()
    if name:
        save(dialog, name)
    buttons = [b for b in dialog.findChildren(QWidget) if hasattr(b, "text") and b.metaObject().className()
               == "QPushButton" and b.text().replace("&", "") == buttonText]
    if not buttons:
        raise RuntimeError(f"No {buttonText!r} button in dialog {name!r}")
    buttons[0].click()
    QApplication.processEvents()
    return dialog.result()


QMessageBox.exec_ = _answer
QDialog.exec_ = _answer


class FakeWorker(QObject):
    """Stands in for the run workers: same signals, but nothing runs."""
    stage = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)
    finishedOk = pyqtSignal(object, str)
    failed = pyqtSignal(str, str)

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._stopRequested = False
        self.aborted = False
        self.running = False

    def start(self):
        self.running = True

    def isRunning(self):
        return self.running

    def finish(self, results=None):
        self.running = False
        self.finishedOk.emit(results, str(ROOT / "error_log.txt"))


def patchValidate():
    from validate.gui import segment_tab, model_tab
    from validate.seg import model_registry
    model_registry.getDefaultInstallDir = lambda: str(INSTALL_DIR)
    segment_tab.model_registry.installStatus = lambda num, installDir: INSTALL_STATUS["value"]
    segment_tab.SegmentWorker = FakeWorker
    model_tab.ModelWorker = FakeWorker
    model_tab.logs.isSegmented = lambda *args: SEGMENTED["value"]     # same module as segment_tab.logs


def newWindow():
    from validate.gui.main_window import MainWindow
    window = MainWindow()
    window.setAttribute(Qt.WA_DontShowOnScreen)
    window.show()
    QApplication.processEvents()
    return window


def header(window):
    return window.centralWidget().layout().itemAt(0).widget()


def setField(edit, value):
    edit.setText(str(value))
    edit.editingFinished.emit()
    QApplication.processEvents()


def runAndFinish(window, tab, name, stage, results=None, saveSettings=True):
    """Press Run (saving the settings first, if they changed), save the in-progress
    and finished states."""
    if saveSettings:
        DIALOGS.append((f"{name}_save", "Save and continue"))
    tab.runBtn.click()
    QApplication.processEvents()
    worker = tab.worker
    worker.progress.emit(0, len(PATIENTS), "")
    worker.stage.emit(stage)
    worker.progress.emit(2, len(PATIENTS), PATIENTS[1])
    save(window, f"{name}_running")
    worker.progress.emit(len(PATIENTS), len(PATIENTS), PATIENTS[-1])
    worker.finish(results)
    QApplication.processEvents()
    save(window, f"{name}_done")


def overview():
    window = newWindow()
    save(window, "gui_overview")
    window.close()


def tutorialSegment():
    """(a) AI segmentation of a cohort."""
    INSTALL_STATUS["value"] = "not installed"
    window = newWindow()
    setField(window.dataDirEdit, ROOT / "hn_cohort")
    save(header(window), "seg_analysis")
    tab = window.segmentTab
    save(window, "seg_not_installed")

    tab.installRadio.setChecked(True)
    tab.installDirEdit.setText(str(INSTALL_DIR))
    tab._refreshStatus()
    save(window, "seg_install")
    tab.installProgress.setVisible(True)
    tab.stageLabel.setText(f"Installing model 7...")
    tab.stageLabel.setVisible(True)
    tab.installBtn.setEnabled(False)
    save(window, "seg_installing")
    tab.installProgress.setVisible(False)
    tab.stageLabel.setVisible(False)
    INSTALL_STATUS["value"] = "installed"
    tab.existingDirEdit.setText(str(INSTALL_DIR))
    tab.useExistingRadio.setChecked(True)
    tab._refreshStatus()
    save(window, "seg_installed")

    runAndFinish(window, tab, "seg", f"Applying {AI_MODEL} AI segmentation model...")
    window.close()


def tutorialDerive():
    """(b) AI segmentation, then derived structures and clinical predictors."""
    INSTALL_STATUS["value"] = "installed"
    window = newWindow()
    setField(window.dataDirEdit, ROOT / "hn_cohort")
    tab = window.modelTab
    window.tabs.blockSignals(True)
    window.goToTab("model")
    window.tabs.blockSignals(False)
    window._currentTab = window.tabs.currentIndex()
    setField(tab.csvEdits["predictors_csv"], ROOT / "csv" / "clinical_predictors_xerostomia.csv")
    save(window, "derive_inputs")

    SEGMENTED["value"] = False
    DIALOGS.append(("derive_save_first", "Save and continue"))
    DIALOGS.append(("derive_segment_first", "Cancel"))
    tab.runBtn.click()
    QApplication.processEvents()

    SEGMENTED["value"] = True
    runAndFinish(window, tab, "derive", "Starting...", saveSettings=False)
    window.close()


def tutorialExisting():
    """(c) A model run on existing structures."""
    window = newWindow()
    window.modelCombo.setCurrentText("Esophagitis (Huang)")
    QApplication.processEvents()
    setField(window.dataDirEdit, ROOT / "lung_cohort")
    window.planInfoEdit.setText(str(ROOT / "csv" / "plan_info_esophagitis.csv"))
    save(header(window), "existing_analysis")
    save(window, "existing_segment")
    window.tabs.blockSignals(True)
    window.goToTab("model")
    window.tabs.blockSignals(False)
    window._currentTab = window.tabs.currentIndex()
    tab = window.modelTab
    tab._structRows[0]["nameEdit"].setText("ESOPHAGUS")
    setField(tab.csvEdits["predictors_csv"], ROOT / "csv" / "clinical_predictors_esophagitis.csv")
    save(window, "existing_inputs")
    runAndFinish(window, tab, "existing", "Starting...")
    window.close()


def tutorialPredictors():
    """(d) A model run from pre-computed predictors alone."""
    window = newWindow()
    window.predictorsRadio.setChecked(True)
    QApplication.processEvents()
    tab = window.modelTab
    setField(tab.csvEdits["predictors_csv"], ROOT / "csv" / "precomputed_predictors_xerostomia.csv")
    window._currentTab = window.tabs.currentIndex()
    save(window, "predictors_inputs")
    runAndFinish(window, tab, "predictors", "Starting...")
    window.close()


def main():
    app = QApplication(sys.argv)
    from validate.gui import theme
    theme.apply(app)
    patchValidate()
    setUpDemo()
    IMAGES.mkdir(parents=True, exist_ok=True)
    try:
        overview()
        tutorialSegment()
        tutorialDerive()
        tutorialExisting()
        tutorialPredictors()
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    if DIALOGS:
        raise RuntimeError(f"Dialogs expected but not shown: {DIALOGS}")
    print(f"Saved {len(list(IMAGES.glob('*.png')))} screenshots to {IMAGES}")


if __name__ == "__main__":
    main()
