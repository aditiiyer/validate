"""Run an analysis on every patient in the cohort.

Segment tab: applyAutoSegToCohort runs the AI models in the settings and records their outputs.
Model tab: applyModelToCohort derives the structures the dosimetric model needs (from the AI
outputs or classic recipes), then computes NTCP.
"""

import os
import shutil
import warnings
from pathlib import Path

import pandas as pd

from cerr.roe import dosimetric_models as doseModels
from cerr.dcm_export import rtstruct_iod
import cerr.dataclasses.scan as cerrScan
from cerr.dataclasses.structure import getMatchingIndex
from cerr.ai_models import run_utils, model_list

from validate.data_io.read_inputs import (discoverPatients, loadPatientPlanC, getDoseIndex,
                                 loadPatientInfo, getFractionation)
from validate.seg.structures import applyStructureNameMap, getRequiredStructures
from validate.modeling.apply_model import getFractionCorrectionType, getFractionationInputs
from validate.seg import structures, model_registry
from validate.seg.autoseg_pipeline import runAIModel
from validate.data_io.build_capsule import buildCapsule, buildPatientRecord
from validate.core import analysis
from validate import logs

RESULT_COLUMNS = ["patient_id", "ntcp", "status", "message"]
AUTOSEG_SUFFIX = "_autoseg"

def applyAutoSegToCohort(analysisDir, errorLog, progressCallback=None, stageCallback=None, overwrite=False,
                         shouldStop=None):
    """Run the AI models in the settings (segment.ai_models) on every patient in the cohort.

    Each model's outputs are written to <analysisDir>/<patientId>/ and recorded in
    task_log.yaml under the patient's "segment" section: status, output files and
    labels. A model that already ran for a patient, with its output files still in
    place, is skipped unless overwrite=True. Structures are derived from the
    outputs later, by applyModelToCohort.

    Args:
        analysisDir (str): the analysis folder. Holds the settings file
            (analysis.FILE_NAME) used to build the DataCapsule, and receives
            logs, sessions and the AI outputs (<analysisDir>/<patientId>/).
        errorLog (validate.logs.ErrorLog): error log to write to.
        progressCallback (callable): optional f(done, total, patientId) hook,
            invoked after each patient is processed.
        stageCallback (callable): optional f(message) hook for the AI model's stages.
        overwrite (bool): if True, re-run models that already ran.
        shouldStop (callable): optional f() -> bool, checked before each patient;
            True stops the run there.

    Returns:
        dict: {patientId: {aiModel: "ok"|"ok (cached)"|"error: <message>"}}
    """
    settingsPath = os.path.join(analysisDir, analysis.FILE_NAME)
    with logs.collectWarnings() as capsuleWarnings:
        try:
            dataCapsule = buildCapsule(settingsPath, errorLog=errorLog)
            installDir = dataCapsule.ai_install_dir
            aiModels = [_useAIModel(name, installDir) for name in dataCapsule.ai_models]
            details = {"ai_models": [logs.aiModelProvenance(modelName, installDir,
                                                            model_registry.getWeightsHash(modelNum))
                                     for modelNum, modelName in aiModels]}
            taskLog, runIndex = logs.startRun(analysisDir, settingsPath, "segment",
                                              errorLogPath=errorLog.path, details=details)
        except Exception as exc:
            errorLog.error("(setup)", str(exc))
            raise
    logs.recordRunWarnings(analysisDir, taskLog, runIndex, capsuleWarnings)

    results = {}
    total = len(dataCapsule.patients)

    # Loop over pts
    for i, record in enumerate(dataCapsule.patients.values()):
        if shouldStop and shouldStop():
            break
        patientId = record.pt_id
        # AI outputs; the patient's own folder if analysisDir is the cohort folder
        outDir = Path(analysisDir) / patientId
        patientResult = {}
        for modelNum, modelName in aiModels:
            if not overwrite and logs.isSegmented(analysisDir, taskLog, patientId, modelName):
                patientResult[modelName] = "ok (cached)"
                continue
            sessionDir = Path(logs.logDir(analysisDir)) / "_sessions" / patientId / modelName
            with logs.collectWarnings() as modelWarnings:
                try:
                    outDir.mkdir(parents=True, exist_ok=True)
                    before = _fileStamps(outDir)
                    runAIModel(modelNum, record, str(sessionDir), stageCallback, outputDir=str(outDir))
                    # The model's outputs: files it added or rewrote in outDir
                    files = sorted(f for f, stamp in _fileStamps(outDir).items() if before.get(f) != stamp)
                    if not files:
                        raise RuntimeError(f"{modelName} wrote no output files.")
                    result = {"status": "ok",
                              "files": [os.path.relpath(outDir / f, analysisDir) for f in files],
                              "labels": _readLabels(modelName, installDir, outDir)}
                    patientResult[modelName] = "ok"
                except Exception as exc:
                    errorLog.error(patientId, f"{modelName}: {exc}")
                    result = {"status": "error", "message": str(exc)}
                    patientResult[modelName] = f"error: {exc}"
                finally:
                    shutil.rmtree(sessionDir, ignore_errors=True)
            logs.recordResult(analysisDir, taskLog, runIndex, patientId, "segment", result,
                              key=modelName, warningMessages=modelWarnings)

        results[patientId] = patientResult
        if progressCallback:
            progressCallback(i + 1, total, patientId)

    logs.finishRun(analysisDir, taskLog, runIndex)
    return results


def applyModelToCohort(analysisDir, errorLog, progressCallback=None, shouldStop=None):
    """Apply a dosimetric model to every patient dataset in the cohort.

    For raw data, each patient's structures are taken from the settings file:
    "existing" ones by their name in the data, "derive" ones made with their
    registered recipe (classic recipes first) from the outputs of the AI models
    Segment ran for that patient. Derived structures are exported to
    <analysisDir>/<patientId>/ for review, then NTCP is computed.

    Args:
        analysisDir (str): the analysis folder. Holds the settings file
            (analysis.FILE_NAME), which supplies the cohort directory, the
            dosimetric model, the structures and the CSV inputs.
        errorLog (validate.logs.ErrorLog): error log to write to.
        progressCallback (callable): optional f(done, total, patientId) hook,
            invoked after each patient is processed.
        shouldStop (callable): optional f() -> bool, checked before each patient;
            True stops the run there.

    Returns:
        pandas.DataFrame with columns: patient_id, ntcp, status, message.
        status is "ok" or "error"; message holds the exception text on error.
    """
    settingsPath = os.path.join(analysisDir, analysis.FILE_NAME)
    try:
        dataCapsule = analysis.toDataCapsule(settingsPath)
        # Load patient-specific clinical factors (selected predictors)
        predictorsDf = loadPatientInfo(dataCapsule.predictors_csv) if dataCapsule.predictors_csv else None

        # Identify if using only pre-computed predictors (incl. DVH metrics)
        fromPredictors = dataCapsule.start_from == "predictors"
        if fromPredictors:
            patients = [(ptId, None) for ptId in sorted(predictorsDf.index)]
        else:
            patients = discoverPatients(dataCapsule.cohort_dir)
        modelFile = dataCapsule.model["file"]

        # Required structure recipes and fractionation correction method
        planStructuresCsv = dataCapsule.plan_structures_csv
        patientInfoDf = loadPatientInfo(planStructuresCsv) if planStructuresCsv else None
        correctionType = getFractionCorrectionType(modelFile)
        requiredStructs = getRequiredStructures(modelFile)
        # Analysis-level recipes for the model's structures ("existing" ones may give a dataset name)
        recipes = {name: dataCapsule.structures.get(name) or {} for name in requiredStructs}
        deriveNames = _deriveOrder(name for name in requiredStructs if recipes[name].get("source") == "derive")

        taskLog, runIndex = logs.startRun(analysisDir, settingsPath, "model", errorLogPath=errorLog.path,
                                          details=logs.modelFileProvenance(modelFile))
    except Exception as exc:
        errorLog.error("(setup)", str(exc))
        raise

    total = len(patients)
    rows = []
    for i, (patientId, dataDir) in enumerate(patients):
        if shouldStop and shouldStop():
            break
        ntcp = None
        status = "ok"
        message = ""
        with logs.collectWarnings() as patientWarnings:
            try:
                if fromPredictors:
                    # Values are used as given (dose metrics must already be fractionation-corrected);
                    # blank cells are left out, so they're reported as missing predictors
                    record = buildPatientRecord(patientId, None, {}, predictorsRow=predictorsDf.loc[patientId])
                    predictors = {name: val for name, val in record.predictors.items() if val is not None}
                    ntcp = float(doseModels.runFromPredictors(modelFile, predictors))
                else:
                    patientInfo = _row(patientInfoDf, patientId)
                    record = buildPatientRecord(patientId, dataDir, recipes, planRow=patientInfo,
                                                predictorsRow=_row(predictorsDf, patientId))
                    planC = loadPatientPlanC(record)
                    planC = _dropValidateOutputs(planC, analysisDir, taskLog, patientId)
                    doseNum = getDoseIndex(planC, patientId=patientId, patientInfo=patientInfo)
                    if doseNum is None:
                        raise ValueError("No dose found in plan.")
                    if deriveNames:
                        scanNum = cerrScan.getScanNumFromUID(planC.dose[doseNum].assocScanUID, planC)
                        existingNames = [record.structures[name] for name in requiredStructs
                                         if recipes[name].get("source") == "existing"]
                        planC = _deriveStructures(planC, scanNum, deriveNames, existingNames, record,
                                                  analysisDir, taskLog)
                    patientModel = applyStructureNameMap(modelFile, _patientNameMap(record))
                    _setPatientPredictors(patientModel, record.predictors)
                    _checkStructuresPresent(planC, getRequiredStructures(patientModel))
                    fxSize, fxNum = getFractionation(patientInfo)
                    fSizeIn, fNumIn = getFractionationInputs(fxSize, fxNum, correctionType)
                    ntcp = float(doseModels.run(patientModel, doseNum, planC, fSizeIn=fSizeIn, fNumIn=fNumIn))
            except Exception as exc:
                status = "error"
                message = str(exc)
                errorLog.error(patientId, f"NTCP: {exc}")

        rows.append({"patient_id": patientId, "ntcp": ntcp,
                     "status": status, "message": message})
        ntcpResult = {"status": status, "value": ntcp} if status == "ok" else {"status": status, "message": message}
        logs.recordResult(analysisDir, taskLog, runIndex, patientId, "ntcp", ntcpResult,
                          warningMessages=patientWarnings)

        if progressCallback:
            progressCallback(i + 1, total, patientId)

    logs.finishRun(analysisDir, taskLog, runIndex)
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)

#===================================
# Helper functions
#====================================
def _useAIModel(aiModel, installDir):
    """(modelNum, modelName) for an AI model in the settings, after checking it is
    installed in installDir and making that its recorded install."""
    modelNum, entry = model_list.resolveModel(aiModel)
    model_registry.useInstall(modelNum, entry["name"], installDir)
    return modelNum, entry["name"]


def _fileStamps(folder):
    """{path relative to folder: (size, modification time)} for every file under folder."""
    folder = Path(folder)
    return {f.relative_to(folder).as_posix(): (f.stat().st_size, f.stat().st_mtime_ns)
            for f in folder.rglob("*") if f.is_file()}


def _readLabels(modelName, installDir, outDir):
    """The model's output labels ({file pattern: {label: structure name}}), read with
    pyCERR from the outputs' labels.json, else the install's models.yaml. None (with a
    warning) if neither has them."""
    try:
        return run_utils.readLabels(str(outDir), modelName, installDir)
    except (OSError, ValueError) as exc:
        warnings.warn(f"Could not read {modelName}'s output labels: {exc}")
        return None


def _row(df, ptId):
    return df.loc[ptId] if df is not None and ptId in df.index else None


def _deriveOrder(structNames):
    """structNames in the order they're derived: classic recipes first (they may be
    used by the others), then the rest. Raises if any has no registered recipe."""
    structNames = list(structNames)
    missing = [name for name in structNames if structures.getDerivation(name) is None]
    if missing:
        raise ValueError(f"No recipe registered to derive: {', '.join(missing)}. "
                         f"Use an existing structure for these instead.")
    return sorted(structNames, key=lambda name: structures.getDerivation(name).type != "classic")


def _deriveStructures(planC, scanNum, deriveNames, existingNames, record, analysisDir, taskLog):
    """Derive deriveNames (in order) for one patient, and export each to
    <analysisDir>/<patientId>/ for review.

    The outputs of every AI model Segment ran for the patient are added first.
    AI outputs, then derived structures, are used instead of structures of the
    same name in the patient's data, except the "existing" structures the
    settings name (existingNames).
    """
    patientId = record.pt_id
    segment = (taskLog["patients"].get(patientId) or {}).get("segment") or {}
    for name in deriveNames:
        aiModel = structures.getDerivation(name).aiModelName
        if aiModel and not logs.isSegmented(analysisDir, taskLog, patientId, aiModel):
            raise ValueError(f"No {aiModel} outputs for this patient; run Segment for {aiModel} first.")

    outDir = Path(analysisDir) / patientId
    numBefore = len(planC.structure)
    for aiModel, result in segment.items():
        if logs.isSegmented(analysisDir, taskLog, patientId, aiModel):
            planC = _importAIOutputs(aiModel, taskLog, result, outDir, scanNum, planC)
    planC = _preferStructures(planC, range(numBefore, len(planC.structure)), existingNames)

    derivedNums = []
    for name in deriveNames:
        structNum, planC = structures.getDerivation(name).deriveFn(planC, scanNum)
        outDir.mkdir(parents=True, exist_ok=True)
        _exportStructure(planC, structNum, record, outDir, name)
        derivedNums.append(structNum)
    return _preferStructures(planC, derivedNums, existingNames)


def _importAIOutputs(aiModel, taskLog, result, outDir, scanNum, planC):
    """Add an AI model's outputs in outDir to planC with pyCERR, using the install
    recorded by the Segment run that made them. Raises if the model's code or
    models.yaml has changed since, since its labels may no longer match."""
    runEntry = taskLog["runs"][result["run"]]
    recorded = next((p for p in (runEntry.get("provenance") or {}).get("ai_models") or []
                     if p["name"] == aiModel), None)
    if recorded is None:
        raise ValueError(f"No install recorded for {aiModel}; run Segment for {aiModel} again.")
    current = logs.aiModelProvenance(aiModel, recorded["install_dir"])
    for key in ("repo_commit", "models_yaml_sha256"):
        if current[key] != recorded[key]:
            raise ValueError(f"{aiModel} has changed since its outputs were made ({key}); "
                             f"run Segment for {aiModel} again.")
    return run_utils.importSeg(aiModel, recorded["install_dir"], str(outDir), scanNum, planC)


def _preferStructures(planC, preferredNums, keepNames=()):
    """Remove structures sharing a name (case-insensitive) with one of
    preferredNums, so validate's structure is used, with a warning. Structures
    named in keepNames (the settings' "existing" structures) are always kept."""
    preferredNums = set(preferredNums)
    preferredNames = [planC.structure[i].structureName for i in preferredNums]
    keepNames = {name.lower() for name in keepNames}
    kept = []
    for i, struct in enumerate(planC.structure):
        if (i not in preferredNums and struct.structureName.lower() not in keepNames
                and getMatchingIndex(struct.structureName, preferredNames, "exact")):
            warnings.warn(f"Using validate's '{struct.structureName}' instead of the one in the patient's data.")
        else:
            kept.append(struct)
    planC.structure = kept
    return planC


def _dropValidateOutputs(planC, analysisDir, taskLog, patientId):
    """Remove structures read from validate's own files (AI outputs recorded in the
    task log, or derived-structure exports) when the patient's folder is also the
    analysis folder, so they aren't mistaken for the patient's data."""
    segment = (taskLog["patients"].get(patientId) or {}).get("segment") or {}
    outputs = {os.path.realpath(Path(analysisDir) / f)
               for result in segment.values() for f in result.get("files") or []}

    def isOutput(struct):
        fileName = struct.structureFileName
        return bool(fileName) and (os.path.realpath(fileName) in outputs
                                   or Path(fileName).name.endswith(f"{AUTOSEG_SUFFIX}.dcm"))

    planC.structure = [s for s in planC.structure if not isOutput(s)]
    return planC


def _patientNameMap(record):
    """{modelStructName: name in this patient's planC}.

    DICOM: the record's per-patient names (plan_structures_csv cell, else an
    "existing" recipe's name).
    NIfTI/NRRD: none, since masks are loaded under the model's structure names.
    """
    if record.file_info.scan_file is not None:
        return {}
    return {model: name for model, name in record.structures.items() if name != model}


def _exportStructure(planC, structNum, record, outDir, structName):
    """Export a derived structure with pyCERR, in the patient's input format:
    RTSTRUCT for DICOM, a NIfTI mask for NIfTI/NRRD (an RTSTRUCT can't be linked
    to a scan loaded from NIfTI). Written as <patientId>_<structName>_autoseg.*"""
    stem = outDir / f"{record.pt_id}_{structName}{AUTOSEG_SUFFIX}"
    if record.file_info.scan_file is None:
        rtstruct_iod.create([structNum], str(stem) + ".dcm", planC,
                            {"seriesDescription": "AI Generated (validate)"})
    else:
        planC.structure[structNum].saveNii(str(stem) + ".nii.gz", planC)


def _checkStructuresPresent(planC, structNames):
    """Raise error if any required structured are missing from planC."""
    available = [s.structureName for s in planC.structure]
    missing = [name for name in structNames if not getMatchingIndex(name, available, "exact")]
    if missing:
        raise ValueError(f"Missing structure(s): {', '.join(missing)}. "
                         f"Available: {', '.join(available) if available else 'none'}.")
    for name in structNames:
        matches = getMatchingIndex(name, available, "exact")
        if len(matches) > 1:
            warnings.warn(f"Structure '{name}' matches {len(matches)} structures in the patient's "
                          f"data; the first is used.")


def _setPatientPredictors(model, predictors):
    """Set patient-specific predictors from CSV row. Blank cells leave the model's value unchanged."""
    for name, entry in model["parameters"].items():
        if (name != "structures" and isinstance(entry, dict) and "val" in entry
                and predictors.get(name) is not None):
            entry["val"] = predictors[name]
    return model
