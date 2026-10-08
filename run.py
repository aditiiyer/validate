"""Run an analysis: apply the model to every patient in the cohort."""

import pandas as pd

from cerr.roe import dosimetric_models as doseModels

from validate.data_io.data_import import (discoverPatients, loadPatientPlanC, getDoseIndex,
                                 loadPatientInfo, getFractionation)
from validate.seg.structures import applyStructureNameMap, getRequiredStructures
from validate.modeling.apply_model import getFractionCorrectionType, getFractionationInputs

RESULT_COLUMNS = ["patient_id", "ntcp", "status", "message"]


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
            per patient (see data_io.data_import).
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
            planC = loadPatientPlanC(dataDir, patientInfo, requiredStructs)
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
