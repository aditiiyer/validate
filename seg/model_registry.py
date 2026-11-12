"""Maintain a log of installed cerr.ai_models models to avoid re-installing.

Each entry also holds the SHA-256 of the model's weights, with the weights'
size and modification time when hashed, so the hash is only recomputed when
the weights change (see getWeightsHash).
"""

import hashlib

import yaml
from datetime import datetime, timezone
from pathlib import Path

from cerr.ai_models import install_utils

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "ai_model_installs.yaml"


def readRegistry():
    """
    Reads and returns the record of installed models.
    """
    if not REGISTRY_PATH.exists():
        return {}
    with open(REGISTRY_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def getInstallInfo(modelNum):
    """Return (installStatus, record).
    The record contains {"modelName", "installDir", "installDate"} for modelNum if available or None if not recorded,
    or recorded but the model's weights are no longer installed (checked with pyCERR: weights in
    <installDir>/<repo>/weights/, see install_utils.listInstalledWeights).
    """
    entry = readRegistry().get(str(modelNum))
    if entry is not None:
        modelName, repo, _ = install_utils.getModel(modelNum)
        repoPath = install_utils.getRepoPath(repo, entry["installDir"])
        if not (repoPath / "models.yaml").is_file() \
                or install_utils.listInstalledWeights(repoPath).get(modelName) is None:
            entry = None
    status = entry is not None
    return status, entry


def recordInstall(modelNum, modelName, installDir):
    """
    Records the installation of a new model, with the hash of its weights
    (None if its weights aren't installed).
    """
    registry = readRegistry()
    entry = {
        "modelName": modelName,
        "installDir": str(installDir),
        "installDate": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    } #Note: Over-writes if re-installed
    entry.update(_weightsRecord(modelNum, installDir))
    registry[str(modelNum)] = entry
    _writeRegistry(registry)
    return 0


def installStatus(modelNum, installDir):
    """Install status of a model in installDir (pyCERR's layout): "installed",
    "no weights" (its code is there but its weights aren't) or "not installed"."""
    if not installDir:
        return "not installed"
    modelName, repo, _ = install_utils.getModel(modelNum)
    repoPath = install_utils.getRepoPath(repo, installDir)
    if not (repoPath / "models.yaml").is_file():
        return "not installed"
    return "installed" if install_utils.listInstalledWeights(repoPath).get(modelName) else "no weights"


def useInstall(modelNum, modelName, installDir):
    """Make installDir the recorded install of modelNum, recording it (and
    hashing its weights) if it isn't already.

    Raises:
        RuntimeError: the model's weights aren't installed in installDir.
    """
    if _weightsPath(modelNum, installDir) is None:
        raise RuntimeError(f"{modelName} is not installed in {installDir}; install it from the Segment tab.")
    entry = readRegistry().get(str(modelNum))
    if entry is None or Path(entry["installDir"]).resolve() != Path(installDir).resolve():
        recordInstall(modelNum, modelName, installDir)


def getWeightsHash(modelNum):
    """SHA-256 of an installed model's weights, or None if the model isn't
    recorded or its weights aren't installed.

    The hash stored at install time is reused while the weights' size and
    modification time are unchanged; otherwise the weights are hashed again
    and the record updated.
    """
    registry = readRegistry()
    entry = registry.get(str(modelNum))
    if entry is None:
        return None
    weightsPath = _weightsPath(modelNum, entry["installDir"])
    if weightsPath is None:
        return None
    if entry.get("weightsSha256") and entry.get("weightsStamp") == _weightsStamp(weightsPath):
        return entry["weightsSha256"]
    entry.update(_weightsRecord(modelNum, entry["installDir"]))
    _writeRegistry(registry)
    return entry["weightsSha256"]


def _writeRegistry(registry):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary file and rename, so a crash never leaves a partial registry
    tmpPath = REGISTRY_PATH.with_name(REGISTRY_PATH.name + ".tmp")
    with open(tmpPath, "w") as f:
        yaml.safe_dump(registry, f, sort_keys=False)
    tmpPath.replace(REGISTRY_PATH)


def _weightsPath(modelNum, installDir):
    """The model's installed weights file or folder (pyCERR's layout), or None."""
    modelName, repo, _ = install_utils.getModel(modelNum)
    repoPath = install_utils.getRepoPath(repo, installDir)
    if not (repoPath / "models.yaml").is_file():
        return None
    return install_utils.listInstalledWeights(repoPath).get(modelName)


def _weightsRecord(modelNum, installDir):
    """{"weightsSha256", "weightsStamp"} for the model's installed weights (None if not installed)."""
    weightsPath = _weightsPath(modelNum, installDir)
    if weightsPath is None:
        return {"weightsSha256": None, "weightsStamp": None}
    return {"weightsSha256": _hashWeights(weightsPath), "weightsStamp": _weightsStamp(weightsPath)}


def _weightFiles(weightsPath):
    """(relative name, path) of each weights file: the file itself, or every file
    in a weights folder, in a fixed order."""
    weightsPath = Path(weightsPath)
    if weightsPath.is_file():
        return [(weightsPath.name, weightsPath)]
    return [(f.relative_to(weightsPath).as_posix(), f) for f in sorted(weightsPath.rglob("*")) if f.is_file()]


def _weightsStamp(weightsPath):
    """Total size and latest modification time of the weights files."""
    files = [path.stat() for _, path in _weightFiles(weightsPath)]
    return {"size": sum(st.st_size for st in files), "mtime": max((st.st_mtime for st in files), default=0)}


def _hashWeights(weightsPath):
    """SHA-256 over the weights files' names and contents."""
    digest = hashlib.sha256()
    for name, path in _weightFiles(weightsPath):
        digest.update(name.encode("utf-8") + b"\0")
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


def getDefaultInstallDir():
    """Last-used install base directory, or None if nothing installed yet."""
    registry = readRegistry()
    if not registry:
        return None
    latest = max(registry.values(), key=lambda e: e["installDate"])
    return latest["installDir"]
