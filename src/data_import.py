"""Cohort discovery, plan selection, and fractionation correction.

Cohort organization:

    cohort_dir/
        pt001/   (CT, RTDOSE, RTSTRUCT DICOM files)
        pt002/
        ...

Patient metadata (plan name and fractionation correction) comes from an optional patient info CSV.
"""

import os
import json
import pandas as pd

from cerr import plan_container as pc
from cerr.roe import dosimetric_models as doseModels


def discoverPatients(cohortDir):
    """List patient subdirectories of a cohort directory.

    Args:
        cohortDir (str): Path to the parent directory holding one DICOM
            subdirectory per patient.

    Returns:
        list of (patientId, dicomDir) tuples, sorted by patientId. Leading-
        underscore subdirectories (e.g. "_autoseg_logs") are excluded --
        those hold validate's own logs, not patient data.
    """
    entries = []
    for name in sorted(os.listdir(cohortDir)):
        if name.startswith("_"):
            continue
        path = os.path.join(cohortDir, name)
        if os.path.isdir(path):
            entries.append((name, path))
    return entries


def loadPatientPlanC(dicomDir):
    """Load a single patient's planC from a DICOM directory."""
    return pc.loadDcmDir(dicomDir)


PATIENT_INFO_COLUMNS = ["ID", "Plan name", "Prescribed dose",
                        "Fraction size", "Fraction number"]


def loadPatientInfo(csvPath):
    """Read the optional per-patient info CSV, indexed by patient ID.

    All columns besides "ID" are optional and only consulted when needed:
        "Plan name"       - RTDOSE file name, to disambiguate patients with
                              more than one dose (see getDoseIndex).
        "Prescribed dose"  - total prescribed dose (Gy).
        "Fraction size"    - dose per fraction (Gy).
        "Fraction number"  - number of fractions.
    Supplying any two of the last three lets the third be derived (see
    getFractionationInputs in this module).

    Args:
        csvPath (str): path to a CSV with an "ID" column matching the DICOM
            subdirectory names.

    Returns:
        pandas.DataFrame indexed by "ID".
    """
    df = pd.read_csv(csvPath, dtype=str)
    if "ID" not in df.columns:
        raise ValueError(
            f"Patient info CSV must have an 'ID' column; found columns: {list(df.columns)}")
    return df.set_index("ID")


def getDoseIndex(planC, patientId=None, patientInfo=None):
    """Return the index of the dose to use for this patient.

    If planC has exactly one dose, that dose is used. Otherwise patientInfo
    (a row of loadPatientInfo's result) must supply a "Plan name" value
    (RTDOSE file name), matched against each dose's doseFileName.

    Args:
        planC (cerr.plan_container.PlanC): patient's plan container.
        patientId (str): DICOM subdirectory name, used in error messages.
        patientInfo (pandas.Series or None): this patient's row from
            loadPatientInfo, required when planC has more than one dose.

    Raises:
        ValueError: if planC has no dose, or has more than one dose and the
            matching dose plan cannot be resolved from patientInfo.
    """
    numDoses = len(planC.dose)
    if numDoses == 0:
        raise ValueError("No dose found in plan.")
    if numDoses == 1:
        return 0

    dosePlanName = patientInfo.get("Plan name") if patientInfo is not None else None
    if dosePlanName is None or pd.isna(dosePlanName) or not str(dosePlanName).strip():
        raise ValueError(
            f"Found {numDoses} doses; provide a 'Plan name' entry for patient "
            f"{patientId!r} in the patient info CSV to select which one to use.")

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


def getFractionCorrectionType(modelFile):
    """Return the fractionation-correction type a model requires.

    Args:
        modelFile (str): built-in model name or path to a model parameter
            JSON file (same accepted forms as dosimetric_models.run).

    Returns:
        "frxSize", "frxNum", or None if the model needs no correction.
    """
    if isinstance(modelFile, str) and ".json" not in modelFile:
        modelFile = doseModels.mapModelToFile(modelFile)
    with open(modelFile, "r") as f:
        model = json.load(f)

    if model.get("fractionCorrect", "No").strip().lower() != "yes":
        return None

    correctionType = model.get("correctionType", "").strip().lower()
    if correctionType == "frxsize":
        return "frxSize"
    if correctionType == "frxnum":
        return "frxNum"
    raise ValueError(
        f"Model requires fractionation correction but has an unrecognized "
        f"correctionType: {model.get('correctionType')!r}")


def _numericField(patientInfo, column):
    if patientInfo is None or column not in patientInfo:
        return None
    value = patientInfo[column]
    if value is None or (isinstance(value, float) and pd.isna(value)) or not str(value).strip():
        return None
    return float(value)


def _csvFrxSize(patientInfo):
    frxSize = _numericField(patientInfo, "Fraction size")
    if frxSize is not None:
        return frxSize
    rx = _numericField(patientInfo, "Prescribed dose")
    frxNum = _numericField(patientInfo, "Fraction number")
    return rx / frxNum if rx is not None and frxNum else None


def _csvFrxNum(patientInfo):
    frxNum = _numericField(patientInfo, "Fraction number")
    if frxNum is not None:
        return frxNum
    rx = _numericField(patientInfo, "Prescribed dose")
    frxSize = _numericField(patientInfo, "Fraction size")
    return rx / frxSize if rx is not None and frxSize else None


def getFractionationInputs(patientInfo, correctionType):
    """Resolve (fSizeIn, fNumIn) to pass to dosimetric_models.run().

    patientInfo must supply "Fraction size" (for a "frxSize"-correcting
    model) or "Fraction number" (for "frxNum"), or both "Prescribed dose"
    and the other of the two so the required value can be derived.

    Args:
        patientInfo (pandas.Series or None): this patient's row from
            cohort.loadPatientInfo. None if no patient info CSV was given,
            or this patient has no row in it.
        correctionType: result of getFractionCorrectionType() for the model
            being applied.

    Returns:
        (fSizeIn, fNumIn) tuple; the entry not required by correctionType is
        None. Both are None when correctionType is None.

    Raises:
        ValueError: correctionType requires a value that isn't resolvable
        from patientInfo (including patientInfo being None, i.e. no patient
        info CSV was provided, or this patient has no row in it).
    """
    if correctionType is None:
        return None, None

    if correctionType == "frxSize":
        frxSize = _csvFrxSize(patientInfo)
        if frxSize is None:
            raise ValueError(
                "Model requires fraction-size correction; provide 'Fraction "
                "size' (or both 'Prescribed dose' and 'Fraction number') for "
                "this patient in the patient info CSV.")
        return frxSize, None

    if correctionType == "frxNum":
        frxNum = _csvFrxNum(patientInfo)
        if frxNum is None:
            raise ValueError(
                "Model requires fraction-number correction; provide "
                "'Fraction number' (or both 'Prescribed dose' and 'Fraction "
                "size') for this patient in the patient info CSV.")
        return None, frxNum

    raise ValueError(f"Unknown correctionType: {correctionType!r}")
