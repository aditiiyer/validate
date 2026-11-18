"""Maintain the logs of an analysis.

1. Error log: Text file recording per-patient errors only (one line each), one per invocation.

2. Task log: task_log.yaml in the analysis directory, written only by the tool.
   Holds one settings hash per tab (decides whether that tab's runs may resume),
   one entry per invocation with the tab that ran, its provenance ID, software
   commits and hardware, and per-patient results:
       patients:
         pt001:
           segment: {<AI model>: {status, run, files, labels, warnings}}
           ntcp:    {status, value | message, run, warnings}

   Results recorded to the task log are tied to the chosen settings. Modifying
   the settings clears associated results from the task log (after you confirm),
   so the two always match. Output files are kept until the tab is re-run.
"""

import csv
import fnmatch
import hashlib
import json
import os
import platform
import subprocess
import warnings
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import yaml

from validate.core.analysis import tabSettings

LOG_DIR_NAME = "_autoseg_logs"
TASK_LOG_NAME = "task_log.yaml"
SUMMARY_NAME = "segment_summary.csv"

TABS = ("segment", "model")
# The section of each patient's entry holding a tab's results
TAB_SECTIONS = {"segment": "segment", "model": "ntcp"}
# Key under a patient's "segment" section listing the structures the Model tab
# derived and exported: {"status", "files": {structName: file}, "message" (on error), "run"}
DERIVED_KEY = "derived"
SUMMARY_COLUMNS = ["patient_id", "ai_model", "status", "run", "file", "label", "structure", "message"]


def logDir(analysisDir):
    d = Path(analysisDir) / LOG_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


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
class SettingsChangedError(ValueError):
    """A tab's settings changed since its results in task_log.yaml were made.
    Its results can be cleared (clearResults) so the tab can run again."""

    def __init__(self, tab, path):
        self.tab = tab
        super().__init__(f"The {tab} settings changed since the {tab} results in {path} were made. "
                         f"Clear the {tab} results to run with the new settings.")


def settingsHashes(settingsPath):
    """{tab: SHA-256 of the settings that tab's results depend on (core.analysis.tabSettings)},
    in canonical form, so formatting, key order and comments don't change them."""
    with open(settingsPath, "r") as f:
        settings = yaml.safe_load(f)
    return {tab: _sha256(_canonical(tabSettings(settings, tab))) for tab in TABS}


def readTaskLog(analysisDir):
    """Return the task log in analysisDir, or None if there is none yet.

    Raises:
        ValueError: task_log.yaml can't be read, isn't a task log, or was
            written by an earlier version of validate.
    """
    path = Path(analysisDir) / TASK_LOG_NAME
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            taskLog = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} can't be read as YAML: {exc}") from None
    if not isinstance(taskLog, dict) or not {"settings_hash", "runs", "patients"} <= taskLog.keys():
        raise ValueError(f"{path} is empty or isn't a validate task log. It may have been "
                         f"edited or damaged; restore it, or move it aside to start a new "
                         f"task log in this folder.")
    if not isinstance(taskLog["settings_hash"], dict):
        raise ValueError(f"{path} was written by an earlier version of validate; "
                         f"move it aside to start a new task log in this folder.")
    return taskLog


def startRun(analysisDir, settingsPath, tab, errorLogPath=None, details=None):
    """Open task_log.yaml for a new invocation of a tab.

    Creates task_log.yaml, or resumes it if the tab's settings hash matches the
    current settings (or the tab hasn't run yet). Appends this invocation's tab,
    provenance, device, hardware and error log file.

    Args:
        analysisDir (str): analysis folder holding task_log.yaml.
        settingsPath (str): path to the analysis settings file.
        tab (str): "segment" or "model".
        errorLogPath (str or None): this invocation's error log; recorded
            relative to analysisDir.
        details (dict or None): tab-specific provenance added to the software
            provenance (see modelFileProvenance, aiModelProvenance).

    Returns:
        (taskLog, runIndex): the task log dict and this invocation's index in taskLog["runs"].

    Raises:
        SettingsChangedError: the tab's settings changed since its results were made.
        ValueError: task_log.yaml exists but can't be read or isn't a task log.
    """
    currentHash = settingsHashes(settingsPath)[tab]
    taskLog = readTaskLog(analysisDir)
    if taskLog is None:
        taskLog = {"settings_hash": {t: None for t in TABS}, "runs": [], "patients": {}}
    recordedHash = taskLog["settings_hash"].get(tab)
    if recordedHash is not None and recordedHash != currentHash:
        raise SettingsChangedError(tab, Path(analysisDir) / TASK_LOG_NAME)
    taskLog["settings_hash"][tab] = currentHash

    with open(settingsPath, "r") as f:
        device = ((yaml.safe_load(f) or {}).get("compute") or {}).get("device", "cpu")
    provenance = {**_provenance(), **(details or {})}
    taskLog["runs"].append({
        "tab": tab,
        "started": _now(),
        "finished": None,
        "provenance_id": _sha256(_canonical({"settings_hash": currentHash, **provenance})),
        "provenance": provenance,
        "device": device,
        "hardware": _hardware(),
        "error_log": os.path.relpath(errorLogPath, analysisDir) if errorLogPath else None,
    })
    writeTaskLog(analysisDir, taskLog)
    return taskLog, len(taskLog["runs"]) - 1


def clearResults(analysisDir, tab):
    """Remove a tab's results from every patient in task_log.yaml and forget its
    settings hash, so the tab can run with new settings. Runs (provenance) are kept.

    Returns:
        dict or None: the updated task log, or None if there is none.
    """
    taskLog = readTaskLog(analysisDir)
    if taskLog is None:
        return None
    section = TAB_SECTIONS[tab]
    for patientId in list(taskLog["patients"]):
        entry = taskLog["patients"][patientId]
        entry.pop(section, None)
        if tab == "model":
            # Derived exports are listed under segment but made by the Model tab
            (entry.get("segment") or {}).pop(DERIVED_KEY, None)
            if entry.get("segment") == {}:
                del entry["segment"]
        if not entry:
            del taskLog["patients"][patientId]
    taskLog["settings_hash"][tab] = None
    writeTaskLog(analysisDir, taskLog)
    return taskLog


def recordResult(analysisDir, taskLog, runIndex, patientId, section, result, key=None,
                 warningMessages=None):
    """Store one patient's result and write task_log.yaml.

    The result is stored under taskLog["patients"][patientId][section], or
    [section][key] when key is given (e.g. the AI model's name under "segment"),
    with the run that made it and any warnings.
    """
    result = {**result, "run": runIndex}
    if warningMessages:
        result["warnings"] = list(warningMessages)
    entry = taskLog["patients"].setdefault(patientId, {})
    if key is None:
        entry[section] = result
    else:
        entry.setdefault(section, {})[key] = result
    writeTaskLog(analysisDir, taskLog)


def isSegmented(analysisDir, taskLog, patientId, aiModel):
    """True if aiModel ran successfully for patientId and all its recorded output
    files (relative to analysisDir) still exist."""
    patient = ((taskLog or {}).get("patients") or {}).get(patientId) or {}
    result = (patient.get("segment") or {}).get(aiModel) or {}
    files = result.get("files") or []
    return (result.get("status") == "ok" and bool(files)
            and all((Path(analysisDir) / f).exists() for f in files))


def generateSummary(analysisDir):
    """Write segment_summary.csv in analysisDir from the task log's segment results:
    one row per patient, AI model, output file and label.

    Returns:
        str: path to the CSV.

    Raises:
        FileNotFoundError: there is no task log in analysisDir yet.
    """
    taskLog = readTaskLog(analysisDir)
    if taskLog is None:
        raise FileNotFoundError(f"No {TASK_LOG_NAME} in {analysisDir}; run Segment first.")
    rows = []
    for patientId, patient in taskLog["patients"].items():
        for aiModel, result in (patient.get("segment") or {}).items():
            if aiModel == DERIVED_KEY:
                base = {"patient_id": patientId, "ai_model": DERIVED_KEY, "status": result.get("status"),
                        "run": result.get("run"), "message": result.get("message")}
                files = result.get("files") or {}
                if not files:
                    rows.append(base)
                for structName, file in files.items():
                    rows.append({**base, "file": file, "structure": structName})
                continue
            base = {"patient_id": patientId, "ai_model": aiModel, "status": result.get("status"),
                    "run": result.get("run"), "message": result.get("message")}
            files = result.get("files") or []
            if not files:
                rows.append(base)
            for file in files:
                fileLabels = [(label, name) for pattern, labels in (result.get("labels") or {}).items()
                              if fnmatch.fnmatch(Path(file).name, pattern)
                              for label, name in labels.items()]
                if not fileLabels:
                    rows.append({**base, "file": file})
                for label, name in fileLabels:
                    rows.append({**base, "file": file, "label": label, "structure": name})

    path = Path(analysisDir) / SUMMARY_NAME
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


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


#============================================
# Provenance
#============================================
def modelFileProvenance(modelFile):
    """Model-tab provenance: the hash of the dosimetric model file."""
    return {"model_file_sha256": _fileSha256(modelFile)}


def aiModelProvenance(aiModel, installDir, weightsSha256=None):
    """Provenance of one AI model install: its number, name, install folder,
    code commit (and whether it has uncommitted changes), and hashes of its
    models.yaml and weights. weightsSha256 comes from the install record, since
    hashing the weights on every run is slow."""
    from cerr.ai_models import install_utils, model_list
    modelNum, _ = model_list.resolveModel(aiModel)
    modelName, repo, _ = install_utils.getModel(aiModel)
    repoPath = install_utils.getRepoPath(repo, installDir)
    modelsYaml = repoPath / "models.yaml"
    return {
        "number": modelNum,
        "name": modelName,
        "install_dir": str(installDir),
        "repo_commit": _git(repoPath, "rev-parse", "HEAD"),
        "repo_user_modified": _userModified(repoPath),
        "models_yaml_sha256": _fileSha256(modelsYaml) if modelsYaml.is_file() else None,
        "weights_sha256": weightsSha256,
    }


def _provenance():
    """Software provenance: validate's and pyCERR's git commits (and whether
    either has uncommitted changes) and the Python version."""
    import cerr
    validateDir = Path(__file__).resolve().parent
    pycerrDir = Path(cerr.__file__).resolve().parent.parent
    return {
        "validate_commit": _git(validateDir, "rev-parse", "HEAD"),
        "validate_user_modified": _userModified(validateDir),
        "pycerr_commit": _git(pycerrDir, "rev-parse", "HEAD"),
        "pycerr_user_modified": _userModified(pycerrDir),
        "python": platform.python_version(),
    }


def _userModified(repoDir):
    """True if repoDir's git checkout has uncommitted changes to tracked files,
    None if it isn't a git checkout."""
    if _git(repoDir, "rev-parse", "HEAD") is None:
        return None
    return bool(_git(repoDir, "status", "--porcelain", "--untracked-files=no"))


def _fileSha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
