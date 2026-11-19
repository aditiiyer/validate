"""Test 16 and the task log helpers: starting runs, per-tab settings, results,
summary and provenance (logs.py)."""

import copy
import csv
import re

import pytest
import yaml

from validate import logs

from conftest import RAW_SETTINGS, writeYaml


def _startRun(analysisDir, tab="model", errorLogPath=None, details=None):
    return logs.startRun(analysisDir, analysisDir / "analysis.yaml", tab,
                         errorLogPath=errorLogPath, details=details)


def _readTaskLog(analysisDir):
    with open(analysisDir / logs.TASK_LOG_NAME) as f:
        return yaml.safe_load(f)


def _changeSettings(analysisDir, key, value):
    settings = copy.deepcopy(RAW_SETTINGS)
    section, name = key.split(".")
    settings[section][name] = value
    writeYaml(analysisDir / "analysis.yaml", settings)


# 16. Starting and resuming task_log.yaml

def test_newTaskLogCreated(analysisDir):
    errorLogPath = analysisDir / logs.LOG_DIR_NAME / "error_log_20260101_000000.txt"
    taskLog, runIndex = _startRun(analysisDir, "model", errorLogPath,
                                  details=logs.modelFileProvenance(analysisDir / "model.json"))

    assert runIndex == 0
    assert taskLog == _readTaskLog(analysisDir)
    assert taskLog["settings_hash"] == {
        "segment": None, "model": logs.settingsHashes(analysisDir / "analysis.yaml")["model"]}
    assert taskLog["patients"] == {}
    run = taskLog["runs"][0]
    assert run["tab"] == "model"
    assert run["finished"] is None
    assert run["device"] == "cpu"
    assert run["provenance_id"]
    assert run["provenance"]["model_file_sha256"]
    assert run["error_log"] == f"{logs.LOG_DIR_NAME}/error_log_20260101_000000.txt"


def test_sameSettingsResume(analysisDir):
    _startRun(analysisDir)
    # Comments, key order and formatting don't count as different settings
    reordered = dict(reversed(list(RAW_SETTINGS.items())))
    (analysisDir / "analysis.yaml").write_text("# my analysis\n" + yaml.safe_dump(reordered, indent=4))
    taskLog, runIndex = _startRun(analysisDir)

    assert runIndex == 1
    assert len(_readTaskLog(analysisDir)["runs"]) == 2


@pytest.mark.parametrize("key, value, refusedTab, allowedTab", [
    ("input.predictors_csv", "/data/predictors.csv", "model", "segment"),
    ("compute.device", "gpu", "segment", "model"),
])
def test_onlyChangedTabRefused(analysisDir, key, value, refusedTab, allowedTab):
    _startRun(analysisDir, "segment")
    _startRun(analysisDir, "model")
    _changeSettings(analysisDir, key, value)

    with pytest.raises(logs.SettingsChangedError, match=f"The {refusedTab} settings changed") as excInfo:
        _startRun(analysisDir, refusedTab)
    assert excInfo.value.tab == refusedTab
    _, runIndex = _startRun(analysisDir, allowedTab)
    assert runIndex == 2


def test_dataChangeRefusesBothTabs(analysisDir):
    _startRun(analysisDir, "segment")
    _startRun(analysisDir, "model")
    _changeSettings(analysisDir, "input.data_dir", "/data/other")
    for tab in logs.TABS:
        with pytest.raises(logs.SettingsChangedError):
            _startRun(analysisDir, tab)


def test_firstRunOfTabAcceptsCurrentSettings(analysisDir):
    _startRun(analysisDir, "model")
    _changeSettings(analysisDir, "compute.device", "gpu")
    _, runIndex = _startRun(analysisDir, "segment")      # segment hasn't run yet
    assert runIndex == 1


@pytest.mark.parametrize("content, message", [
    ("", "is empty or isn't a validate task log"),
    ("just some text\n", "is empty or isn't a validate task log"),
    ("settings_hash: abc\n", "is empty or isn't a validate task log"),
    ("runs: [unclosed\n", "can't be read as YAML"),
    ("settings_hash: abc\nruns: []\npatients: {}\n", "written by an earlier version of validate"),
], ids=["empty", "not a mapping", "missing keys", "invalid YAML", "earlier format"])
def test_damagedTaskLogRefused(analysisDir, content, message):
    (analysisDir / logs.TASK_LOG_NAME).write_text(content)
    with pytest.raises(ValueError, match=message):
        _startRun(analysisDir)
    # The damaged file is left as it was
    assert (analysisDir / logs.TASK_LOG_NAME).read_text() == content


# Results

def test_resultsRecordedWithRun(analysisDir):
    taskLog, runIndex = _startRun(analysisDir, "segment")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "segment",
                      {"status": "ok", "files": ["pt1/pt1_seg.nii.gz"]}, key="CT_HeadAndNeck_OARs",
                      warningMessages=["No dose plan given."])
    taskLog, runIndex = _startRun(analysisDir, "model")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "ntcp", {"status": "ok", "value": 0.5})

    assert _readTaskLog(analysisDir)["patients"]["pt1"] == {
        "segment": {"CT_HeadAndNeck_OARs": {"status": "ok", "files": ["pt1/pt1_seg.nii.gz"],
                                            "run": 0, "warnings": ["No dose plan given."]}},
        "ntcp": {"status": "ok", "value": 0.5, "run": 1},
    }


def test_otherAIModelResultsKept(analysisDir):
    taskLog, runIndex = _startRun(analysisDir, "segment")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "segment", {"status": "ok"}, key="ModelA")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "segment", {"status": "ok"}, key="ModelB")
    assert set(_readTaskLog(analysisDir)["patients"]["pt1"]["segment"]) == {"ModelA", "ModelB"}


def test_clearResultsOnlyClearsThatTab(analysisDir):
    taskLog, runIndex = _startRun(analysisDir, "segment")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "segment", {"status": "ok"}, key="ModelA")
    taskLog, runIndex = _startRun(analysisDir, "model")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "ntcp", {"status": "ok", "value": 0.5})
    logs.recordResult(analysisDir, taskLog, runIndex, "pt2", "ntcp", {"status": "ok", "value": 0.7})
    _changeSettings(analysisDir, "model.name", "Dysphagia")

    logs.clearResults(analysisDir, "model")
    taskLog = _readTaskLog(analysisDir)
    assert taskLog["patients"] == {"pt1": {"segment": {"ModelA": {"status": "ok", "run": 0}}}}
    assert taskLog["settings_hash"]["model"] is None
    assert taskLog["settings_hash"]["segment"] is not None
    assert len(taskLog["runs"]) == 2                     # run history is kept
    _, runIndex = _startRun(analysisDir, "model")        # the model tab can run again
    assert runIndex == 2


def test_clearResultsWithNoTaskLog(analysisDir):
    assert logs.clearResults(analysisDir, "model") is None


# isSegmented: done only if the run succeeded and its files are still there

def _segmentedLog(analysisDir, status="ok", files=("pt1/pt1_seg.nii.gz",)):
    taskLog, runIndex = _startRun(analysisDir, "segment")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "segment",
                      {"status": status, "files": list(files)}, key="ModelA")
    return taskLog


def test_segmentedWhenFilesExist(analysisDir):
    (analysisDir / "pt1").mkdir()
    (analysisDir / "pt1" / "pt1_seg.nii.gz").touch()
    assert logs.isSegmented(analysisDir, _segmentedLog(analysisDir), "pt1", "ModelA")


@pytest.mark.parametrize("status, files, makeFiles", [
    ("ok", ["pt1/pt1_seg.nii.gz"], False),
    ("error", ["pt1/pt1_seg.nii.gz"], True),
    ("ok", [], True),
], ids=["files deleted", "run failed", "no files recorded"])
def test_notSegmented(analysisDir, status, files, makeFiles):
    if makeFiles:
        (analysisDir / "pt1").mkdir()
        (analysisDir / "pt1" / "pt1_seg.nii.gz").touch()
    taskLog = _segmentedLog(analysisDir, status, files)
    assert not logs.isSegmented(analysisDir, taskLog, "pt1", "ModelA")


def test_notSegmentedForOtherPatientOrModel(analysisDir):
    (analysisDir / "pt1").mkdir()
    (analysisDir / "pt1" / "pt1_seg.nii.gz").touch()
    taskLog = _segmentedLog(analysisDir)
    assert not logs.isSegmented(analysisDir, taskLog, "pt2", "ModelA")
    assert not logs.isSegmented(analysisDir, taskLog, "pt1", "ModelB")
    assert not logs.isSegmented(analysisDir, None, "pt1", "ModelA")


# Generate summary

def test_generateSummary(analysisDir):
    taskLog, runIndex = _startRun(analysisDir, "segment")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "segment",
                      {"status": "ok", "files": ["pt1/pt1_seg.nii.gz", "pt1/pt1_extra.dcm"],
                       "labels": {"*_seg.*": {1: "Parotid_L", 2: "Parotid_R"}}}, key="ModelA")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt2", "segment",
                      {"status": "error", "message": "GPU out of memory"}, key="ModelA")
    path = logs.generateSummary(analysisDir)

    assert path == str(analysisDir / logs.SUMMARY_NAME)
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert [(r["patient_id"], r["file"], r["label"], r["structure"], r["status"]) for r in rows] == [
        ("pt1", "pt1/pt1_seg.nii.gz", "1", "Parotid_L", "ok"),
        ("pt1", "pt1/pt1_seg.nii.gz", "2", "Parotid_R", "ok"),
        ("pt1", "pt1/pt1_extra.dcm", "", "", "ok"),
        ("pt2", "", "", "", "error"),
    ]
    assert rows[3]["message"] == "GPU out of memory"
    assert all(r["ai_model"] == "ModelA" and r["run"] == "0" for r in rows)


def test_generateSummaryWithNoTaskLog(analysisDir):
    with pytest.raises(FileNotFoundError, match="run Segment first"):
        logs.generateSummary(analysisDir)


# Provenance

def test_softwareProvenanceRecordsCommits(analysisDir):
    taskLog, _ = _startRun(analysisDir)
    provenance = taskLog["runs"][0]["provenance"]
    assert "pycerr_version" not in provenance
    assert re.fullmatch(r"[0-9a-f]{40}", provenance["pycerr_commit"])
    assert isinstance(provenance["pycerr_user_modified"], bool)
    assert {"validate_commit", "validate_user_modified", "python"} <= provenance.keys()


def test_aiModelProvenance(tmp_path):
    from cerr.ai_models import install_utils
    modelName, repo, _ = install_utils.getModel("CT_HeadAndNeck_OARs")
    repoPath = tmp_path / "models" / repo
    repoPath.mkdir(parents=True)
    (repoPath / "models.yaml").write_text("models: {}\n")

    provenance = logs.aiModelProvenance("CT_HeadAndNeck_OARs", tmp_path / "models", weightsSha256="abc")
    assert provenance["number"] == 3
    assert provenance["name"] == modelName
    assert provenance["install_dir"] == str(tmp_path / "models")
    assert provenance["repo_commit"] is None             # not a git checkout
    assert provenance["repo_user_modified"] is None
    assert provenance["models_yaml_sha256"] == logs._fileSha256(repoPath / "models.yaml")
    assert provenance["weights_sha256"] == "abc"
