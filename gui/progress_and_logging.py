"""Shared functionalities of the Segment and Model tabs: Run, Stop, Log, progress, and the checks made before a run.
"""

from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QMessageBox
)

from validate.gui import theme
from validate import logs

LABEL_WIDTH = 150


def buttonRow(buttons):
    """A left-aligned row of buttons."""
    row = QHBoxLayout()
    for button in buttons:
        row.addWidget(button)
    row.addStretch()
    return row


class ManageRun(QWidget):
    """Manage progress (run, stop, log) and report status.
    Used by both the Segment and Model tabs.
    """
    TAB = None              # "segment" or "model" (see logs.TABS)
    RESULTS_LABEL = None    # e.g. "NTCP results"

    def __init__(self, host, parent=None):
        """Set up the tab.

        Args:
            host (MainWindow): Main window holding the shared settings (analysis
                folder, data folder, model); saves them before a run.
            parent (QWidget, optional): Qt parent.
        """
        super().__init__(parent)
        self.host = host
        self.worker = None
        self._errorLogPath = None

    def _buildRunGroup(self, extraButtons=()):
        """The Run section: Run, Stop, the log buttons and any extra buttons on one row, then progress.

        Args:
            extraButtons (iterable[QPushButton]): Tab-specific buttons added to the row.

        Returns:
            QGroupBox: The Run section.
        """
        runGroup, runLayout = theme.section("Run")
        runLayout.addLayout(buttonRow(self._buildRunButtons() + self._buildLogButtons() + list(extraButtons)))
        self._addProgress(runLayout)
        return runGroup

    def _buildRunButtons(self):
        """Run and Stop."""
        self.runBtn = QPushButton("Run")
        theme.markPrimary(self.runBtn)
        self.runBtn.clicked.connect(self._onRun)
        self.stopBtn = QPushButton("Stop")
        self.stopBtn.setToolTip("Stops before the next patient.")
        self.stopBtn.setEnabled(False)
        self.stopBtn.clicked.connect(self._onStop)
        return [self.runBtn, self.stopBtn]

    def _buildLogButtons(self):
        """View task log and View error log."""
        viewTaskLogBtn = QPushButton("View task log")
        viewTaskLogBtn.clicked.connect(self._viewTaskLog)
        viewErrorLogBtn = QPushButton("View error log")
        viewErrorLogBtn.clicked.connect(self._viewErrorLog)
        return [viewTaskLogBtn, viewErrorLogBtn]

    def _addProgress(self, layout):
        """The stage message and progress bar, hidden until the first run."""
        self.stageLabel = QLabel("")
        self.stageLabel.setVisible(False)
        layout.addWidget(self.stageLabel)
        self.progressBar = QProgressBar()
        self.progressBar.setVisible(False)
        layout.addWidget(self.progressBar)

    # Running

    def _onRun(self):
        """Start a run: save the settings (asking first), check they haven't changed
        since this tab's results were made, then start the tab's worker."""
        if not self.host.checkIdle():      # one run at a time across the window
            return
        if not self.host.ensureSaved(required=True):
            return
        analysisDir = self.host.analysisDir()
        if not self._checkSettingsUnchanged(analysisDir):
            return
        worker = self._makeWorker(analysisDir)
        if worker is None:
            return

        self.worker = worker
        worker.stage.connect(self._onStage)
        worker.progress.connect(self._onProgress)
        worker.finishedOk.connect(self._onFinished)
        worker.failed.connect(self._onFailed)
        # In progress: a busy (animated) bar; the stage and patient count are shown above it
        self._stage, self._done, self._total = "Starting...", 0, None
        self.progressBar.setRange(0, 0)
        self._showStatus()
        self.stageLabel.setVisible(True)
        self.progressBar.setVisible(True)
        self._setRunning(True)
        worker.start()

    def _checkSettingsUnchanged(self, analysisDir):
        """If this tab's settings changed since its results were made (e.g.
        analysis.yaml was edited by hand), offer to clear its results.
        Returns False if the user cancels."""
        try:
            taskLog = logs.readTaskLog(analysisDir)
        except ValueError as exc:
            QMessageBox.critical(self, "Task log", str(exc))
            return False
        if taskLog is None:
            return True
        recorded = taskLog["settings_hash"].get(self.TAB)
        current = logs.settingsHashes(Path(analysisDir) / "analysis.yaml")[self.TAB]
        if recorded is None or recorded == current:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Settings changed")
        box.setText(f"The settings changed since the {self.RESULTS_LABEL} were made.\n"
                    f"Clear the {self.RESULTS_LABEL} and run?")
        clearBtn = box.addButton("Clear and run", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        if box.clickedButton() is not clearBtn:
            return False
        logs.clearResults(analysisDir, self.TAB)
        return True

    def _makeWorker(self, analysisDir):
        """Return the worker for this run, or None to cancel it."""
        raise NotImplementedError

    def _setRunning(self, running):
        """Enable Stop while running, and Run otherwise.

        Args:
            running (bool): True while a run is in progress.
        """
        self.runBtn.setEnabled(not running)
        self.stopBtn.setEnabled(running)

    def _onStop(self):
        """Ask the running worker to stop before the next patient."""
        if self.worker is not None:
            self.worker.requestStop()
            self.stopBtn.setEnabled(False)
            self._onStage("Stopping after the current patient...")

    def _onStage(self, message):
        """Show the run's current stage (e.g. the AI model being applied)."""
        self._stage = message
        self._showStatus()

    def _onProgress(self, done, total, patientId):
        """Update the count of patients done.

        Args:
            done (int): Patients processed so far.
            total (int): Patients in the cohort.
            patientId (str or None): The patient just processed (None at the start).
        """
        self._done, self._total = done, total
        self._showStatus()

    def _showStatus(self):
        """While running: "<stage> · <done>/<total> patients done"."""
        count = f"{self._done}/{self._total} patients done" if self._total is not None else ""
        self.stageLabel.setText("  ·  ".join(part for part in (self._stage, count) if part))

    def _showOutcome(self, outcome):
        """End the busy bar: "<outcome> (<done>/<total> patients)", the bar filled to
        the patients done, and the stage line hidden."""
        total = self._total
        self.progressBar.setRange(0, max(total or 0, 1))
        self.progressBar.setValue(self._done if total else 0)
        self.progressBar.setFormat(f"{outcome} ({self._done}/{total} patients)" if total is not None else outcome)
        self.stageLabel.setVisible(False)

    def _onFinished(self, results, errorLogPath):
        """Show that the run finished (or stopped).

        Args:
            results: The run function's results.
            errorLogPath (str): This run's error log.
        """
        self._errorLogPath = errorLogPath
        self._setRunning(False)
        stopped = self.worker is not None and self.worker._stopRequested
        aborted = self.worker is not None and self.worker.aborted
        self._showOutcome("Aborted" if aborted else "Stopped" if stopped else "Done")

    def _onFailed(self, message, errorLogPath):
        """Show that the run failed, with its error message.

        Args:
            message (str): The error message.
            errorLogPath (str): This run's error log.
        """
        self._errorLogPath = errorLogPath
        self._setRunning(False)
        if self.worker is not None and self.worker.aborted:
            self._showOutcome("Aborted")     # no pop-up: the window is closing
            return
        self._showOutcome("Failed")
        QMessageBox.critical(self, "Run failed", message)

    # Logs

    def _viewTaskLog(self):
        """Open the analysis folder's task_log.yaml, or say there isn't one yet."""
        analysisDir = self.host.analysisDir()
        path = Path(analysisDir) / logs.TASK_LOG_NAME if analysisDir else None
        if path is None or not path.exists():
            QMessageBox.information(self, "Task log", "No task log yet; it's written by the first run.")
            return
        self._openPath(path)

    def _viewErrorLog(self):
        """Open this tab's last error log (else the analysis folder's latest one),
        or say there isn't one yet."""
        path = self._errorLogPath
        analysisDir = self.host.analysisDir()
        if path is None and analysisDir:
            errorLogs = sorted((Path(analysisDir) / logs.LOG_DIR_NAME).glob("error_log_*.txt"))
            path = errorLogs[-1] if errorLogs else None
        if path is None:
            QMessageBox.information(self, "Error log", "No error log yet; one is written by each run.")
            return
        self._openPath(path)

    def _openPath(self, path):
        """Open a file or folder with the system's default application.

        Args:
            path (str or pathlib.Path): File or folder to open.
        """
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
