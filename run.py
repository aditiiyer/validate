"""Run an analysis on every patient in the cohort.

Segment tab: applyAutoSegToCohort runs the AI models in the settings and records their outputs.
Model tab: applyModelToCohort derives the structures the dosimetric model needs (from the AI
outputs or classic recipes), then computes NTCP. deriveStructuresForCohort only derives them.
"""

import os
import shutil
import warnings
from pathlib import Path
from types import SimpleNamespace

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
DERIVE_COLUMNS = ["patient_id", "status", "message"]
AUTOSEG_SUFFIX = "_autoseg"
ABORTED_MESSAGE = "Aborted by user"

def applyAutoSegToCohort(analysisDir, errorLog, progressCallback=None, stageCallback=None, overwrite=False,
                         shouldStop=None, isAborted=None):
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
        isAborted (callable): optional f() -> bool; True once the run was aborted (its
            AI model processes killed). The patient being run is recorded as aborted,
            and no further AI model is run.

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
            if isAborted and isAborted():
                break
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
                    message = _errorMessage(exc, isAborted)
                    errorLog.error(patientId, f"{modelName}: {message}")
                    result = {"status": "error", "message": message}
                    patientResult[modelName] = f"error: {message}"
                finally:
                    shutil.rmtree(sessionDir, ignore_errors=True)
            logs.recordResult(analysisDir, taskLog, runIndex, patientId, "segment", result,
                              key=modelName, warningMessages=modelWarnings)

        results[patientId] = patientResult
        if progressCallback:
            progressCallback(i + 1, total, patientId)

    logs.finishRun(analysisDir, taskLog, runIndex)
    return results


def applyModelToCohort(analysisDir, errorLog, progressCallback=None, shouldStop=None, isAborted=None):
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
        isAborted (callable): optional f() -> bool; True once the run was aborted.
            A patient that fails after that is recorded as aborted.

    Returns:
        pandas.DataFrame with columns: patient_id, ntcp, status, message.
        status is "ok" or "error"; message holds the exception text on error.
    """
    settingsPath = os.path.join(analysisDir, analysis.FILE_NAME)
    try:
        inputs = _modelInputs(settingsPath)
        predictorsDf, fromPredictors, patients = inputs.predictorsDf, inputs.fromPredictors, inputs.patients
        modelFile, patientInfoDf = inputs.modelFile, inputs.patientInfoDf
        recipes, deriveNames = inputs.recipes, inputs.deriveNames
        correctionType = getFractionCorrectionType(modelFile)

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
        derivedFiles = {}   # {structName: exported file, relative to analysisDir}
        derived = False     # True once the structures are derived
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
                    planC, doseNum = deriveModelStructures(record, patientInfo, recipes, deriveNames,
                                                           analysisDir, taskLog, derivedFiles)
                    derived = True
                    if doseNum is None:
                        raise ValueError("No dose found in plan.")
                    patientModel = applyStructureNameMap(modelFile, _patientNameMap(record))
                    _setPatientPredictors(patientModel, record.predictors)
                    _checkStructuresPresent(planC, getRequiredStructures(patientModel))
                    fxSize, fxNum = getFractionation(patientInfo)
                    fSizeIn, fNumIn = getFractionationInputs(fxSize, fxNum, correctionType)
                    ntcp = float(doseModels.run(patientModel, doseNum, planC, fSizeIn=fSizeIn, fNumIn=fNumIn))
            except Exception as exc:
                status = "error"
                message = _errorMessage(exc, isAborted)
                errorLog.error(patientId, f"NTCP: {message}")

        rows.append({"patient_id": patientId, "ntcp": ntcp,
                     "status": status, "message": message})
        ntcpResult = {"status": status, "value": ntcp} if status == "ok" else {"status": status, "message": message}
        if deriveNames and not fromPredictors:
            derivedResult = {"status": "ok"} if derived else {"status": "error", "message": message}
            logs.recordResult(analysisDir, taskLog, runIndex, patientId, "segment",
                              {**derivedResult, "files": derivedFiles}, key=logs.DERIVED_KEY)
        logs.recordResult(analysisDir, taskLog, runIndex, patientId, "ntcp", ntcpResult,
                          warningMessages=patientWarnings)

        if progressCallback:
            progressCallback(i + 1, total, patientId)

    logs.finishRun(analysisDir, taskLog, runIndex)
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def deriveStructuresForCohort(analysisDir, errorLog, progressCallback=None, shouldStop=None, isAborted=None):
    """Derive the structures set to "derive" in the settings for every patient,
    without computing NTCP (see deriveModelStructures).

    Each patient's exports and status are recorded in task_log.yaml under the
    patient's "segment" section (logs.DERIVED_KEY).

    Args:
        analysisDir (str): the analysis folder holding the settings file (analysis.FILE_NAME).
        errorLog (validate.logs.ErrorLog): error log to write to.
        progressCallback (callable): optional f(done, total, patientId) hook,
            invoked after each patient is processed.
        shouldStop (callable): optional f() -> bool, checked before each patient;
            True stops the run there.
        isAborted (callable): optional f() -> bool; True once the run was aborted.
            A patient that fails after that is recorded as aborted.

    Returns:
        pandas.DataFrame: One row per patient: patient_id, status ("ok" or "error"), message.

    Raises:
        ValueError: the settings start from pre-computed predictors, or no structure is set to "derive".
    """
    settingsPath = os.path.join(analysisDir, analysis.FILE_NAME)
    try:
        inputs = _modelInputs(settingsPath)
        if inputs.fromPredictors:
            raise ValueError("Structures can't be derived when starting from pre-computed predictors.")
        if not inputs.deriveNames:
            raise ValueError("No structures are set to Derive.")
        taskLog, runIndex = logs.startRun(analysisDir, settingsPath, "model", errorLogPath=errorLog.path,
                                          details=logs.modelFileProvenance(inputs.modelFile))
    except Exception as exc:
        errorLog.error("(setup)", str(exc))
        raise

    total = len(inputs.patients)
    rows = []
    for i, (patientId, dataDir) in enumerate(inputs.patients):
        if shouldStop and shouldStop():
            break
        derivedFiles = {}
        result = {"status": "ok"}
        with logs.collectWarnings() as patientWarnings:
            try:
                patientInfo = _row(inputs.patientInfoDf, patientId)
                record = buildPatientRecord(patientId, dataDir, inputs.recipes, planRow=patientInfo,
                                            predictorsRow=_row(inputs.predictorsDf, patientId))
                deriveModelStructures(record, patientInfo, inputs.recipes, inputs.deriveNames,
                                      analysisDir, taskLog, derivedFiles)
            except Exception as exc:
                result = {"status": "error", "message": _errorMessage(exc, isAborted)}
                errorLog.error(patientId, f"Derive: {result['message']}")

        rows.append({"patient_id": patientId, "status": result["status"], "message": result.get("message", "")})
        logs.recordResult(analysisDir, taskLog, runIndex, patientId, "segment",
                          {**result, "files": derivedFiles}, key=logs.DERIVED_KEY,
                          warningMessages=patientWarnings)
        if progressCallback:
            progressCallback(i + 1, total, patientId)

    logs.finishRun(analysisDir, taskLog, runIndex)
    return pd.DataFrame(rows, columns=DERIVE_COLUMNS)


def deriveModelStructures(record, patientInfo, recipes, deriveNames, analysisDir, taskLog, derivedFiles=None):
    """Load one patient's data and derive the model's "derive" structures.

    Validate's own outputs are dropped from the loaded data first. Structures are
    derived on the scan the dose is linked to (the first scan if there's no dose),
    and each is exported to <analysisDir>/<patientId>/ (see _deriveStructures).

    Args:
        record: the patient's record (data_io.build_capsule.buildPatientRecord).
        patientInfo (pandas.Series or None): the patient's plan CSV row.
        recipes (dict): {structName: settings entry} for the model's structures.
        deriveNames (list[str]): structures to derive, in order (see _deriveOrder).
        analysisDir (str): the analysis folder.
        taskLog (dict): the task log (for the AI outputs Segment recorded).
        derivedFiles (dict, optional): filled with {structName: exported file, relative to analysisDir}.

    Returns:
        tuple: (planC, doseNum), doseNum None if the patient has no dose.
    """
    patientId = record.pt_id
    planC = loadPatientPlanC(record)
    planC = _dropValidateOutputs(planC, analysisDir, taskLog, patientId)
    # Forget the last run's derived exports; this run records its own
    ((taskLog["patients"].get(patientId) or {}).get("segment") or {}).pop(logs.DERIVED_KEY, None)
    doseNum = getDoseIndex(planC, patientId=patientId, patientInfo=patientInfo)
    if deriveNames:
        scanNum = (cerrScan.getScanNumFromUID(planC.dose[doseNum].assocScanUID, planC)
                   if doseNum is not None else 0)
        existingNames = [record.structures[name] for name, recipe in recipes.items()
                         if recipe.get("source") == "existing"]
        planC = _deriveStructures(planC, scanNum, deriveNames, existingNames, record,
                                  analysisDir, taskLog, derivedFiles)
    return planC, doseNum

#===================================
# Helper functions
#====================================
def _modelInputs(settingsPath):
    """Read the Model tab's inputs from the settings: the patients, model file,
    CSV tables and each required structure's recipe."""
    dataCapsule = analysis.toDataCapsule(settingsPath)
    # Patient-specific clinical factors (selected predictors)
    predictorsDf = loadPatientInfo(dataCapsule.predictors_csv) if dataCapsule.predictors_csv else None
    # Only pre-computed predictors (incl. DVH metrics)?
    fromPredictors = dataCapsule.start_from == "predictors"
    if fromPredictors:
        patients = [(ptId, None) for ptId in sorted(predictorsDf.index)]
    else:
        patients = discoverPatients(dataCapsule.cohort_dir)
    modelFile = dataCapsule.model["file"]
    planStructuresCsv = dataCapsule.plan_structures_csv
    requiredStructs = getRequiredStructures(modelFile)
    # Analysis-level recipes for the model's structures ("existing" ones may give a dataset name)
    recipes = {name: dataCapsule.structures.get(name) or {} for name in requiredStructs}
    return SimpleNamespace(
        predictorsDf=predictorsDf, fromPredictors=fromPredictors, patients=patients, modelFile=modelFile,
        patientInfoDf=loadPatientInfo(planStructuresCsv) if planStructuresCsv else None,
        recipes=recipes,
        deriveNames=_deriveOrder(name for name in requiredStructs if recipes[name].get("source") == "derive"))


def _errorMessage(exc, isAborted):
    """The message recorded for a patient's error: ABORTED_MESSAGE if the run was
    aborted (the error is then from its killed processes), else the error's text."""
    return ABORTED_MESSAGE if isAborted and isAborted() else str(exc)


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


def _deriveStructures(planC, scanNum, deriveNames, existingNames, record, analysisDir, taskLog,
                      derivedFiles=None):
    """Derive deriveNames (in order) for one patient, and export each to
    <analysisDir>/<patientId>/ for review.

    The outputs of every AI model Segment ran for the patient are added first.
    AI outputs, then derived structures, are used instead of structures of the
    same name in the patient's data, except the "existing" structures the
    settings name (existingNames). Each export is added to derivedFiles
    ({structName: path relative to analysisDir}) as it's written.
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
        if aiModel != logs.DERIVED_KEY and logs.isSegmented(analysisDir, taskLog, patientId, aiModel):
            planC = _importAIOutputs(aiModel, taskLog, result, outDir, scanNum, planC)
    planC = _preferStructures(planC, range(numBefore, len(planC.structure)), existingNames)

    derivedNums = []
    for name in deriveNames:
        structNum, planC = structures.getDerivation(name).deriveFn(planC, scanNum)
        outDir.mkdir(parents=True, exist_ok=True)
        exportPath = _exportStructure(planC, structNum, record, outDir, name)
        if derivedFiles is not None:
            derivedFiles[name] = Path(exportPath).relative_to(analysisDir).as_posix()
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
    # files is a list for AI outputs, {structName: file} for derived exports
    outputs = {os.path.realpath(Path(analysisDir) / f)
               for key, result in segment.items() if key != logs.DERIVED_KEY
               for f in result.get("files") or []}
    derived = (segment.get(logs.DERIVED_KEY) or {}).get("files") or {}
    outputs |= {os.path.realpath(Path(analysisDir) / f) for f in derived.values()}

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
    to a scan loaded from NIfTI). Written as <patientId>_<structName>_autoseg.*

    Returns:
        str: path to the exported file.
    """
    stem = outDir / f"{record.pt_id}_{structName}{AUTOSEG_SUFFIX}"
    if record.file_info.scan_file is None:
        path = str(stem) + ".dcm"
        rtstruct_iod.create([structNum], path, planC,
                            {"seriesDescription": "AI Generated (validate)"})
    else:
        path = str(stem) + ".nii.gz"
        planC.structure[structNum].saveNii(path, planC)
    return path


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
