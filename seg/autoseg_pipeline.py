"""Batch auto-segmentation pipeline.
- Check install status, install missing AI models, then run+derive+export+log per patient.
"""

import shutil
from pathlib import Path

from cerr.ai_models import install_utils, run_utils, model_list

from validate.seg import model_registry
from validate.seg import structures


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


def installMissingModels(modelNums, installBaseDir, progressCallback=None, force=False, **installOptions):
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
            skips anything already installed, as before. Also replaces
            the installed weights (install_utils forceWeights).
        **installOptions: optional keyword arguments passed on to
            install_utils.main, e.g. weightsUrl, weightsFile, credentials,
            forceWeights, rebuildEnv, update. weightsUrl and weightsFile
            need a single model in modelNums.

    Returns:
        list of (modelNum, success, message) -- message is the error text
        on failure, "" on success.

    Raises:
        ValueError: weightsUrl or weightsFile given with more than one model.
    """
    modelNums = list(modelNums)
    if len(modelNums) > 1 and (installOptions.get("weightsUrl") or installOptions.get("weightsFile")):
        raise ValueError("weightsUrl and weightsFile apply to one model; pass a single model number.")
    if force:
        installOptions["forceWeights"] = True
    results = []
    for modelNum in modelNums:
        isInstalled, __ = model_registry.getInstallInfo(modelNum)
        if not force and isInstalled:
            results.append((modelNum, True, ""))
            continue
        try:
            if progressCallback:
                progressCallback(f"Installing model {modelNum}...")
            _, modelEntry = model_list.resolveModel(modelNum)
            modelName = modelEntry["name"]
            install_utils.main(modelNum, installBaseDir, **installOptions)
            model_registry.recordInstall(modelNum, modelName, installBaseDir)
            results.append((modelNum, True, ""))
        except Exception as exc:
            results.append((modelNum, False, str(exc)))
    return results


def runAIModel(modelNum, record, sessionDir,
               progressCallback=None, outputDir=None):
    """Run one AI model on one patient (DICOM, NIfTI or NRRD).

    Args:
        modelNum (int): AI model number.
        record (validate.core.data_capsule.PatientRecord): Patient info datastruct.
                For DICOM, scans are in record.file_info.data_dir.
                For NIfTI/NRRD, teh scan is at record.file_info.scan_file.
        sessionDir (str): working folder for this run.
        progressCallback (callable): optional f(message) status hook.
        outputDir (str or None): folder the model writes its outputs to.
            Defaults to the patient's folder, record.file_info.data_dir.
    """
    installed, installInfo = model_registry.getInstallInfo(modelNum)
    if not installed:
        raise RuntimeError(f"Model {modelNum} is not installed.")
    installDir = installInfo["installDir"]

    dataDir = record.file_info.data_dir
    scanFile = record.file_info.scan_file
    if scanFile is None:
        inputDir = dataDir
    else:
        stagedDir = Path(sessionDir) / "scan_cpy"
        stagedDir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(dataDir) / scanFile, stagedDir / Path(scanFile).name)
        inputDir = str(stagedDir)

    userInputs = {"input_path": inputDir, "output_path": str(outputDir) if outputDir else dataDir,
                 "session_path": sessionDir}
    if progressCallback:
        progressCallback(f"Applying {installInfo['modelName']} AI segmentation model...")
    run_utils.main(modelNum, installDir, userInputs)
