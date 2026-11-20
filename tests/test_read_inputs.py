"""Tests 6, 8, 9, 10: reading patient inputs (data_io/read_inputs.py)."""

import re
import warnings
from types import SimpleNamespace

import pandas as pd
import pytest

from validate.data_io.read_inputs import inferFileFormat, getFractionation, getDoseIndex


# 6. inferFileFormat tells DICOM from NIfTI/NRRD

def _writeDicom(path):
    # is_dicom only checks for the 128-byte preamble followed by "DICM"
    path.write_bytes(b"\0" * 128 + b"DICM")


@pytest.mark.parametrize("fileName", ["scan.nii", "scan.nii.gz", "scan.nrrd", "SCAN.NII.GZ"])
def test_imageFilesAreNiftiNrrd(tmp_path, fileName):
    (tmp_path / fileName).touch()
    assert inferFileFormat(tmp_path) == "nifti_nrrd"


def test_dicomFiles(tmp_path):
    _writeDicom(tmp_path / "CT1.dcm")
    _writeDicom(tmp_path / "RS1")         # DICOM files needn't have an extension
    (tmp_path / "notes.txt").write_text("not DICOM")
    assert inferFileFormat(tmp_path) == "dicom"


def test_mixedFormatsRaise(tmp_path):
    _writeDicom(tmp_path / "CT1.dcm")
    (tmp_path / "scan.nii.gz").touch()
    with pytest.raises(ValueError, match="holds both DICOM and NIfTI/NRRD"):
        inferFileFormat(tmp_path)


def _writeFiles(folder, names):
    for name in names:
        (folder / name).write_text("x")


@pytest.mark.parametrize("fileNames", [[], ["notes.txt"]], ids=["empty", "no image files"])
def test_noImageFilesRaise(tmp_path, fileNames):
    _writeFiles(tmp_path, fileNames)
    with pytest.raises(ValueError, match="No DICOM, NIfTI or NRRD files found"):
        inferFileFormat(tmp_path)


def test_subfoldersIgnored(tmp_path):
    (tmp_path / "scan.nii.gz").mkdir()    # a folder, not a file
    with pytest.raises(ValueError, match="No DICOM, NIfTI or NRRD files found"):
        inferFileFormat(tmp_path)


# 8. getFractionation fills in the missing value

def _row(**values):
    columns = {"rx": "Prescribed dose (Gy)", "size": "Fraction size (Gy)", "num": "Fraction number"}
    return pd.Series({columns[key]: value for key, value in values.items()}, name="pt1", dtype=object)


@pytest.mark.parametrize("row, expected", [
    (_row(rx="70", size="2", num="35"), (2.0, 35.0)),
    (_row(rx="70", num="35"), (2.0, 35.0)),
    (_row(rx="70", size="2"), (2.0, 35.0)),
    (_row(size="2", num="35"), (2.0, 35.0)),
    (_row(size="2"), (2.0, None)),
    (_row(rx="70"), (None, None)),
    (_row(rx="", size=" ", num=None), (None, None)),
    pytest.param(_row(rx="70", size="3"), (3.0, pytest.approx(70 / 3)),
                 marks=pytest.mark.filterwarnings("ignore:.*is not a whole number")),
], ids=["all given", "size from rx and num", "num from rx and size", "no rx",
        "size only", "rx only", "blank cells", "non-whole fraction number"])
def test_fractionation(row, expected):
    assert getFractionation(row) == expected


def test_noPlanRow():
    assert getFractionation(None) == (None, None)


@pytest.mark.parametrize("size, warned", [("3", True), ("2", False)],
                         ids=["70/3 fractions", "70/2 fractions"])
def test_warnsIfFractionNumberNotWhole(size, warned):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        getFractionation(_row(rx="70", size=size))
    assert any("is not a whole number" in str(w.message) for w in caught) == warned


# 9. A non-numeric value gives a clear error

@pytest.mark.parametrize("row, column", [
    (_row(size="two"), "Fraction size (Gy)"),
    (_row(rx="70 Gy", num="35"), "Prescribed dose (Gy)"),
    (_row(rx="70", size="2", num="35 fx"), "Fraction number"),
])
def test_nonNumericValueRaises(row, column):
    with pytest.raises(ValueError, match=re.escape(f"pt1: '{column}' must be a number")):
        getFractionation(row)


# 10. getDoseIndex picks the dose to use

def _planC(*doseFileNames):
    return SimpleNamespace(dose=[SimpleNamespace(doseFileName=name) for name in doseFileNames])


def _planRow(planName):
    return pd.Series({"Plan name": planName}, name="pt1", dtype=object)


def test_singleDoseUsed():
    assert getDoseIndex(_planC("/pt1/RD1.dcm")) == 0


def test_noDoseReturnsNone():
    # run.applyAutoSegToCohort uses the first scan when no dose is found
    assert getDoseIndex(_planC()) is None


@pytest.mark.parametrize("planName", ["RD2.dcm", "/elsewhere/RD2.dcm"],
                         ids=["file name", "path (only the file name is matched)"])
def test_planNameSelectsDose(planName):
    planC = _planC("/pt1/RD1.dcm", "/pt1/RD2.dcm", "/pt1/RD3.dcm")
    assert getDoseIndex(planC, "pt1", _planRow(planName)) == 1


@pytest.mark.parametrize("planRow", [None, _planRow(None), _planRow("  ")],
                         ids=["no plan row", "no plan name", "blank plan name"])
def test_severalDosesNeedPlanName(planRow):
    with pytest.raises(ValueError, match="Found 2 doses; provide a 'Plan name'"):
        getDoseIndex(_planC("RD1.dcm", "RD2.dcm"), "pt1", planRow)


def test_unmatchedPlanNameRaises():
    with pytest.raises(ValueError, match="does not match any of the 2 dose files"):
        getDoseIndex(_planC("RD1.dcm", "RD2.dcm"), "pt1", _planRow("RD9.dcm"))


def test_planNameMatchingSeveralDosesRaises():
    with pytest.raises(ValueError, match="matches multiple doses"):
        getDoseIndex(_planC("/a/RD1.dcm", "/b/RD1.dcm"), "pt1", _planRow("RD1.dcm"))


# discoverPatients skips analysis folders inside the cohort folder

def test_analysisFoldersNotPatients(tmp_path):
    from validate.data_io.read_inputs import discoverPatients
    (tmp_path / "pt1").mkdir()
    (tmp_path / "analysis_Xerostomia (grade 2+)").mkdir()
    (tmp_path / "analysis_Xerostomia (grade 2+)" / "analysis.yaml").write_text("{}")
    (tmp_path / "_autoseg_logs").mkdir()
    assert discoverPatients(tmp_path) == [("pt1", str(tmp_path / "pt1"))]
