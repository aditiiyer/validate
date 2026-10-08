"""Run an analysis: apply the model to every patient in the cohort."""

import os
import shutil
from pathlib import Path

import pandas as pd

from cerr.roe import dosimetric_models as doseModels
from cerr import plan_container as pc
from cerr.dcm_export import rtstruct_iod
from cerr.ai_models import run_utils

from validate.data_io.read_inputs import (discoverPatients, loadPatientPlanC, getDoseIndex,
                                 loadPatientInfo, getFractionation)
from validate.seg.structures import applyStructureNameMap, getRequiredStructures
from validate.modeling.apply_model import getFractionCorrectionType, getFractionationInputs
from validate.seg import structures, model_registry
from validate.seg.autoseg_pipeline import runAIModel
from validate.data_io.build_capsule import buildCapsule, buildPatientRecord
from validate import logs as autoseg_log

RESULT_COLUMNS = ["patient_id", "ntcp", "status", "message"]


def applyAutoSegToCohort(analysisPath, autosegStructNames, installBaseDir,
                                 taskLog, progressCallback=None, overwrite=False):
    """Auto-segment specified structures for every pt dataset in the cohort.

    For each patient, each distinct AI model needed is run at most once.
    Each structure in the dosimetric model is then derived, exported (RTSTRUCT), and logged.
    Skips (patient, AI model) pairs already fully covered by the availability log unless overwrite=True.

    Args:
        analysisPath (str): path to the analysis settings file used to build teh DataCapsule.
        autosegStructNames (list[str]): required structure names to
            auto-segment (must all have a registered derivation --
            call checkModelsForStructures first to confirm).
        installBaseDir (str): directory AI models are installed under.
        taskLog (validate.src.logging.TaskLog): run log to write to.
        progressCallback (callable): optional f(message) stage hook.
        overwrite (bool): if True, re-run even if already logged available.

    Returns:
        dict: {patientId: {structName: "ok"|"error: <message>"}}
    """
    dataCapsule = buildCapsule(analysisPath)
    cohortDir = dataCapsule.cohort_dir

    # Group AI-backed structures by aiModelNum
    # Skip for structires segmented using classical methods.
    # -- deriveFn runs its own model internally -- so each gets its own group.
    structsByModel = {}
    for structName in autosegStructNames:
        derivation = structures.getDerivation(structName)
        isClassic = derivation.type == 'classic'
        groupKey = ('classic', structName) if isClassic else derivation.aiModelNum
        structsByModel.setdefault(groupKey, []).append((structName, derivation))

    results = {}

    # Loop over pts
    for record in dataCapsule.patients.values():
        patientId = record.pt_id
        dataDir = record.file_info.data_dir
        patientResult = {}
        planC = None
        planNum = None
        # getDoseIndex reads the plan name from a plan_structures_csv-style row
        patientInfo = {"Plan name": record.plan_info.name} if record.plan_info else None
        # Run AI-models before classic ones
        orderedGroups = sorted(structsByModel.items(),
                               key=lambda kv: kv[1][0][1].type == 'classic')
        for groupKey, structEntries in orderedGroups:
            firstDerivation = structEntries[0][1]
            isClassic = firstDerivation.type == 'classic'
            # aiModelName also doubles as the availability-log key; shared
            # with _checkExistingAvailability via structures.getAvailabilityLogKey
            # so the two never disagree on where a structure's log lives.
            aiModelName = structures.getAvailabilityLogKey(structEntries[0][0])
            needed = [(name, d) for name, d in structEntries
                     if overwrite or not autoseg_log.isAvailable(
                         cohortDir, aiModelName, patientId, name)]
            # Check if already auto-segmented (autoseg log)
            if not needed:
                for name, _ in structEntries:
                    patientResult[name] = "ok (cached)"
                continue

            #Otherwise:
            sessionDir = Path(autoseg_log.logDir(cohortDir)) / "_sessions" / patientId / aiModelName
            try:
                # Load dataset
                if planC is None:
                    planC = loadPatientPlanC(record)
                if not isClassic:
                    # Run AI model and import segmentations
                    runAIModel(groupKey, record, str(sessionDir), progressCallback)
                    __, installInfo = model_registry.getInstallInfo(groupKey)
                    planC = run_utils.importSeg(groupKey, installInfo["installDir"], dataDir, 0, planC)
                if planNum is None:
                    planNum = getDoseIndex(planC, patientId=patientId, patientInfo=patientInfo)

                # Apply post-processing operations
                for structName, derivation in needed:
                    structNum, planC = derivation.deriveFn(planC, planNum)
                    outFile = os.path.join(
                        dataDir, f"{patientId}_{structName}_autoseg.dcm")
                    rtstruct_iod.create([structNum], outFile, planC,
                                        {"seriesDescription": "AI Generated (validate)"})
                    # Update autoseg log
                    autoseg_log.recordAvailability(cohortDir, aiModelName,
                                                   patientId, structName)
                    patientResult[structName] = "ok"
            except Exception as exc:
                # Record errors in task log
                taskLog.error(patientId, f"{aiModelName}: {exc}")
                for structName, _ in needed:
                    patientResult[structName] = f"error: {exc}"
            finally:
                shutil.rmtree(sessionDir, ignore_errors=True)

        results[patientId] = patientResult
        if progressCallback:
            progressCallback(f"Auto-segmented {patientId}")

    return results


def applyModelToCohort(cohortDir, modelName, planStructuresCsv=None, structNameMap=None,
                       progressCallback=None):
    """Apply a dosimetric model to every patient subdirectory in cohortDir.

    Args:
        cohortDir (str): Parent directory with one subdir per patient, holding
            DICOM, NIfTI or NRRD files (format inferred).
        modelName (str): Built-in model name (see
            cerr.roe.dosimetric_models.listModels()) or path to a custom
            model parameter JSON file.
        planStructuresCsv (str): optional path to plan_structures_csv, one row
            per patient (see data_io.read_inputs).
        structNameMap (dict): optional {modelStructName: datasetStructName}
            mapping the model's required structures (see
            validate.src.structures.getRequiredStructures) to the structure
            names used in the cohort's DICOM data, applied to every patient.
        progressCallback (callable): optional f(done, total, patientId) hook,
            invoked after each patient is processed.

    Returns:
        pandas.DataFrame with columns: patient_id, ntcp, status, message.
        status is "ok" or "error"; message holds the exception text on error.
    """
    patients = discoverPatients(cohortDir)
    total = len(patients)
    patientInfoDf = loadPatientInfo(planStructuresCsv) if planStructuresCsv else None
    correctionType = getFractionCorrectionType(modelName)
    effectiveModel = applyStructureNameMap(modelName, structNameMap)
    requiredStructs = getRequiredStructures(modelName)
    rows = []

    for i, (patientId, dataDir) in enumerate(patients):
        ntcp = None
        status = "ok"
        message = ""
        try:
            patientInfo = (patientInfoDf.loc[patientId]
                          if patientInfoDf is not None and patientId in patientInfoDf.index
                          else None)
            record = buildPatientRecord(patientId, dataDir, {name: {} for name in requiredStructs},
                                        planRow=patientInfo)
            planC = loadPatientPlanC(record)
            doseNum = getDoseIndex(planC, patientId=patientId, patientInfo=patientInfo)
            fxSize, fxNum = getFractionation(patientInfo)
            fSizeIn, fNumIn = getFractionationInputs(fxSize, fxNum, correctionType)
            ntcp = doseModels.run(effectiveModel, doseNum, planC, fSizeIn=fSizeIn, fNumIn=fNumIn)
        except Exception as exc:
            status = "error"
            message = str(exc)

        rows.append({"patient_id": patientId, "ntcp": ntcp,
                     "status": status, "message": message})

        if progressCallback:
            progressCallback(i + 1, total, patientId)

    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


