"""Apply a cerr.roe dosimetric model to every patient in a cohort.
"""

import json
import pandas as pd

from cerr.roe import dosimetric_models as doseModels

from validate.data_io.data_import import (discoverPatients, loadPatientPlanC, getDoseIndex,
                                 loadPatientInfo, getFractionation)
from validate.seg.structures import applyStructureNameMap



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


def getFractionationInputs(fxSize, fxNum, correctionType):
    """Return (fSizeIn, fNumIn) for dosimetric_models.run(), checking that the
    value the model's correction needs is available.

    Args:
        fxSize (float or None): fraction size, from data_import.getFractionation.
        fxNum (float or None): fraction number, from data_import.getFractionation.
        correctionType: result of getFractionCorrectionType() for the model
            being applied.

    Returns:
        (fSizeIn, fNumIn) tuple; the entry not required by correctionType is
        None. Both are None when correctionType is None.
    """
    if correctionType is None:
        return None, None

    if correctionType == "frxSize":
        if fxSize is None:
            raise ValueError(
                "Model requires fraction-size correction; provide 'Fraction "
                "size (Gy)' (or both 'Prescribed dose (Gy)' and 'Fraction "
                "number') for this patient in plan_structures_csv.")
        return fxSize, None

    if correctionType == "frxNum":
        if fxNum is None:
            raise ValueError(
                "Model requires fraction-number correction; provide "
                "'Fraction number' (or both 'Prescribed dose (Gy)' and "
                "'Fraction size (Gy)') for this patient in plan_structures_csv.")
        return None, fxNum

    raise ValueError(f"Unknown correctionType: {correctionType!r}")
