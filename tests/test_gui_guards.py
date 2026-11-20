"""The main window's safeguards for task_log.yaml (gui/main_window.py):
- one run at a time: while a Segment run, Model run or AI model install is in
  progress, no other can start and settings can't be saved, since each run rewrites
  task_log.yaml;
- saving changed settings clears exactly the results that depend on them.

Uses the real main window (offscreen); a run in progress is a stand-in thread.
"""

import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QThread
from PyQt5.QtWidgets import QApplication, QMessageBox

from validate import logs
from validate.core import analysis
from validate.gui.main_window import MainWindow

APP = QApplication.instance() or QApplication([])


class _RunInProgress(QThread):
    """Runs until released."""

    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def run(self):
        self.release.wait(30)


@pytest.fixture
def window(monkeypatch):
    """The main window, with pop-ups recorded instead of shown."""
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text, *args: shown.append(text))
    win = MainWindow()
    win.shown = shown
    yield win
    win.deleteLater()


@pytest.fixture
def runInProgress():
    thread = _RunInProgress()
    thread.start()
    yield thread
    thread.release.set()
    thread.wait()


@pytest.mark.parametrize("runningTab, runningSlot, label, startTab, startAction, startedSlot", [
    ("segmentTab", "worker", "A Segment run", "modelTab", "_onRun", "worker"),
    ("modelTab", "worker", "A Model run", "segmentTab", "_onRun", "worker"),
    ("segmentTab", "installWorker", "An AI model install", "segmentTab", "_onRun", "worker"),
    ("segmentTab", "worker", "A Segment run", "segmentTab", "_install", "installWorker"),
], ids=["Model run during Segment run", "Segment run during Model run",
        "Segment run during install", "install during Segment run"])
def test_secondRunRefused(window, runInProgress, runningTab, runningSlot, label,
                          startTab, startAction, startedSlot):
    setattr(getattr(window, runningTab), runningSlot, runInProgress)
    started = getattr(getattr(window, startTab), startedSlot)

    getattr(getattr(window, startTab), startAction)()

    assert window.shown == [f"{label} is in progress. Wait for it to finish, or stop it."]
    assert getattr(getattr(window, startTab), startedSlot) is started      # nothing new started
    assert window.runningTask()[1] is runInProgress


def test_settingsNotSavedDuringRun(window, runInProgress, tmp_path):
    analysisDir = tmp_path / "analysis"
    window.dataDirEdit.setText(str(tmp_path))
    window.analysisDirEdit.setText(str(analysisDir))
    analysis.saveSettings(window.formSettings(), str(analysisDir))
    saved = (analysisDir / analysis.FILE_NAME).read_text()
    window.segmentTab.worker = runInProgress
    window.segmentTab.cpuRadio.setChecked(True)          # the form now differs from the file

    assert window.ensureSaved() is False
    assert (analysisDir / analysis.FILE_NAME).read_text() == saved
    assert "Settings can't be saved until it finishes" in window.shown[-1]


# Saving changed settings clears the results that depend on them

def _useCpu(window, tmp_path):
    window.segmentTab.cpuRadio.setChecked(True)


def _setPredictorValues(window, tmp_path):
    window.modelTab.csvEdits["predictors_csv"].setText(str(tmp_path / "predictors.csv"))


def _setPlanInfo(window, tmp_path):
    window.planInfoEdit.setText(str(tmp_path / "plan.csv"))


@pytest.fixture
def analysisWithResults(window, tmp_path, monkeypatch):
    """Saved settings, with a Segment and a Model result for pt1. Save pop-ups are
    answered "Save and continue" and their text recorded in window.shown."""
    def saveAndContinue(box):
        window.shown.append(box.text())
        box._clicked = next(b for b in box.buttons() if b.text() == "Save and continue")
        return 0

    monkeypatch.setattr(QMessageBox, "exec_", saveAndContinue)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._clicked)
    analysisDir = tmp_path / "analysis"
    window.dataDirEdit.setText(str(tmp_path))
    window.analysisDirEdit.setText(str(analysisDir))
    settingsPath = analysis.saveSettings(window.formSettings(), str(analysisDir))
    taskLog, runIndex = logs.startRun(analysisDir, settingsPath, "segment")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "segment", {"status": "ok", "files": []},
                      key="CT_HN_SMIT")
    taskLog, runIndex = logs.startRun(analysisDir, settingsPath, "model")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "ntcp", {"status": "ok", "value": 0.5})
    return analysisDir


@pytest.mark.parametrize("change, keptSections", [
    (_useCpu, ["ntcp"]),
    (_setPredictorValues, ["segment"]),
    (_setPlanInfo, []),
], ids=["device: Segment results cleared", "predictor values: Model results cleared",
        "plan info: both cleared"])
def test_savingClearsDependentResults(window, analysisWithResults, tmp_path, change, keptSections):
    change(window, tmp_path)

    assert window.ensureSaved() is True

    assert analysis.readSettings(str(analysisWithResults)) == window.formSettings()
    patient = (logs.readTaskLog(analysisWithResults)["patients"].get("pt1") or {})
    assert sorted(patient) == keptSections
