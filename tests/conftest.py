"""Shared test setup.

Run from the validate folder with:  python -m pytest tests/
"""

import sys
from pathlib import Path

import pytest
import yaml

# validate isn't pip-installed; make the folder holding the package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

RAW_SETTINGS = {
    "input": {"start_from": "dicom", "data_dir": "/data/cohort", "predictors_csv": None,
              "plan_structures_csv": None, "outcomes_csv": None},
    "compute": {"device": "cpu"},
    "model": {"name": "Test model", "file": None},
    "segment": {"ai_models": [], "install_dir": None},
    "structures": {},
}


def writeYaml(path, data):
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    return path


@pytest.fixture
def analysisDir(tmp_path):
    """An analysis folder holding analysis.yaml and a model file (model.json)."""
    analysisDir = tmp_path / "analysis"
    analysisDir.mkdir()
    (analysisDir / "model.json").write_text('{"function": "logitFn", "parameters": {}}')
    writeYaml(analysisDir / "analysis.yaml", RAW_SETTINGS)
    return analysisDir
