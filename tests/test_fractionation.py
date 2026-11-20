"""Fractionation correction (modeling/apply_model.py): which correction a model needs,
and the fraction size or number passed to the dosimetric model for it."""

import json

import pytest

from cerr.roe import dosimetric_models as doseModels

from validate.modeling.apply_model import getFractionCorrectionType, getFractionationInputs


def _modelFile(tmp_path, **fields):
    path = tmp_path / "model.json"
    path.write_text(json.dumps({"function": "logitFn", "parameters": {}, **fields}))
    return str(path)


@pytest.mark.parametrize("fields, expected", [
    ({"fractionCorrect": "Yes", "correctionType": "frxSize"}, "frxSize"),
    ({"fractionCorrect": "yes", "correctionType": "frxnum"}, "frxNum"),
    ({"fractionCorrect": "No", "correctionType": "frxSize"}, None),
    ({}, None),
], ids=["fraction size", "fraction number (any case)", "correction off", "not specified"])
def test_correctionType(tmp_path, fields, expected):
    assert getFractionCorrectionType(_modelFile(tmp_path, **fields)) == expected


def test_unknownCorrectionTypeRaises(tmp_path):
    modelFile = _modelFile(tmp_path, fractionCorrect="Yes", correctionType="BED")
    with pytest.raises(ValueError, match="unrecognized correctionType: 'BED'"):
        getFractionCorrectionType(modelFile)


@pytest.mark.parametrize("modelName", doseModels.listModels())
def test_builtInModelsHaveKnownCorrection(modelName):
    """Every model shipped with pyCERR declares a correction validate can apply."""
    assert getFractionCorrectionType(modelName) in (None, "frxSize", "frxNum")


@pytest.mark.parametrize("correctionType, expected", [
    ("frxSize", (2.0, None)),
    ("frxNum", (None, 35.0)),
    (None, (None, None)),
], ids=["fraction size", "fraction number", "no correction"])
def test_onlyTheNeededValueIsPassed(correctionType, expected):
    assert getFractionationInputs(2.0, 35.0, correctionType) == expected


@pytest.mark.parametrize("fxSize, fxNum, correctionType, column", [
    (None, 35.0, "frxSize", "Fraction size"),
    (2.0, None, "frxNum", "Fraction number"),
], ids=["fraction size missing", "fraction number missing"])
def test_missingValueRaises(fxSize, fxNum, correctionType, column):
    with pytest.raises(ValueError, match=f"provide '{column}"):
        getFractionationInputs(fxSize, fxNum, correctionType)
