"""Maintain logs for the auto-segmentation pipeline.

1. Structure-availability log: one CSV per AI model, stored in
the analysis directory, recording (patient_id, structure_name) for every
structure exported to DICOM for that patient. Review to avoid re-running models.

2. Error log: Text file recording per-patient errors only (one line each).

3. Task log: task_log.yaml in the analysis directory, written only by the tool.
   Holds the settings hash (decides whether a run may resume), one entry per
   invocation with its provenance ID, software versions and hardware, and
   per-patient results.
"""

import csv
import hashlib
import json
import os
import platform
import subprocess
import warnings
from contextlib import contextmanager
from datetime import datetime
from importlib import metadata
from pathlib import Path

import yaml

LOG_DIR_NAME = "_autoseg_logs"
TASK_LOG_NAME = "task_log.yaml"


def logDir(analysisDir):
    d = Path(analysisDir) / LOG_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safeName(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))


def availabilityLogPath(analysisDir, aiModelName):
    return logDir(analysisDir) / f"{_safeName(aiModelName)}_availability.csv"


def readAvailability(analysisDir, aiModelName):
    """Return the {(patient_id, structure_name)} set logged for aiModelName."""
    path = availabilityLogPath(analysisDir, aiModelName)
    entries = set()
    if path.exists():
        with open(path, "r", newline="") as f:
            for row in csv.DictReader(f):
                entries.add((row["patient_id"], row["structure_name"]))
    return entries


def isAvailable(analysisDir, aiModelName, patientId, structureName):
    return (patientId, structureName) in readAvailability(analysisDir, aiModelName)


def recordAvailability(analysisDir, aiModelName, patientId, structureName):
    path = availabilityLogPath(analysisDir, aiModelName)
    isNew = not path.exists()
    if not isNew and isAvailable(analysisDir, aiModelName, patientId, structureName):
        return
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if isNew:
            writer.writerow(["patient_id", "structure_name", "logged_at"])
        writer.writerow([patientId, structureName,
                         datetime.now().isoformat(timespec="seconds")])


class ErrorLog:
    """Per-invocation failure log: one line per per-patient error, nothing else."""

    def __init__(self, analysisDir):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = logDir(analysisDir) / f"error_log_{timestamp}.txt"
        self._file = open(self.path, "w")

    def error(self, patientId, message):
        oneLine = " ".join(str(message).split())
        self._file.write(f"[ERROR] {patientId}: {oneLine}\n")
        self._file.flush()

    def close(self):
        self._file.close()


#============================================
# Task log (task_log.yaml)
#============================================
def settingsHash(settingsPath):
    """SHA-256 of the analysis settings in canonical form, so formatting,
    key order and comments in the settings file don't change it."""
    with open(settingsPath, "r") as f:
        settings = yaml.safe_load(f)
    return _sha256(_canonical(settings))


def startRun(analysisDir, settingsPath, modelFile, errorLogPath=None):
    """Open task_log.yaml for a new invocation.

    Creates task_log.yaml, or resumes it if its settings hash matches the
    current settings file. Appends this invocation's provenance, hardware and
    error log file.

    Args:
        analysisDir (str): analysis folder holding task_log.yaml.
        settingsPath (str): path to the analysis settings file.
        modelFile (str): path to the ROE model JSON used.
        errorLogPath (str or None): this invocation's error log; recorded
            relative to analysisDir.

    Returns:
        (taskLog, runIndex): the task log dict and this invocation's index in taskLog["runs"].

    Raises:
        ValueError: task_log.yaml exists but can't be read, isn't a task log,
            or was written for different settings.
    """
    currentHash = settingsHash(settingsPath)
    path = Path(analysisDir) / TASK_LOG_NAME
    if path.exists():
        try:
            with open(path, "r") as f:
                taskLog = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"{path} can't be read as YAML: {exc}") from None
        if not isinstance(taskLog, dict) or not {"settings_hash", "runs", "patients"} <= taskLog.keys():
            raise ValueError(f"{path} is empty or isn't a validate task log. It may have been "
                             f"edited or damaged; restore it, or move it aside to start a new "
                             f"task log in this folder.")
        if taskLog["settings_hash"] != currentHash:
            raise ValueError(
                f"{path} was written for different analysis settings; "
                f"use a new analysis folder for these settings.")
    else:
        taskLog = {"settings_hash": currentHash, "runs": [], "patients": {}}

    provenance = _provenance(modelFile)
    taskLog["runs"].append({
        "started": _now(),
        "finished": None,
        "provenance_id": _sha256(_canonical({"settings_hash": currentHash, **provenance})),
        "provenance": provenance,
        "hardware": _hardware(),
        "error_log": os.path.relpath(errorLogPath, analysisDir) if errorLogPath else None,
    })
    writeTaskLog(analysisDir, taskLog)
    return taskLog, len(taskLog["runs"]) - 1


def recordPatient(analysisDir, taskLog, runIndex, patientId, section, results, computed=True,
                  warningMessages=None):
    """Store one patient's results under taskLog["patients"][patientId][section]
    and write task_log.yaml.

    The patient's "run" and "warnings" are updated only if computed is True, so
    results reused from an earlier run keep pointing at the run that made them.
    """
    entry = taskLog["patients"].setdefault(patientId, {})
    entry[section] = results
    if computed:
        entry["run"] = runIndex
        if warningMessages:
            entry["warnings"] = list(warningMessages)
        else:
            entry.pop("warnings", None)
    writeTaskLog(analysisDir, taskLog)


def recordRunWarnings(analysisDir, taskLog, runIndex, warningMessages):
    """Store run-level warnings (e.g. from building the DataCapsule) under this
    invocation's entry and write task_log.yaml."""
    if warningMessages:
        taskLog["runs"][runIndex]["warnings"] = list(warningMessages)
        writeTaskLog(analysisDir, taskLog)


@contextmanager
def collectWarnings():
    """Collect the messages of UserWarnings raised inside the block, without
    printing them, so they can be written to task_log.yaml.

    Usage:
        with collectWarnings() as messages:
            ...
        # messages now holds the unique warning texts, in order
    """
    messages = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield messages
    for w in caught:
        text = str(w.message)
        if issubclass(w.category, UserWarning) and text not in messages:
            messages.append(text)


def finishRun(analysisDir, taskLog, runIndex):
    """Mark this invocation as finished and write task_log.yaml."""
    taskLog["runs"][runIndex]["finished"] = _now()
    writeTaskLog(analysisDir, taskLog)


def writeTaskLog(analysisDir, taskLog):
    """Write task_log.yaml atomically (temporary file, then rename)."""
    path = Path(analysisDir) / TASK_LOG_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmpPath = path.with_name(path.name + ".tmp")
    with open(tmpPath, "w") as f:
        yaml.safe_dump(taskLog, f, sort_keys=False)
    os.replace(tmpPath, path)


def _provenance(modelFile):
    validateDir = Path(__file__).resolve().parent
    commit = _git(validateDir, "rev-parse", "HEAD")
    changes = _git(validateDir, "status", "--porcelain", "--untracked-files=no")
    try:
        pycerrVersion = metadata.version("pycerr")
    except metadata.PackageNotFoundError:
        pycerrVersion = None
    with open(modelFile, "rb") as f:
        modelHash = hashlib.sha256(f.read()).hexdigest()
    return {
        "validate_commit": commit,
        "user_modified": bool(changes) if commit else None,
        "pycerr_version": pycerrVersion,
        "model_file_sha256": modelHash,
        "python": platform.python_version(),
    }


def _hardware():
    gpus = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "gpus": gpus.splitlines() if gpus else [],
    }


def _git(repoDir, *args):
    return _run(["git", "-C", str(repoDir), *args])


def _run(cmd):
    """Output of cmd, or None if it can't be run or fails."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now():
    return datetime.now().isoformat(timespec="seconds")
