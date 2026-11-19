"""Background threads (ensures installing AI models, running segmentation and evaluating dosimetric
models never blocks the GUI thread.
"""

import threading
import time

import psutil
from PyQt5.QtCore import QThread, pyqtSignal

from validate.run import applyModelToCohort, applyAutoSegToCohort, deriveStructuresForCohort
from validate.seg.autoseg_pipeline import installMissingModels, removePartialDownloads
from validate.logs import ErrorLog


def killChildProcesses(timeout=3):
    """Terminate this process's child processes and their children (AI model
    inference, git, uv, weights downloads), killing any still running after timeout s."""
    children = psutil.Process().children(recursive=True)
    for proc in children:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(children, timeout=timeout)
    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass


def _abortThread(thread):
    """Kill the thread's child processes until it finishes, in the background:
    pyCERR may start another process (e.g. the next install step) after one is killed."""
    def keepKilling():
        while thread.isRunning():
            killChildProcesses()
            time.sleep(0.2)
    threading.Thread(target=keepKilling, daemon=True).start()


class InstallWorker(QThread):
    """Runs installMissingModels off the GUI thread. Supports AI model installation
    (git clone + weights download + env creation) without blocking the window.
    """
    stage = pyqtSignal(str)
    finishedOk = pyqtSignal(list)   # [(modelNum, success, message), ...]
    failed = pyqtSignal(str)

    def __init__(self, modelNums, installBaseDir, force=False, installOptions=None, parent=None):
        """Set up the install of AI models.

        Args:
            modelNums (list[int]): AI model numbers to install.
            installBaseDir (str): Folder to install the models into.
            force (bool): If True, reinstall models that are already installed.
            installOptions (dict, optional): Passed on to pyCERR's install_utils
                (e.g. weightsUrl, for a single model).
            parent (QObject, optional): Qt parent.
        """
        super().__init__(parent)
        self.modelNums = modelNums
        self.installBaseDir = installBaseDir
        self.force = force
        self.installOptions = installOptions or {}
        self.aborted = False

    def abort(self):
        """Stop the install now: kill its processes. Unfinished weights downloads
        are deleted once it stops (see run)."""
        self.aborted = True
        _abortThread(self)

    def run(self):
        """Install the models, then emit finishedOk with each model's result,
        or failed with the error message. After an abort, unfinished weights
        downloads are deleted first."""
        try:
            results = installMissingModels(
                self.modelNums, self.installBaseDir,
                progressCallback=lambda msg: self.stage.emit(msg),
                force=self.force, shouldStop=lambda: self.aborted, **self.installOptions)
            if self.aborted:
                removePartialDownloads(self.modelNums, self.installBaseDir)
            self.finishedOk.emit(results)
        except Exception as exc:
            if self.aborted:
                removePartialDownloads(self.modelNums, self.installBaseDir)
            self.failed.emit(str(exc))


class RunWorker(QThread):
    """Applies a selected method (Segment/Model) to the entire cohort, maintaining
      a distinct  error log, progress, and a stop request that takes effect before the next patient."""
    stage = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)   # done, total, patientId
    finishedOk = pyqtSignal(object, str)   # results, errorLogPath
    failed = pyqtSignal(str, str)          # message, errorLogPath

    def __init__(self, analysisDir, parent=None):
        """Set up a run over the cohort.

        Args:
            analysisDir (str): Analysis folder holding analysis.yaml; receives the logs and outputs.
            parent (QObject, optional): Qt parent.
        """
        super().__init__(parent)
        self.analysisDir = analysisDir
        self._stopRequested = False
        self.aborted = False

    def requestStop(self):
        """Ask the run to stop before the next patient."""
        self._stopRequested = True

    def abort(self):
        """Stop the run now: kill its processes (AI model inference). The patient
        being run is recorded as aborted, and the run stops there."""
        self._stopRequested = True
        self.aborted = True
        _abortThread(self)

    def run(self):
        """Run over the cohort with a new error log, then emit finishedOk with the
        results and the error log's path, or failed with the error message and path."""
        # The run functions write their own errors (setup and per patient) to the error log
        errorLog = ErrorLog(self.analysisDir)
        try:
            results = self._run(errorLog)
            errorLog.close()
            self.finishedOk.emit(results, str(errorLog.path))
        except Exception as exc:
            errorLog.close()
            self.failed.emit(str(exc), str(errorLog.path))

    def _run(self, errorLog):
        """Run the tab's function over the cohort. Implemented by subclasses.

        Args:
            errorLog (validate.logs.ErrorLog): Error log for this run.

        Returns:
            The run function's results.
        """
        raise NotImplementedError


class SegmentWorker(RunWorker):
    """Runs selected AI models (run.applyAutoSegToCohort)."""

    def __init__(self, analysisDir, overwrite=False, parent=None):
        """Set up a Segment run.

        Args:
            analysisDir (str): Analysis folder holding analysis.yaml; receives the logs and outputs.
            overwrite (bool): If True, run the AI models again for patients that already have outputs.
            parent (QObject, optional): Qt parent.
        """
        super().__init__(analysisDir, parent)
        self.overwrite = overwrite

    def _run(self, errorLog):
        """Run the AI models over the cohort.

        Args:
            errorLog (validate.logs.ErrorLog): Error log for this run.

        Returns:
            dict: {patientId: {aiModel: "ok" | "ok (cached)" | "error: <message>"}}.
        """
        return applyAutoSegToCohort(
            self.analysisDir, errorLog,
            progressCallback=lambda done, total, pid: self.progress.emit(done, total, pid),
            stageCallback=lambda msg: self.stage.emit(msg),
            overwrite=self.overwrite,
            shouldStop=lambda: self._stopRequested, isAborted=lambda: self.aborted)


class ModelWorker(RunWorker):
    """Derives modelled structures and computes NTCP (run.applyModelToCohort)."""

    def _run(self, errorLog):
        """Derive the structures and compute NTCP over the cohort.

        Args:
            errorLog (validate.logs.ErrorLog): Error log for this run.

        Returns:
            pandas.DataFrame: One row per patient: patient_id, ntcp, status, message.
        """
        return applyModelToCohort(
            self.analysisDir, errorLog,
            progressCallback=lambda done, total, pid: self.progress.emit(done, total, pid),
            shouldStop=lambda: self._stopRequested, isAborted=lambda: self.aborted)


class DeriveWorker(RunWorker):
    """Derives the modelled structures only, without NTCP (run.deriveStructuresForCohort)."""

    def _run(self, errorLog):
        """Derive the structures over the cohort.

        Args:
            errorLog (validate.logs.ErrorLog): Error log for this run.

        Returns:
            pandas.DataFrame: One row per patient: patient_id, status, message.
        """
        return deriveStructuresForCohort(
            self.analysisDir, errorLog,
            progressCallback=lambda done, total, pid: self.progress.emit(done, total, pid),
            shouldStop=lambda: self._stopRequested, isAborted=lambda: self.aborted)
