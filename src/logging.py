"""Maintain logs for the auto-segmentation pipeline.

1. Structure-availability log: one CSV per AI model, stored in
the cohort directory, recording (patient_id, structure_name) for every
structure exported to DICOM for that patient. Review to avoid re-running models.

2. Task log: Text file recording stage progress and per-patient errors.
"""

import csv
from datetime import datetime
from pathlib import Path

LOG_DIR_NAME = "_autoseg_logs"


def logDir(cohortDir):
    d = Path(cohortDir) / LOG_DIR_NAME
    d.mkdir(exist_ok=True)
    return d


def _safeName(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))


def availabilityLogPath(cohortDir, aiModelName):
    return logDir(cohortDir) / f"{_safeName(aiModelName)}_availability.csv"


def readAvailability(cohortDir, aiModelName):
    """Return the {(patient_id, structure_name)} set logged for aiModelName."""
    path = availabilityLogPath(cohortDir, aiModelName)
    entries = set()
    if path.exists():
        with open(path, "r", newline="") as f:
            for row in csv.DictReader(f):
                entries.add((row["patient_id"], row["structure_name"]))
    return entries


def isAvailable(cohortDir, aiModelName, patientId, structureName):
    return (patientId, structureName) in readAvailability(cohortDir, aiModelName)


def recordAvailability(cohortDir, aiModelName, patientId, structureName):
    path = availabilityLogPath(cohortDir, aiModelName)
    isNew = not path.exists()
    if not isNew and isAvailable(cohortDir, aiModelName, patientId, structureName):
        return
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if isNew:
            writer.writerow(["patient_id", "structure_name", "logged_at"])
        writer.writerow([patientId, structureName,
                         datetime.now().isoformat(timespec="seconds")])


class TaskLog:
    """Per-invocation log: stage progress and per-patient errors."""

    def __init__(self, cohortDir):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = logDir(cohortDir) / f"task_log_{timestamp}.txt"
        self._file = open(self.path, "w")
        self.info(f"Task log started {datetime.now().isoformat(timespec='seconds')}")

    def info(self, message):
        self._file.write(f"{message}\n")
        self._file.flush()

    def stage(self, message):
        self.info(f"--- {message} ---")

    def error(self, patientId, message):
        self.info(f"[ERROR] {patientId}: {message}")

    def summary(self, succeeded, failed):
        self.info(f"Summary: {succeeded} succeeded, {failed} failed")

    def close(self):
        self.info(f"Task log closed {datetime.now().isoformat(timespec='seconds')}")
        self._file.close()
