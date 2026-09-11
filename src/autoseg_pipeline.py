"""Batch auto-segmentation pipeline.
- Check install status, install missing AI models, then run+derive+export+log per patient.
"""

import os
import shutil
from pathlib import Path

import pandas as pd

from cerr import plan_container as pc
from cerr.ai_models import install_utils, run_utils
from cerr.dcm_export import rtstruct_iod

from validate.src import model_registry
from validate.src import structures
from validate.src import logging as autoseg_log
from validate.src.data_import import discoverPatients, loadPatientInfo, getDoseIndex


def checkModelsForStructures(structNames):
    """Resolve install status for the AI models structNames need.

    Structures derived via a "classic" (non cerr.ai_models) method --
    structures.StructureDerivation.type == 'classic', aiModelNum None --
    need no install check; getRequiredAiModels still reports them (as
    aiModelNum None), so they're filtered out here.

    Returns:
        (models, missingRecipe): models is {aiModelNum: {"name": str, "installed": bool}}
         for the required AI models.
    """
    modelNames, missingRecipe = structures.getRequiredAiModels(structNames)
    models = {}
    for num, name in modelNames.items():
        if num is None: #Classical models
            continue
        isInstalled, __ = model_registry.getInstallInfo(num)
        models[num] = {"name": name, "installed": isInstalled}
    return models, missingRecipe


def installMissingModels(modelNums, installBaseDir, progressCallback=None, force=False):
    """Install each of modelNums via cerr.ai_models.install_utils, recording
    success in model_registry.

    Args:
        modelNums (iterable[int]): AI model numbers to ensure installed.
        installBaseDir (str): directory models are installed under
            (installed to installBaseDir/<modelName>).
        progressCallback (callable): optional f(message) status hook.
        force (bool): if True, re-install and replace the registry entry
            even for a modelNum already marked installed (e.g. its files
            were modified locally and need a fresh install). Default False
            skips anything already installed, as before.

    Returns:
        list of (modelNum, success, message) -- message is the error text
        on failure, "" on success.
    """
    results = []
    for modelNum in modelNums:
        isInstalled, __ = model_registry.getInstallInfo(modelNum)
        if not force and isInstalled:
            results.append((modelNum, True, ""))
            continue
        try:
            if progressCallback:
                progressCallback(f"Installing model {modelNum}...")
            modelName = install_utils.validateModelNum(modelNum)
            install_utils.main(modelNum, installBaseDir)
            model_registry.recordInstall(modelNum, modelName, installBaseDir)
            results.append((modelNum, True, ""))
        except Exception as exc:
            results.append((modelNum, False, str(exc)))
    return results


def runAIModel(modelNum, dicomDir, sessionDir,
               progressCallback=None):
    """Run one AI model on one patient's DICOM directory.

    The model's own post-processing script (cerr/ai_models/post/*.py)
    exports its raw output as an RTSTRUCT into dicomDir, per the
    cerr.ai_models convention -- so afterward, reloading the patient's
    planC from dicomDir picks up those raw structures generically, without
    depending on run_utils.main()'s return value.
    """
    installed, installInfo = model_registry.getInstallInfo(modelNum)
    if not installed:
        raise RuntimeError(f"Model {modelNum} is not installed.")
    installDir = installInfo["installDir"]

    userInputs = {"input_path": dicomDir, "output_path": dicomDir,
                 "session_path": sessionDir}
    if progressCallback:
        progressCallback(f"Applying {installInfo['modelName']} AI segmentation model...")
    run_utils.main(modelNum, installDir, userInputs)


def runAutoSegmentationForCohort(cohortDir, autosegStructNames, installBaseDir,
                                 planName,taskLog, progressCallback=None, overwrite=False):
    """Auto-segment autosegStructNames for every patient in cohortDir.

    For each patient, each distinct AI model needed is run at most once.
    Each structure in the dosimetric model is then derived, exported (RTSTRUCT), and logged.
    Skips (patient, AI model) pairs already fully covered by the availability log unless overwrite=True.

    Args:
        cohortDir (str): cohort directory (one DICOM subdir per patient).
        autosegStructNames (list[str]): required structure names to
            auto-segment (must all have a registered derivation --
            call checkModelsForStructures first to confirm).
        installBaseDir (str): directory AI models are installed under.
        planName (str, pandas.DataFrame, or None): Per-patient info DataFrame
            Used to resolve dose/plan index (see validate.src.data_import.loadPatientInfo).
        taskLog (validate.src.logging.TaskLog): run log to write to.
        progressCallback (callable): optional f(message) stage hook.
        overwrite (bool): if True, re-run even if already logged available.

    Returns:
        dict: {patientId: {structName: "ok"|"error: <message>"}}
    """
    if planName is None:
        patientInfoDf = None
    elif isinstance(planName, pd.DataFrame):
        patientInfoDf = planName
    else:
        patientInfoDf = loadPatientInfo(planName)

    # Group AI-backed structures by aiModelNum
    # Skip for structires segmented using classical methods.
    # -- deriveFn runs its own model internally -- so each gets its own group.
    structsByModel = {}
    for structName in autosegStructNames:
        derivation = structures.getDerivation(structName)
        isClassic = derivation.type == 'classic'
        groupKey = ('classic', structName) if isClassic else derivation.aiModelNum
        structsByModel.setdefault(groupKey, []).append((structName, derivation))

    patients = discoverPatients(cohortDir)
    results = {}

    # Loop oer pts
    for patientId, dicomDir in patients:
        patientResult = {}
        planC = None
        planNum = None
        # Get metadata
        patientInfo = (patientInfoDf.loc[patientId]
                       if patientInfoDf is not None and patientId in patientInfoDf.index
                       else None)
        # For each required structure:
        for groupKey, structEntries in structsByModel.items():
            firstDerivation = structEntries[0][1]
            isClassic = firstDerivation.type == 'classic'
            # aiModelName also doubles as the availability-log key;
            # classic availability entries are in classic_<structure> log.
            aiModelName = (f"classic_{structEntries[0][0]}" if isClassic
                          else firstDerivation.aiModelName)
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
                if not isClassic:
                    # Run required AI model
                    runAIModel(groupKey, dicomDir, str(sessionDir), progressCallback)
                if planC is None:
                    planC = pc.loadDcmDir(dicomDir)
                else:
                    planC = pc.loadDcmDir(dicomDir, initplanC=planC)
                if planNum is None:
                    planNum = getDoseIndex(planC, patientId=patientId, patientInfo=patientInfo)

                # Apply post-processing operations
                for structName, derivation in needed:
                    structNum, planC = derivation.deriveFn(planC, planNum)
                    outFile = os.path.join(
                        dicomDir, f"{patientId}_{structName}_autoseg.dcm")
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
