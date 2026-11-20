"""Aborting an install or run: killing validate's child processes, stopping between
AI model installs, and deleting unfinished weights downloads."""

import subprocess
import sys
import time

import psutil

from validate.gui.worker import killChildProcesses
from validate.seg import autoseg_pipeline


def _waitFor(condition, timeout=10):
    """Poll until condition() is true (returning its value), or fail after timeout s."""
    deadline = time.monotonic() + timeout
    while not (value := condition()):
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)
    return value


def _running(pid):
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_killChildProcesses():
    # A child that starts its own child, like uv starting the model's Python
    proc = subprocess.Popen([sys.executable, "-c",
                             "import subprocess, sys, time; "
                             "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
                             "time.sleep(60)"])
    grandchild = _waitFor(lambda: psutil.Process(proc.pid).children())[0]

    killChildProcesses()

    assert proc.wait(timeout=10) is not None
    assert _waitFor(lambda: not _running(grandchild.pid))


def test_installStopsBetweenModels(monkeypatch):
    installed = []
    monkeypatch.setattr(autoseg_pipeline.model_registry, "getInstallInfo", lambda num: (False, None))
    monkeypatch.setattr(autoseg_pipeline.model_registry, "recordInstall", lambda *args: None)
    monkeypatch.setattr(autoseg_pipeline.model_list, "resolveModel", lambda num: (num, {"name": f"m{num}"}))
    monkeypatch.setattr(autoseg_pipeline.install_utils, "main", lambda num, installDir, **kw: installed.append(num))

    results = autoseg_pipeline.installMissingModels([3, 7], "/models", shouldStop=lambda: bool(installed))

    assert installed == [3]
    assert results == [(3, True, "")]


def test_removePartialDownloads(tmp_path, monkeypatch):
    weightsDir = tmp_path / "smit" / "weights"
    (weightsDir / ".get_weights_abc").mkdir(parents=True)
    (weightsDir / ".get_weights_abc" / "download").write_bytes(b"partial")
    (weightsDir / "CT_HN_SMIT.safetensors").write_bytes(b"complete")
    monkeypatch.setattr(autoseg_pipeline.install_utils, "getModel", lambda num: ("CT_HN_SMIT", "smit", None))
    monkeypatch.setattr(autoseg_pipeline.install_utils, "getRepoPath", lambda repo, installDir: tmp_path / repo)

    removed = autoseg_pipeline.removePartialDownloads([7], str(tmp_path))

    assert removed == [str(weightsDir / ".get_weights_abc")]
    assert sorted(p.name for p in weightsDir.iterdir()) == ["CT_HN_SMIT.safetensors"]
