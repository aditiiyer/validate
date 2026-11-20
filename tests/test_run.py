"""Tests 26 and 28 (reworked): running the AI models, then deriving structures and
computing NTCP (run.py).

pyCERR's loaders, the AI model, its import and export, and the dosimetric model are
replaced with stand-ins, so no image data, install or GPU is needed.
"""

import copy
import json
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from validate import logs, run
from validate.core.data_capsule import DataCapsule, FileInfo, PatientRecord
from validate.seg import structures
from validate.seg.structures import StructureDerivation

from conftest import RAW_SETTINGS, writeYaml

AI_MODEL = "CT_HeadAndNeck_OARs"
LABELS = {"*_seg.*": {1: "Left parotid", 2: "Oral cavity"}}


def _struct(name, fileName=""):
    return SimpleNamespace(structureName=name, structureFileName=fileName)


def _names(planC):
    return [s.structureName for s in planC.structure]


def _readTaskLog(analysisDir):
    return yaml.safe_load((analysisDir / logs.TASK_LOG_NAME).read_text())


def _errorLines(errorLog):
    errorLog.close()
    return Path(errorLog.path).read_text().splitlines()


def _provenance(name, installDir, weightsSha256=None):
    return {"number": 3, "name": name, "install_dir": str(installDir), "repo_commit": "abc",
            "repo_user_modified": False, "models_yaml_sha256": "def", "weights_sha256": weightsSha256}


# 28. applyAutoSegToCohort: runs the AI models only

@pytest.fixture
def segment(analysisDir, monkeypatch):
    """Two patients and one AI model. The stand-in AI model writes <pt>_seg.nii.gz,
    unless told to fail for a patient. Returns the calls made, in order."""
    calls = []
    failFor = {}

    def runAIModel(modelNum, record, sessionDir, progressCallback=None, outputDir=None, device=None):
        calls.append(("ai", modelNum, record.pt_id))
        if record.pt_id in failFor:
            raise failFor[record.pt_id]
        (Path(outputDir) / f"{record.pt_id}_seg.nii.gz").write_bytes(b"mask")

    patients = {ptId: PatientRecord(pt_id=ptId, file_info=FileInfo(data_dir=f"/data/{ptId}"))
                for ptId in ("pt1", "pt2")}
    capsule = DataCapsule(start_from="dicom", model={"name": "Test model", "file": None},
                          ai_models=[AI_MODEL], ai_install_dir="/models", patients=patients)
    monkeypatch.setattr(run, "buildCapsule", lambda path, errorLog=None: capsule)
    monkeypatch.setattr(run.model_registry, "useInstall", lambda num, name, installDir: None)
    monkeypatch.setattr(run.model_registry, "getWeightsHash", lambda num: "w123")
    monkeypatch.setattr(run.logs, "aiModelProvenance", _provenance)
    monkeypatch.setattr(run, "runAIModel", runAIModel)
    monkeypatch.setattr(run.run_utils, "readLabels", lambda outDir, model, installDir: LABELS)
    return SimpleNamespace(dir=analysisDir, calls=calls, failFor=failFor, capsule=capsule)


def _segment(segment, **kwargs):
    errorLog = logs.ErrorLog(segment.dir)
    results = run.applyAutoSegToCohort(str(segment.dir), errorLog, **kwargs)
    return results, _errorLines(errorLog)


def test_segmentRecordsOutputs(segment):
    results, errors = _segment(segment)

    assert results == {"pt1": {AI_MODEL: "ok"}, "pt2": {AI_MODEL: "ok"}}
    assert errors == []
    assert segment.calls == [("ai", 3, "pt1"), ("ai", 3, "pt2")]
    taskLog = _readTaskLog(segment.dir)
    assert taskLog["patients"]["pt1"]["segment"][AI_MODEL] == {
        "status": "ok", "files": ["pt1/pt1_seg.nii.gz"], "labels": LABELS, "run": 0}
    run_ = taskLog["runs"][0]
    assert run_["tab"] == "segment"
    assert run_["provenance"]["ai_models"] == [_provenance(AI_MODEL, "/models", "w123")]
    assert run_["finished"] is not None


def test_onlyNewFilesRecorded(segment):
    (segment.dir / "pt1").mkdir()
    (segment.dir / "pt1" / "notes.txt").write_text("already here")
    _segment(segment)
    assert _readTaskLog(segment.dir)["patients"]["pt1"]["segment"][AI_MODEL]["files"] == ["pt1/pt1_seg.nii.gz"]


def test_segmentedPatientsSkipped(segment):
    _segment(segment)
    segment.calls.clear()
    results, _ = _segment(segment)

    assert segment.calls == []
    assert results == {"pt1": {AI_MODEL: "ok (cached)"}, "pt2": {AI_MODEL: "ok (cached)"}}
    # Skipped results keep pointing at the run that made them
    assert _readTaskLog(segment.dir)["patients"]["pt1"]["segment"][AI_MODEL]["run"] == 0


def test_deletedOutputsRunAgain(segment):
    _segment(segment)
    (segment.dir / "pt2" / "pt2_seg.nii.gz").unlink()
    segment.calls.clear()
    results, _ = _segment(segment)

    assert segment.calls == [("ai", 3, "pt2")]
    assert results["pt2"] == {AI_MODEL: "ok"}


def test_overwriteRunsAgain(segment):
    _segment(segment)
    segment.calls.clear()
    results, _ = _segment(segment, overwrite=True)

    assert segment.calls == [("ai", 3, "pt1"), ("ai", 3, "pt2")]
    assert results == {"pt1": {AI_MODEL: "ok"}, "pt2": {AI_MODEL: "ok"}}
    assert _readTaskLog(segment.dir)["patients"]["pt1"]["segment"][AI_MODEL]["files"] == ["pt1/pt1_seg.nii.gz"]


def test_failedPatientDoesNotStopOthers(segment):
    segment.failFor["pt1"] = RuntimeError("GPU out of memory")
    results, errors = _segment(segment)

    assert results == {"pt1": {AI_MODEL: "error: GPU out of memory"}, "pt2": {AI_MODEL: "ok"}}
    assert errors == [f"[ERROR] pt1: {AI_MODEL}: GPU out of memory"]
    result = _readTaskLog(segment.dir)["patients"]["pt1"]["segment"][AI_MODEL]
    assert result == {"status": "error", "message": "GPU out of memory", "run": 0}


def test_abortedPatientRecordedAndRunStops(segment, monkeypatch):
    aborted = []

    def killedAIModel(*args, **kwargs):
        aborted.append(True)        # the abort kills the AI model's process
        raise RuntimeError("Model inference failed. STDERR: (killed)")

    monkeypatch.setattr(run, "runAIModel", killedAIModel)
    results, errors = _segment(segment, shouldStop=lambda: bool(aborted), isAborted=lambda: bool(aborted))

    assert results == {"pt1": {AI_MODEL: f"error: {run.ABORTED_MESSAGE}"}}
    assert errors == [f"[ERROR] pt1: {AI_MODEL}: {run.ABORTED_MESSAGE}"]
    taskLog = _readTaskLog(segment.dir)
    assert taskLog["patients"] == {"pt1": {"segment": {AI_MODEL: {
        "status": "error", "message": run.ABORTED_MESSAGE, "run": 0}}}}
    assert taskLog["runs"][0]["finished"] is not None


def test_noOutputFilesIsAnError(segment, monkeypatch):
    monkeypatch.setattr(run, "runAIModel", lambda *args, **kwargs: None)
    results, errors = _segment(segment)
    assert results["pt1"] == {AI_MODEL: f"error: {AI_MODEL} wrote no output files."}
    assert len(errors) == 2


def test_missingLabelsWarn(segment, monkeypatch):
    def noLabels(outDir, model, installDir):
        raise FileNotFoundError("No labels.json")
    monkeypatch.setattr(run.run_utils, "readLabels", noLabels)
    results, _ = _segment(segment)

    assert results["pt1"] == {AI_MODEL: "ok"}
    result = _readTaskLog(segment.dir)["patients"]["pt1"]["segment"][AI_MODEL]
    assert result["labels"] is None
    assert result["warnings"] == [f"Could not read {AI_MODEL}'s output labels: No labels.json"]


def test_stopBetweenPatients(segment):
    results, _ = _segment(segment, shouldStop=lambda: "pt1" in {c[2] for c in segment.calls})
    assert list(results) == ["pt1"]
    assert _readTaskLog(segment.dir)["runs"][0]["finished"] is not None


def test_modelNotInstalledStopsSetup(segment, monkeypatch):
    def notInstalled(num, name, installDir):
        raise RuntimeError(f"{name} is not installed in {installDir}")
    monkeypatch.setattr(run.model_registry, "useInstall", notInstalled)
    errorLog = logs.ErrorLog(segment.dir)
    with pytest.raises(RuntimeError, match="is not installed"):
        run.applyAutoSegToCohort(str(segment.dir), errorLog)
    assert _errorLines(errorLog) == [f"[ERROR] (setup): {AI_MODEL} is not installed in /models"]


# 26 (reworked). applyModelToCohort: derive structures, then NTCP

@pytest.fixture
def model(tmp_path, analysisDir, monkeypatch):
    """One DICOM patient, a model needing Parotids (existing) and Oral cavity
    (derived from the AI model's outputs), with Segment already run.

    Returns the calls made to the stand-ins, and the model dict NTCP was computed with."""
    calls = []
    seen = {}
    dataDir = tmp_path / "data" / "pt1"
    dataDir.mkdir(parents=True)
    (dataDir / "CT1.dcm").write_bytes(b"\0" * 128 + b"DICM")
    (analysisDir / "model.json").write_text(json.dumps({
        "function": "logitFn",
        "parameters": {"structures": {"Parotids": {"meanDose": {"weight": 1}},
                                      "Oral cavity": {"meanDose": {"weight": 1}}},
                       "concurrentChemo": {"val": 0, "weight": 1}}}))

    settings = copy.deepcopy(RAW_SETTINGS)
    settings["input"]["data_dir"] = str(tmp_path / "data")
    settings["model"]["file"] = str(analysisDir / "model.json")
    settings["segment"] = {"ai_models": [AI_MODEL], "install_dir": "/models"}
    settings["structures"] = {"Parotids": {"source": "existing", "name": "Parotid_Total"},
                              "Oral cavity": {"source": "derive"}}
    writeYaml(analysisDir / "analysis.yaml", settings)

    # Segment already ran for pt1
    taskLog, runIndex = logs.startRun(analysisDir, analysisDir / "analysis.yaml", "segment",
                                      details={"ai_models": [_provenance(AI_MODEL, "/models", "w123")]})
    (analysisDir / "pt1").mkdir()
    (analysisDir / "pt1" / "pt1_seg.nii.gz").write_bytes(b"mask")
    logs.recordResult(analysisDir, taskLog, runIndex, "pt1", "segment",
                      {"status": "ok", "files": ["pt1/pt1_seg.nii.gz"], "labels": LABELS}, key=AI_MODEL)

    def derive(name):
        def deriveFn(planC, scanNum):
            calls.append(("derive", name))
            planC.structure.append(_struct(name))
            return len(planC.structure) - 1, planC
        return deriveFn

    def importSeg(aiModel, installDir, outputPath, scanNum, planC):
        calls.append(("import", aiModel, installDir))
        planC.structure.append(_struct("Left parotid", str(Path(outputPath) / "pt1_seg.nii.gz")))
        return planC

    def runModel(patientModel, doseNum, planC, fSizeIn=None, fNumIn=None):
        seen["model"] = patientModel
        seen["structures"] = _names(planC)
        return 0.5

    monkeypatch.setattr(structures, "STRUCTURE_REGISTRY", {
        "Oral cavity": StructureDerivation(deriveFn=derive("Oral cavity"), aiModelNum=3,
                                           aiModelName=AI_MODEL, type="AI"),
        "SCRR": StructureDerivation(deriveFn=derive("SCRR"), type="classic"),
    })
    monkeypatch.setattr(run, "loadPatientPlanC", lambda record: SimpleNamespace(
        structure=[_struct("Parotid_Total", str(dataDir / "RS.dcm"))],
        dose=[SimpleNamespace(assocScanUID="uid", doseFileName="RD.dcm")]))
    monkeypatch.setattr(run.cerrScan, "getScanNumFromUID", lambda uid, planC: 0)
    monkeypatch.setattr(run.logs, "aiModelProvenance", _provenance)
    monkeypatch.setattr(run.run_utils, "importSeg", importSeg)
    def exportStructure(planC, structNum, record, outDir, structName):
        calls.append(("export", structName))
        return str(outDir / f"pt1_{structName}_autoseg.nii.gz")

    monkeypatch.setattr(run, "_exportStructure", exportStructure)
    monkeypatch.setattr(run.doseModels, "run", runModel)
    return SimpleNamespace(dir=analysisDir, calls=calls, seen=seen, settings=settings, dataDir=dataDir)


def _model(model, **kwargs):
    errorLog = logs.ErrorLog(model.dir)
    resultsDf = run.applyModelToCohort(str(model.dir), errorLog, **kwargs)
    return resultsDf, _errorLines(errorLog)


def _saveSettings(model):
    writeYaml(model.dir / "analysis.yaml", model.settings)


def test_derivedFromAIOutputsThenNTCP(model):
    resultsDf, errors = _model(model)

    assert errors == []
    assert resultsDf.to_dict("records") == [{"patient_id": "pt1", "ntcp": 0.5, "status": "ok", "message": ""}]
    assert model.calls == [("import", AI_MODEL, "/models"), ("derive", "Oral cavity"), ("export", "Oral cavity")]
    # The existing structure is used by its name in the data
    assert set(model.seen["model"]["parameters"]["structures"]) == {"Parotid_Total", "Oral cavity"}
    taskLog = _readTaskLog(model.dir)
    assert taskLog["patients"]["pt1"]["ntcp"] == {"status": "ok", "value": 0.5, "run": 1}
    assert taskLog["patients"]["pt1"]["segment"]["derived"] == {
        "status": "ok", "files": {"Oral cavity": "pt1/pt1_Oral cavity_autoseg.nii.gz"}, "run": 1}
    assert taskLog["runs"][1]["tab"] == "model"


def test_deriveOnlySkipsNTCP(model):
    errorLog = logs.ErrorLog(model.dir)
    resultsDf = run.deriveStructuresForCohort(str(model.dir), errorLog)

    assert _errorLines(errorLog) == []
    assert resultsDf.to_dict("records") == [{"patient_id": "pt1", "status": "ok", "message": ""}]
    assert model.calls == [("import", AI_MODEL, "/models"), ("derive", "Oral cavity"), ("export", "Oral cavity")]
    assert "model" not in model.seen       # NTCP not computed
    patient = _readTaskLog(model.dir)["patients"]["pt1"]
    assert "ntcp" not in patient
    assert patient["segment"]["derived"] == {
        "status": "ok", "files": {"Oral cavity": "pt1/pt1_Oral cavity_autoseg.nii.gz"}, "run": 1}


def test_classicRecipesDerivedFirst(model):
    model.settings["structures"]["Oral cavity"] = {"source": "derive"}
    model.settings["structures"]["SCRR"] = {"source": "derive"}
    modelJson = json.loads((model.dir / "model.json").read_text())
    modelJson["parameters"]["structures"]["SCRR"] = {"meanDose": {"weight": 1}}
    (model.dir / "model.json").write_text(json.dumps(modelJson))
    _saveSettings(model)
    _model(model)

    derived = [call[1] for call in model.calls if call[0] == "derive"]
    assert derived == ["SCRR", "Oral cavity"]


def test_noRecipeStopsSetup(model):
    model.settings["structures"]["Parotids"] = {"source": "derive"}
    _saveSettings(model)
    errorLog = logs.ErrorLog(model.dir)
    with pytest.raises(ValueError, match="No recipe registered to derive: Parotids"):
        run.applyModelToCohort(str(model.dir), errorLog)
    assert _errorLines(errorLog)[0].startswith("[ERROR] (setup): No recipe registered to derive: Parotids")
    # The run never started
    assert [r["tab"] for r in _readTaskLog(model.dir)["runs"]] == ["segment"]


def test_segmentNotRun(model):
    (model.dir / "pt1" / "pt1_seg.nii.gz").unlink()
    resultsDf, errors = _model(model)

    assert resultsDf["status"].tolist() == ["error"]
    assert f"run Segment for {AI_MODEL} first" in resultsDf["message"][0]
    assert errors[0].startswith("[ERROR] pt1: NTCP: No CT_HeadAndNeck_OARs outputs")


@pytest.mark.parametrize("key", ["repo_commit", "models_yaml_sha256"])
def test_changedAIModelRefused(model, monkeypatch, key):
    def changed(name, installDir, weightsSha256=None):
        return {**_provenance(name, installDir), key: "changed"}
    monkeypatch.setattr(run.logs, "aiModelProvenance", changed)
    resultsDf, _ = _model(model)

    assert resultsDf["status"].tolist() == ["error"]
    assert f"{AI_MODEL} has changed since its outputs were made ({key})" in resultsDf["message"][0]


def test_derivedStructureUsedOverDataCopy(model, monkeypatch):
    monkeypatch.setattr(run, "loadPatientPlanC", lambda record: SimpleNamespace(
        structure=[_struct("Parotid_Total"), _struct("oral cavity")],
        dose=[SimpleNamespace(assocScanUID="uid", doseFileName="RD.dcm")]))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resultsDf, _ = _model(model)

    assert resultsDf["status"].tolist() == ["ok"]
    assert model.seen["structures"] == ["Parotid_Total", "Left parotid", "Oral cavity"]
    taskLog = _readTaskLog(model.dir)
    assert taskLog["patients"]["pt1"]["ntcp"]["warnings"] == [
        "Using validate's 'oral cavity' instead of the one in the patient's data."]


def test_existingStructureKeptOverAIOutput(model, monkeypatch):
    # The settings' existing structure has the same name as an AI output
    model.settings["structures"]["Parotids"] = {"source": "existing", "name": "Left parotid"}
    _saveSettings(model)
    monkeypatch.setattr(run, "loadPatientPlanC", lambda record: SimpleNamespace(
        structure=[_struct("Left parotid", "/data/pt1/RS.dcm")],
        dose=[SimpleNamespace(assocScanUID="uid", doseFileName="RD.dcm")]))
    resultsDf, _ = _model(model)

    assert resultsDf["status"].tolist() == ["ok"]
    assert model.seen["structures"] == ["Left parotid", "Left parotid", "Oral cavity"]
    assert model.seen["structures"].count("Left parotid") == 2       # the data's copy is listed first


def test_validateOutputsInPatientFolderDropped(model, monkeypatch):
    exportFile = str(model.dir / "pt1" / "pt1_Oral cavity_autoseg.dcm")
    aiOutput = str(model.dir / "pt1" / "pt1_seg.nii.gz")
    monkeypatch.setattr(run, "loadPatientPlanC", lambda record: SimpleNamespace(
        structure=[_struct("Parotid_Total", "/data/pt1/RS.dcm"), _struct("Oral cavity", exportFile),
                   _struct("Left parotid", aiOutput)],
        dose=[SimpleNamespace(assocScanUID="uid", doseFileName="RD.dcm")]))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        resultsDf, _ = _model(model)

    assert resultsDf["status"].tolist() == ["ok"]
    assert model.seen["structures"] == ["Parotid_Total", "Left parotid", "Oral cavity"]


def test_noDoseIsAnError(model, monkeypatch):
    monkeypatch.setattr(run, "loadPatientPlanC", lambda record: SimpleNamespace(
        structure=[_struct("Parotid_Total")], dose=[]))
    resultsDf, _ = _model(model)
    assert resultsDf["message"].tolist() == ["No dose found in plan."]


def test_patientPredictorsFromCsv(model, tmp_path):
    predictorsCsv = tmp_path / "predictors.csv"
    predictorsCsv.write_text("ID,concurrentChemo\npt1,1\n")
    model.settings["input"]["predictors_csv"] = str(predictorsCsv)
    _saveSettings(model)
    _model(model)
    assert model.seen["model"]["parameters"]["concurrentChemo"]["val"] == 1.0


def test_allExistingNeedsNoSegment(model):
    model.settings["structures"]["Oral cavity"] = {"source": "existing", "name": "OralCavity"}
    model.settings["segment"] = {"ai_models": [], "install_dir": None}
    _saveSettings(model)
    (model.dir / "pt1" / "pt1_seg.nii.gz").unlink()
    resultsDf, _ = _model(model)

    assert model.calls == []
    assert resultsDf["message"].tolist() == ["Missing structure(s): OralCavity. Available: Parotid_Total."]


def test_modelStopBetweenPatients(model):
    resultsDf, _ = _model(model, shouldStop=lambda: True)
    assert resultsDf.empty
    assert _readTaskLog(model.dir)["runs"][1]["finished"] is not None


# listReqdAISegModels: what the Segment tab lists

def test_aiModelsForModel(model):
    assert structures.listReqdAISegModels(str(model.dir / "model.json")) == [AI_MODEL]


def test_segmentProgress(segment):
    progress = []
    _segment(segment, progressCallback=lambda done, total, pt: progress.append((done, total, pt)))
    assert progress == [(0, 2, None), (1, 2, "pt1"), (2, 2, "pt2")]
