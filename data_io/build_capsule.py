"""Build one PatientRecord per patient and attach them to a DataCapsule.

Combines patient discovery with the per-patient CSV inputs (plan_structures_csv,
predictors_csv, outcomes_csv; see data_import for their formats). Values only
known once a patient's data is loaded (dose index, computed predictors, NTCP)
are initialized to None.
"""

import os
import warnings

from validate.core.analysis import toDataCapsule
from validate.core.data_capsule import FileInfo, PatientRecord, PlanInfo
from validate.data_io.read_inputs import (discoverPatients, inferFileFormat, loadPatientInfo,
                                          getFractionation, _resolveFile, _textField,
                                          _numericField)

def buildCapsule(analysisPath, errorLog=None):
    """Read the analysis settings and build every patient's record.

    Args:
        analysisPath (str): path to the analysis settings file.
        errorLog (validate.logs.ErrorLog or None): see buildPatientRecords.

    Returns:
        DataCapsule: analysis-level settings with patients filled in.
    """
    dataCapsule = toDataCapsule(analysisPath)
    records = buildPatientRecords(dataCapsule, errorLog=errorLog)
    dataCapsule.patients = {record.pt_id: record for record in records}
    return dataCapsule


def buildPatientRecords(dataCapsule, errorLog=None):
    """Build one PatientRecord per patient, using dataCapsule's cohort-level defaults where needed.

    Args:
        dataCapsule (DataCapsule): analysis-level settings.
        errorLog (validate.logs.ErrorLog or None): if given, a patient whose
            record can't be built (e.g. empty folder, unresolvable file
            pattern, non-numeric CSV cell) is written to it and skipped, so
            the rest of the cohort continues. If None, the error is raised.

    Returns:
        list of PatientRecord, sorted by pt_id.
    """
    planDf = loadPatientInfo(dataCapsule.plan_structures_csv) if dataCapsule.plan_structures_csv else None
    predictorsDf = loadPatientInfo(dataCapsule.predictors_csv) if dataCapsule.predictors_csv else None
    outcomesDf = loadPatientInfo(dataCapsule.outcomes_csv) if dataCapsule.outcomes_csv else None

    if dataCapsule.start_from == "predictors":
        patients = [(ptId, None) for ptId in sorted(predictorsDf.index)]
    else:
        patients = discoverPatients(dataCapsule.cohort_dir)

    ptIds = {ptId for ptId, _ in patients}
    for csvName, df in (("plan_structures_csv", planDf), ("predictors_csv", predictorsDf),
                        ("outcomes_csv", outcomesDf)):
        if df is not None:
            unmatched = sorted(set(df.index) - ptIds)
            if unmatched:
                warnings.warn(f"{csvName} has IDs with no matching patient: {unmatched}")

    records = []
    for ptId, dataDir in patients:
        try:
            records.append(buildPatientRecord(ptId, dataDir, dataCapsule.structures,
                                              _row(planDf, ptId), _row(predictorsDf, ptId),
                                              _row(outcomesDf, ptId)))
        except Exception as exc:
            if errorLog is None:
                raise
            errorLog.error(ptId, f"Could not build patient record; skipped: {exc}")
    return records


def buildPatientRecord(ptId, dataDir, recipes, planRow=None, predictorsRow=None, outcomesRow=None):
    """Build a single patient's PatientRecord.

    Args:
        ptId (str): patient ID.
        dataDir (str or None): patient folder; None when starting from predictors.
        recipes (dict): analysis-level structure recipes (DataCapsule.structures).
        planRow, predictorsRow, outcomesRow (pandas.Series or None): this
            patient's row from plan_structures_csv, predictors_csv and
            outcomes_csv, or None.

    Returns:
        PatientRecord
    """
    record = PatientRecord(pt_id=ptId)

    if dataDir is not None:
        isImageFiles = inferFileFormat(dataDir) == "nifti_nrrd"
        record.file_info = _fileInfo(dataDir, planRow, isImageFiles, recipes)
        record.plan_info = _planInfo(planRow)
        record.structures = _structureNames(recipes, planRow, isImageFiles)

    if predictorsRow is not None:
        # A blank cell stays None: computed on the fly where possible
        record.predictors = {col: _numericField(predictorsRow, col) for col in predictorsRow.index}

    record.outcome = _numericField(outcomesRow, "Outcome")
    return record


def _row(df, ptId):
    return df.loc[ptId] if df is not None and ptId in df.index else None


def _fileInfo(dataDir, planRow, isImageFiles, recipes):
    """Patient folder plus, for NIfTI/NRRD, the scan, dose and structure mask
    files (relative to it). A blank structure cell adds no mask file."""
    fileInfo = FileInfo(data_dir=dataDir)
    if isImageFiles:
        scanPattern = _textField(planRow, "Scan file")
        dosePattern = _textField(planRow, "Dose file")
        if scanPattern:
            fileInfo.scan_file = os.path.relpath(_resolveFile(dataDir, scanPattern, "Scan file"), dataDir)
        if dosePattern:
            fileInfo.dose_file = os.path.relpath(_resolveFile(dataDir, dosePattern, "Dose file"), dataDir)
        for structName in recipes:
            cell = _textField(planRow, structName)
            if cell:
                pattern, sep, label = cell.partition(":")
                maskFile = os.path.relpath(_resolveFile(dataDir, pattern, structName), dataDir)
                fileInfo.structure_files[structName] = maskFile + sep + label
    return fileInfo


def _planInfo(planRow):
    if planRow is None:
        return None
    fxSize, fxNum = getFractionation(planRow)
    return PlanInfo(name=_textField(planRow, "Plan name"),
                    prescribed_dose=_numericField(planRow, "Prescribed dose (Gy)"),
                    fx_size=fxSize, fx_num=fxNum)


def _structureNames(recipes, planRow, isImageFiles):
    """Map each modelled structure to its name in this patient's planC.

    DICOM: Read from plan_structures_csv cell gives the patient's own name; otherwise
    an "existing" recipe's name is used. Generated structures (ai, classic,
    derived) and NIfTI/NRRD masks are named after the modelled structure.
    """
    names = {}
    for structName, recipe in recipes.items():
        csvName = _textField(planRow, structName)
        if isImageFiles:
            names[structName] = structName
        elif csvName:
            names[structName] = csvName
        elif (recipe or {}).get("source") == "existing":
            names[structName] = recipe.get("name") or structName
        else:
            names[structName] = structName
    return names
