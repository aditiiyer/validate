"""Test 13: a patient whose record can't be built is logged and skipped (data_io/build_capsule.py)."""

import pytest

from validate.core.data_capsule import DataCapsule
from validate.data_io.build_capsule import buildPatientRecords


class FakeErrorLog:
    def __init__(self):
        self.lines = []

    def error(self, patientId, message):
        self.lines.append((patientId, message))


@pytest.fixture
def capsule(tmp_path):
    """A NIfTI cohort: pt1 is fine, pt2's folder is empty, pt3 has a non-numeric plan CSV cell."""
    cohortDir = tmp_path / "cohort"
    for ptId in ("pt1", "pt2", "pt3"):
        (cohortDir / ptId).mkdir(parents=True)
    (cohortDir / "pt1" / "scan.nii.gz").touch()
    (cohortDir / "pt3" / "scan.nii.gz").touch()
    planCsv = tmp_path / "plan.csv"
    planCsv.write_text("ID,Fraction size (Gy)\npt1,2\npt3,two\n")
    return DataCapsule(start_from="nifti", model={"name": "Test model", "file": None},
                       cohort_dir=str(cohortDir), plan_structures_csv=str(planCsv))


def test_failedPatientsSkippedAndLogged(capsule):
    errorLog = FakeErrorLog()
    records = buildPatientRecords(capsule, errorLog=errorLog)

    assert [record.pt_id for record in records] == ["pt1"]
    assert records[0].plan_info.fx_size == 2.0
    assert [ptId for ptId, _ in errorLog.lines] == ["pt2", "pt3"]
    for _, message in errorLog.lines:
        assert message.startswith("Could not build patient record; skipped:")
    assert "No DICOM, NIfTI or NRRD files found" in errorLog.lines[0][1]
    assert "'Fraction size (Gy)' must be a number" in errorLog.lines[1][1]


def test_failureRaisesWithoutErrorLog(capsule):
    with pytest.raises(ValueError, match="No DICOM, NIfTI or NRRD files found"):
        buildPatientRecords(capsule)
