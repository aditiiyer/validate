"""Maintain a log of installed cerr.ai_models models to avoid re-installing.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "ai_model_installs.json"


def readRegistry():
    """
    Reads and returns the record of installed models.
    """
    if not REGISTRY_PATH.exists():
        return {}
    with open(REGISTRY_PATH, "r") as f:
        return json.load(f)


def getInstallInfo(modelNum):
    """Return (installStatus, record).
    The record contains {"modelName", "installDir", "installDate"} for modelNum if available or None if not recorded,
    or recorded but the installation directory no longer exists.
    """
    entry = readRegistry().get(str(modelNum))
    if entry is not None:
        modelDir = Path(entry["installDir"]) / entry["modelName"]
        if not modelDir.is_dir():
            entry = None
    status = entry is not None
    return status, entry


def recordInstall(modelNum, modelName, installDir):
    """
    Records the installation of a new model.
    """
    registry = readRegistry()
    registry[str(modelNum)] = {
        "modelName": modelName,
        "installDir": str(installDir),
        "installDate": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    } #Note: Over-writes if re-installed
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary file and rename, so a crash never leaves a partial registry
    tmpPath = REGISTRY_PATH.with_name(REGISTRY_PATH.name + ".tmp")
    with open(tmpPath, "w") as f:
        json.dump(registry, f, indent=2)
    tmpPath.replace(REGISTRY_PATH)
    return 0


def getDefaultInstallDir():
    """Last-used install base directory, or None if nothing installed yet."""
    registry = readRegistry()
    if not registry:
        return None
    latest = max(registry.values(), key=lambda e: e["installDate"])
    return latest["installDir"]
