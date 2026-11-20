"""The Device setting reaches the AI model (--device), and the task log records only
the GPU the model uses."""

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from validate import logs, run
from validate.core.data_capsule import DataCapsule, FileInfo, PatientRecord
from validate.seg import autoseg_pipeline

from conftest import RAW_SETTINGS, writeYaml

NVIDIA_SMI = ("0, GPU-aaa, NVIDIA GeForce RTX 2080 Ti\n"
              "1, GPU-bbb, NVIDIA GeForce RTX 2080 Ti\n"
              "2, GPU-ccc, NVIDIA GeForce RTX 2080 Ti")


@pytest.fixture
def aiModel(tmp_path, monkeypatch):
    """runAIModel with pyCERR replaced: returns the userInputs passed to run_utils.main.
    acceptsDevice says whether the model's script has a --device option."""
    calls = SimpleNamespace(userInputs=None, acceptsDevice=True)
    monkeypatch.setattr(autoseg_pipeline.model_registry, "getInstallInfo",
                        lambda num: (True, {"installDir": str(tmp_path), "modelName": "CT_HN_SMIT"}))
    monkeypatch.setattr(autoseg_pipeline.install_utils, "getModel",
                        lambda num: ("CT_HN_SMIT", "smit", "run_segmentation.py"))
    monkeypatch.setattr(autoseg_pipeline.install_utils, "getRepoPath", lambda repo, installDir: tmp_path / repo)
    monkeypatch.setattr(autoseg_pipeline.run_utils, "additionalInputs",
                        lambda entrypoint, option: calls.acceptsDevice and option == "--device")
    monkeypatch.setattr(autoseg_pipeline.run_utils, "main",
                        lambda num, installDir, userInputs: setattr(calls, "userInputs", userInputs))
    calls.record = PatientRecord(pt_id="pt1", file_info=FileInfo(data_dir=str(tmp_path)))
    calls.sessionDir = str(tmp_path / "session")
    return calls


@pytest.mark.parametrize("device, platform, expected", [
    ("gpu", "linux", "cuda"),
    ("gpu", "darwin", "mps"),
    ("cpu", "linux", "cpu"),
])
def test_devicePassedToModel(aiModel, monkeypatch, device, platform, expected):
    monkeypatch.setattr(autoseg_pipeline.sys, "platform", platform)
    autoseg_pipeline.runAIModel(7, aiModel.record, aiModel.sessionDir, device=device)
    assert aiModel.userInputs["device"] == expected


def test_deviceNotPassedIfModelHasNoOption(aiModel):
    aiModel.acceptsDevice = False
    autoseg_pipeline.runAIModel(3, aiModel.record, aiModel.sessionDir, device="gpu")
    assert "device" not in aiModel.userInputs


@pytest.mark.parametrize("device, env, expected", [
    ("gpu", {}, [{"index": 0, "uuid": "GPU-aaa", "name": "NVIDIA GeForce RTX 2080 Ti"}]),
    ("gpu", {"CUDA_VISIBLE_DEVICES": "2,1"}, [{"index": 2, "uuid": "GPU-ccc", "name": "NVIDIA GeForce RTX 2080 Ti"}]),
    ("gpu", {"CUDA_VISIBLE_DEVICES": "GPU-bbb"}, [{"index": 1, "uuid": "GPU-bbb", "name": "NVIDIA GeForce RTX 2080 Ti"}]),
    ("gpu", {"CUDA_VISIBLE_DEVICES": ""}, []),
    ("cpu", {}, []),
], ids=["default GPU 0", "first visible by index", "visible by UUID", "none visible", "CPU run"])
def test_onlyGpuUsedRecorded(monkeypatch, device, env, expected):
    monkeypatch.setattr(logs.sys, "platform", "linux")
    monkeypatch.setattr(logs, "_run", lambda cmd: NVIDIA_SMI)
    monkeypatch.setattr(logs.os, "environ", env)
    assert logs._gpusUsed(device) == expected


@pytest.mark.parametrize("device, tab, expectedGpus", [
    ("gpu", "segment", [{"index": 0, "uuid": "GPU-aaa", "name": "NVIDIA GeForce RTX 2080 Ti"}]),
    ("cpu", "segment", []),
    ("gpu", "model", []),
], ids=["Segment on GPU", "Segment on CPU", "Model run (no AI model)"])
def test_runRecordsDeviceAndGpuUsed(tmp_path, monkeypatch, device, tab, expectedGpus):
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["compute"]["device"] = device
    settingsPath = writeYaml(tmp_path / "analysis.yaml", settings)
    monkeypatch.setattr(logs.sys, "platform", "linux")
    monkeypatch.setattr(logs.os, "environ", {})
    monkeypatch.setattr(logs, "_run", lambda cmd: NVIDIA_SMI if cmd[0] == "nvidia-smi" else None)

    taskLog, runIndex = logs.startRun(tmp_path, settingsPath, tab)

    assert taskLog["runs"][runIndex]["device"] == device
    assert taskLog["runs"][runIndex]["hardware"]["gpus"] == expectedGpus


def test_deviceSettingReachesAIModel(tmp_path, monkeypatch):
    """Segment passes the settings' device to each AI model run."""
    devices = []
    record = PatientRecord(pt_id="pt1", file_info=FileInfo(data_dir=str(tmp_path)))
    capsule = DataCapsule(start_from="dicom", model={"name": "Test model", "file": None}, device="gpu",
                          ai_models=["CT_HN_SMIT"], ai_install_dir="/models", patients={"pt1": record})

    def runAIModel(modelNum, record, sessionDir, progressCallback=None, outputDir=None, device=None):
        devices.append(device)
        (Path(outputDir) / "pt1_seg.nii.gz").write_bytes(b"mask")

    writeYaml(tmp_path / "analysis.yaml", RAW_SETTINGS)
    monkeypatch.setattr(run, "buildCapsule", lambda path, errorLog=None: capsule)
    monkeypatch.setattr(run.model_registry, "useInstall", lambda num, name, installDir: None)
    monkeypatch.setattr(run.model_registry, "getWeightsHash", lambda num: None)
    monkeypatch.setattr(run.logs, "aiModelProvenance", lambda name, installDir, weights=None: {"name": name})
    monkeypatch.setattr(run, "runAIModel", runAIModel)
    monkeypatch.setattr(run.run_utils, "readLabels", lambda outDir, model, installDir: {})

    run.applyAutoSegToCohort(str(tmp_path), logs.ErrorLog(tmp_path))

    assert devices == ["gpu"]
