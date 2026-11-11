"""Cohort discovery, importing data and analysis settings to DataCapsule

Required inputs
 Raw data or pre-computed predictors

    * Raw data
        cohort_dir/
            pt001/   (scan, dose and structure files: DICOM, NIfTI or NRRD)
            pt002/
            ...
    * Predictors (CSV input)
        One row per patient."ID" is required. Other columns are model-dependent.
        Columns containing DVH metrics should be named "<structure> <metric>"  as in the model file (e.g. "Esophagus meanDose").
        Values must already be fractionation-corrected if the model requires correction.

Optional inputs:

    * plan_structures_csv (optional input alongside raw data)
    One row per patient. Only "ID" is required; every other column is optional.

        ID               Patient folder name under cohort_dir.
        Plan name        DICOM only: RTDOSE file name, used where more than one dose plan is available.
        Prescribed dose (Gy)  Total prescribed dose. Number only, in Gy.
        Fraction size (Gy)    Dose per fraction. Number only, in Gy.
        Fraction number  Number of fractions.
        Scan file        NIfTI/NRRD only: scan file name or wildcard pattern.
        Dose file        NIfTI/NRRD only: dose file name or wildcard pattern.
                         The loaded dose is used as dose index 0.
        <structure>      One column per structure the model requires, named as in
                         the model. The value is:
                         DICOM      : Structure name in the RTSTRUCT
                         NIfTI/NRRD : Mask file name or pattern, or "file:label"
                                   for a label map (e.g. "labels.nii.gz:3")

    File names and patterns are relative to the patient's folder and
    must match exactly one file.

    Example:
    ID,Prescribed dose (Gy),Fraction size (Gy),Fraction number,Scan file,Dose file,Parotids,Oral cavity
    pt_1,70,2,35,scan_*.nii.gz,dose_*.nii.gz,Parotids.nii.gz,labels.nii.gz:3

    * predictors_csv (optional, raw data only)

"""

import os
import glob
import json
import warnings
import pandas as pd
from pydicom.misc import is_dicom

from cerr import plan_container as pc
from cerr.roe import dosimetric_models as doseModels

from validate.core.analysis import FILE_NAME as SETTINGS_FILE_NAME
from validate.logs import LOG_DIR_NAME, TASK_LOG_NAME

IMAGE_FILE_EXTENSIONS = (".nii", ".nii.gz", ".nrrd")
# validate's own outputs, which may sit in the cohort folder when it is also the analysis folder
VALIDATE_OUTPUT_NAMES = {LOG_DIR_NAME, SETTINGS_FILE_NAME, TASK_LOG_NAME}
PLAN_INFO_COLUMNS = ["ID", "Plan name", "Prescribed dose (Gy)",
                     "Fraction size (Gy)", "Fraction number"]


def discoverPatients(cohortDir):
    """List patient subdirectories of a cohort directory.

    Args:
        cohortDir (str): Path to the parent directory holding DICOM/ NIfTI/NRRD data.

    Returns:
        list of (patientId, dicomDir) tuples, sorted by patientId. validate's
        own outputs (VALIDATE_OUTPUT_NAMES: the log folder, settings file and
        task log) are skipped, since the cohort folder may also be the
        analysis folder.
    """
    entries = []
    for name in sorted(os.listdir(cohortDir)):
        if name in VALIDATE_OUTPUT_NAMES:
            continue
        path = os.path.join(cohortDir, name)
        if os.path.isdir(path):
            entries.append((name, path))
    return entries


def inferFileFormat(dataDir):
    """Return data format.
    Identifies raw data format (dicom) or (nifti_nrrd).

    """
    fileNames = [f for f in os.listdir(dataDir) if os.path.isfile(os.path.join(dataDir, f))]
    hasImageFiles = any(f.lower().endswith(IMAGE_FILE_EXTENSIONS) for f in fileNames)
    hasDicomFiles = any(is_dicom(os.path.join(dataDir, f)) for f in fileNames
                        if not f.lower().endswith(IMAGE_FILE_EXTENSIONS))
    if hasImageFiles and hasDicomFiles:
        raise ValueError(f"{dataDir} holds both DICOM and NIfTI/NRRD files.")
    if hasImageFiles:
        return "nifti_nrrd"
    if hasDicomFiles:
        return "dicom"
    raise ValueError(f"No DICOM, NIfTI or NRRD files found in {dataDir}.")


def loadPatientPlanC(record):
    """Load a single patient's planC from a DICOM, NIfTI or NRRD folder.

    Args:
        record (validate.core.data_capsule.PatientRecord): The patient directory is
            in record.file_info.data_dir (DICOM). For NIfTI/NRRD,
            record.file_info.scan_file (required) and dose_file (optional)
            name the scan and dose, and record.file_info.structure_files maps
            each modelled structure to its mask file, or "file:label" for a
            label map (default: binary mask, label 1); all relative to that folder.
            Each mask is named after its modelled structure in planC.

    Returns:
        cerr.plan_container.PlanC
    """
    dataDir = record.file_info.data_dir
    fileFormat = inferFileFormat(dataDir)
    if fileFormat == "dicom":
        return pc.loadDcmDir(dataDir)
    if fileFormat != "nifti_nrrd":
        raise ValueError(f"Unsupported file format: {fileFormat!r}")

    if record.file_info.scan_file is None:
        raise ValueError(f"No 'Scan file' given for patient {record.pt_id!r} in plan_structures_csv.")
    planC = pc.loadNiiScan(os.path.join(dataDir, record.file_info.scan_file))

    if record.file_info.dose_file is not None:
        planC = pc.loadNiiDose(os.path.join(dataDir, record.file_info.dose_file), 0, planC)

    # Group structures by file so a label map shared by several structures is read once
    multiLabelFile = {}
    for structName, fileAndLabel in record.file_info.structure_files.items():
        maskFile, _, label = fileAndLabel.partition(":")
        structFile = os.path.join(dataDir, maskFile)
        multiLabelFile.setdefault(structFile, {})[structName] = int(label) if label else 1
    for structFile, labelsDict in multiLabelFile.items():
        planC = pc.loadNiiStructure(structFile, 0, planC, labelsDict)

    return planC



def loadPatientInfo(csvPath):
    """Read optional CSV files (plan_structures_csv, predictors_csv, outcomes_csv) indexed by patient ID.

    All columns besides "ID" are optional and only consulted when needed:

    In plan_structures_csv:
        "Plan name"       - RTDOSE file name, to disambiguate patients with
                              more than one dose (see getDoseIndex).
        "Prescribed dose (Gy)" - total prescribed dose (Gy).
        "Fraction size (Gy)"   - dose per fraction (Gy).
        "Fraction number"  - number of fractions.
        Supplying any two of the last three lets the third be derived (see
        getFractionation).

    In predictors_csv:
        "<structure> <metric>" - start_from: predictors only. One column per
                              dose metric the model uses, named as in the
                              model file (e.g. "Esophagus meanDose").
                              Values must already be fractionation-corrected
                              if the model requires correction.
        "<predictor>"     - one column per non-dose predictor the model lists,
                              named as in the model file (e.g. "gender",
                              "concurrentChemo"). Values are the numeric codes
                              from the model's "desc" (e.g. Female = 1).
        With raw data, only non-dose predictors are read from this file; dose
        metrics are computed from the images.

    In outcomes_csv:

    Args:
        csvPath (str): path to a CSV with an "ID" column matching the DICOM
            subdirectory names.

    Returns:
        pandas.DataFrame indexed by "ID".
    """
    df = pd.read_csv(csvPath, dtype=str)
    df.columns = df.columns.str.strip()
    if "ID" not in df.columns:
        raise ValueError(
            f"CSV must have an 'ID' column; found columns: {list(df.columns)}")
    duplicateIds = sorted(df.loc[df["ID"].duplicated(), "ID"].unique())
    if duplicateIds:
        raise ValueError(f"{csvPath} has duplicate IDs: {duplicateIds}")
    return df.set_index("ID")


def getDoseIndex(planC, patientId=None, patientInfo=None):
    """Return the index of the dose to use for this patient.

    If planC has no dose, None is returned. If it has exactly one dose, that
    dose is used. Otherwise patientInfo (a row of loadPatientInfo's result)
    must supply a "Plan name" value (RTDOSE file name), matched against each
    dose's doseFileName.

    Args:
        planC (cerr.plan_container.PlanC): patient's plan container.
        patientId (str): DICOM subdirectory name, used in error messages.
        patientInfo (pandas.Series or None): this patient's row from
            loadPatientInfo, required when planC has more than one dose.
    """
    numDoses = len(planC.dose)
    if numDoses == 0:
        return None
    if numDoses == 1:
        return 0

    dosePlanName = patientInfo.get("Plan name") if patientInfo is not None else None
    if dosePlanName is None or pd.isna(dosePlanName) or not str(dosePlanName).strip():
        raise ValueError(
            f"Found {numDoses} doses; provide a 'Plan name' entry for patient "
            f"{patientId!r} in the CSV to select which one to use.")

    dosePlanName = os.path.basename(str(dosePlanName))
    fileNames = [os.path.basename(str(d.doseFileName)) for d in planC.dose]
    matchIdxV = [i for i, fname in enumerate(fileNames) if fname == dosePlanName]

    if not matchIdxV:
        raise ValueError(
            f"Dose plan {dosePlanName!r} for patient {patientId!r} does not "
            f"match any of the {numDoses} dose files found: {fileNames}")
    if len(matchIdxV) > 1:
        raise ValueError(
            f"Dose plan {dosePlanName!r} for patient {patientId!r} matches "
            f"multiple doses: {[fileNames[i] for i in matchIdxV]}")
    return matchIdxV[0]


def getFractionation(patientInfo):
    """Return this patient's (fxSize, fxNum) from plan_structures_csv.

    A missing value is derived from "Prescribed dose (Gy)" and the other one.
    Either value is None if it can't be resolved.

    Args:
        patientInfo (pandas.Series or None): this patient's row from
            loadPatientInfo. None if no plan_structures_csv was given, or
            this patient has no row in it.
    """
    return _csvFrxSize(patientInfo), _csvFrxNum(patientInfo)

#============================================
# Helper functions to read CSVs
#============================================
def _resolveFile(dataDir, pattern, column):
    """Return the file in dataDir matching pattern (name or wildcard)."""
    if pattern is None:
        raise ValueError(f"No '{column}' given for this patient in plan_structures_csv.")
    matches = sorted(glob.glob(os.path.join(dataDir, pattern)))
    if len(matches) != 1:
        raise ValueError(
            f"'{column}' pattern {pattern!r} matched {len(matches)} files in "
            f"{dataDir} (expected exactly one): {matches}")
    return matches[0]


def _textField(patientInfo, column):
    if patientInfo is None or column not in patientInfo:
        return None
    value = patientInfo[column]
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return str(value).strip()


def _numericField(patientInfo, column):
    if patientInfo is None or column not in patientInfo:
        return None
    value = patientInfo[column]
    if value is None or (isinstance(value, float) and pd.isna(value)) or not str(value).strip():
        return None
    try:
        return float(value)
    except ValueError:
        raise ValueError(
            f"{patientInfo.name}: '{column}' must be a number, got {value!r}") from None


def _csvFrxSize(patientInfo):
    frxSize = _numericField(patientInfo, "Fraction size (Gy)")
    if frxSize is not None:
        return frxSize
    rx = _numericField(patientInfo, "Prescribed dose (Gy)")
    frxNum = _numericField(patientInfo, "Fraction number")
    return rx / frxNum if rx is not None and frxNum else None


def _csvFrxNum(patientInfo):
    frxNum = _numericField(patientInfo, "Fraction number")
    if frxNum is not None:
        return frxNum
    rx = _numericField(patientInfo, "Prescribed dose (Gy)")
    frxSize = _numericField(patientInfo, "Fraction size (Gy)")
    if rx is None or not frxSize:
        return None
    frxNum = rx / frxSize
    if abs(frxNum - round(frxNum)) > 1e-6:
        warnings.warn(f"{patientInfo.name}: fraction number derived from 'Prescribed dose (Gy)' "
                      f"/ 'Fraction size (Gy)' = {rx:g} / {frxSize:g} = {frxNum:.3f} is not a whole number.")
    return frxNum

