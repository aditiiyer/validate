"""Tests 1-2 and the settings helpers: reading, checking and saving analysis.yaml (core/analysis.py)."""

import copy

import pytest
import yaml

from validate.core import analysis
from validate.core.data_capsule import DataCapsule

from conftest import RAW_SETTINGS, writeYaml


# 1. A valid analysis.yaml loads into a DataCapsule

def test_rawSettingsLoad(tmp_path):
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["input"]["plan_structures_csv"] = "/data/plan.csv"
    settings["compute"] = {"device": "gpu"}
    settings["segment"] = {"ai_models": ["CT_HeadAndNeck_OARs"], "install_dir": "/models"}
    settings["structures"] = {"Parotids": {"source": "existing", "name": "Parotid_Total"},
                              "Oral cavity": {"source": "derive"}}
    capsule = analysis.toDataCapsule(writeYaml(tmp_path / "analysis.yaml", settings))

    assert isinstance(capsule, DataCapsule)
    assert capsule.start_from == "dicom"
    assert capsule.cohort_dir == "/data/cohort"
    assert capsule.plan_structures_csv == "/data/plan.csv"
    assert capsule.predictors_csv is None
    assert capsule.device == "gpu"
    assert capsule.ai_models == ["CT_HeadAndNeck_OARs"]
    assert capsule.ai_install_dir == "/models"
    assert capsule.model == {"name": "Test model", "file": None}
    assert capsule.structures == settings["structures"]
    assert capsule.patients == {}


def test_predictorsSettingsLoad(tmp_path):
    settings = {"input": {"start_from": "predictors", "data_dir": None,
                          "predictors_csv": "/data/predictors.csv"},
                "model": {"name": "Test model"}}
    capsule = analysis.toDataCapsule(writeYaml(tmp_path / "analysis.yaml", settings))

    assert capsule.start_from == "predictors"
    assert capsule.cohort_dir is None
    assert capsule.predictors_csv == "/data/predictors.csv"
    assert capsule.device == "cpu"          # default when compute is left out
    assert capsule.ai_models == []          # default when segment is left out
    assert capsule.structures == {}


# 2. Clear errors for invalid settings

def _set(path, value):
    """Return a function that sets settings[a][b]... = value (path "a.b")."""
    def edit(settings):
        *parents, key = path.split(".")
        target = settings
        for parent in parents:
            target = target[parent]
        target[key] = value
    return edit


def _delete(path):
    def edit(settings):
        *parents, key = path.split(".")
        target = settings
        for parent in parents:
            target = target[parent]
        del target[key]
    return edit


def _predictorsMode(settings):
    settings["input"].update(start_from="predictors", data_dir=None,
                             predictors_csv="/data/predictors.csv")


INVALID_CASES = {
    "missing start_from": (_delete("input.start_from"), "input.start_from is required."),
    "missing model": (_delete("model"), "model is required."),
    "unknown top-level key": (_set("extra", 1), "Unknown key 'extra'."),
    "unknown section key": (_set("input.foo", 1), "Unknown key 'input.foo'."),
    "old compute.ai_install_dir key": (_set("compute.ai_install_dir", "/models"),
                                       "Unknown key 'compute.ai_install_dir'."),
    "bad start_from": (_set("input.start_from", "dcm"), "input.start_from must be one of"),
    "bad device": (_set("compute.device", "tpu"), "compute.device must be one of"),
    "raw data without data_dir": (_set("input.data_dir", None), "input.data_dir is required"),
    "predictors with data_dir": (lambda s: (_predictorsMode(s), _set("input.data_dir", "/x")(s)),
                                 "input.data_dir must be null"),
    "predictors without predictors_csv": (lambda s: (_predictorsMode(s), _set("input.predictors_csv", None)(s)),
                                          "input.predictors_csv is required"),
    "predictors with ai_models": (lambda s: (_predictorsMode(s),
                                             _set("segment", {"ai_models": ["CT_HeadAndNeck_OARs"],
                                                              "install_dir": "/models"})(s)),
                                  "segment.ai_models apply to raw data only"),
    "ai_models without install_dir": (_set("segment.ai_models", ["CT_HeadAndNeck_OARs"]),
                                      "segment.install_dir is required"),
    "ai_models not a list": (lambda s: (_set("segment.ai_models", "CT_HeadAndNeck_OARs")(s),
                                        _set("segment.install_dir", "/models")(s)),
                             "segment.ai_models must be a list"),
    "unknown ai model": (lambda s: (_set("segment.ai_models", ["NoSuchModel"])(s),
                                    _set("segment.install_dir", "/models")(s)),
                         "segment.ai_models: Unknown model: 'NoSuchModel'"),
    "ai model not supported via pyCERR": (lambda s: (_set("segment.ai_models", ["CT_Lung_SMIT"])(s),
                                                     _set("segment.install_dir", "/models")(s)),
                                          "is not yet supported via pyCERR"),
    "bad structure source": (_set("structures", {"Parotids": {"source": "ai"}}),
                             "structures.Parotids.source must be one of ['existing', 'derive']"),
}


@pytest.mark.parametrize("edit, message", INVALID_CASES.values(), ids=INVALID_CASES.keys())
def test_invalidSettingsRaise(edit, message):
    settings = copy.deepcopy(RAW_SETTINGS)
    edit(settings)
    with pytest.raises(ValueError, match="Invalid analysis.yaml") as excInfo:
        analysis.checkSettings(settings)
    assert message in str(excInfo.value)


def test_validSettingsPass():
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["segment"] = {"ai_models": ["CT_HeadAndNeck_OARs"], "install_dir": "/models"}
    settings["structures"] = {"Parotids": {"source": "existing", "name": "Parotid_Total"},
                              "Oral cavity": {"source": "derive"}}
    analysis.checkSettings(settings)


def test_emptyFileRaises(tmp_path):
    path = tmp_path / "analysis.yaml"
    path.write_text("")
    with pytest.raises(ValueError, match="it is empty"):
        analysis.toDataCapsule(path)


def test_nonMappingRaises():
    with pytest.raises(ValueError, match="found list"):
        analysis.checkSettings(["dicom"])


def test_allProblemsReportedTogether():
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["compute"]["device"] = "tpu"
    settings["extra"] = 1
    with pytest.raises(ValueError) as excInfo:
        analysis.checkSettings(settings)
    assert "compute.device must be one of" in str(excInfo.value)
    assert "Unknown key 'extra'." in str(excInfo.value)


# Reading and saving settings

def test_readSettingsWithNoFile(tmp_path):
    assert analysis.readSettings(tmp_path) is None


def test_saveSettingsWritesAndReadsBack(tmp_path):
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["model"]["file"] = "/models/test.json"
    path = analysis.saveSettings(settings, tmp_path / "analysis")

    assert path == str(tmp_path / "analysis" / analysis.FILE_NAME)
    assert analysis.readSettings(tmp_path / "analysis") == settings
    assert not (tmp_path / "analysis" / (analysis.FILE_NAME + ".tmp")).exists()


def test_saveSettingsReplacesEarlierSettings(tmp_path):
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["model"]["file"] = "/models/test.json"
    analysis.saveSettings(settings, tmp_path)
    settings["compute"]["device"] = "gpu"
    analysis.saveSettings(settings, tmp_path)
    assert analysis.readSettings(tmp_path)["compute"]["device"] == "gpu"


def test_saveSettingsFillsBuiltInModelFile(tmp_path):
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["model"] = {"name": "Xerostomia (grade 2+)", "file": None}
    analysis.saveSettings(settings, tmp_path)
    modelFile = analysis.readSettings(tmp_path)["model"]["file"]
    assert modelFile.endswith(".json")
    assert settings["model"]["file"] is None        # the caller's dict is left unchanged


def test_saveSettingsRefusesInvalidSettings(tmp_path):
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["model"]["file"] = "/models/test.json"
    settings["compute"]["device"] = "tpu"
    with pytest.raises(ValueError, match="compute.device must be one of"):
        analysis.saveSettings(settings, tmp_path)
    assert analysis.readSettings(tmp_path) is None


# diffSettings: what the save pop-up lists

def test_noChanges():
    assert analysis.diffSettings(RAW_SETTINGS, copy.deepcopy(RAW_SETTINGS)) == []


def test_changesListedByKey():
    new = copy.deepcopy(RAW_SETTINGS)
    new["model"]["name"] = "Dysphagia"
    new["segment"]["ai_models"] = ["CT_HeadAndNeck_OARs"]
    new["structures"] = {"SCRR": {"source": "derive"}}
    assert analysis.diffSettings(RAW_SETTINGS, new) == [
        ("model.name", "Test model", "Dysphagia"),
        ("segment.ai_models", [], ["CT_HeadAndNeck_OARs"]),
        ("structures.SCRR", None, {"source": "derive"}),
    ]


def test_removedKeyListed():
    old = copy.deepcopy(RAW_SETTINGS)
    old["structures"] = {"Parotids": {"source": "existing", "name": "Parotid_Total"}}
    assert analysis.diffSettings(old, RAW_SETTINGS) == [
        ("structures.Parotids", {"source": "existing", "name": "Parotid_Total"}, None)]


def test_noEarlierSettings():
    changes = analysis.diffSettings(None, RAW_SETTINGS)
    assert ("compute.device", None, "cpu") in changes
    assert ("model.name", None, "Test model") in changes


# tabSettings: what each tab's results depend on

def test_segmentTabSettings():
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["segment"] = {"ai_models": ["CT_HeadAndNeck_OARs"], "install_dir": "/models"}
    assert analysis.tabSettings(settings, "segment") == {
        "input": {"start_from": "dicom", "data_dir": "/data/cohort", "plan_structures_csv": None},
        "compute": {"device": "cpu"},
        "segment": {"ai_models": ["CT_HeadAndNeck_OARs"], "install_dir": "/models"},
    }


def test_modelTabSettings():
    settings = copy.deepcopy(RAW_SETTINGS)
    settings["structures"] = {"SCRR": {"source": "derive"}}
    assert analysis.tabSettings(settings, "model") == {
        "input": settings["input"],
        "structures": {"SCRR": {"source": "derive"}},
    }


@pytest.mark.parametrize("key, value, changedTabs", [
    ("model.name", "Dysphagia", set()),     # a new model is a new analysis, in its own folder
    ("structures", {"SCRR": {"source": "derive"}}, {"model"}),
    ("input.plan_structures_csv", "/data/plan.csv", {"segment", "model"}),
    ("input.predictors_csv", "/data/predictors.csv", {"model"}),
    ("compute.device", "gpu", {"segment"}),
    ("segment.ai_models", ["CT_HeadAndNeck_OARs"], {"segment"}),
    ("input.data_dir", "/data/other", {"segment", "model"}),
])
def test_changeAffectsTabs(key, value, changedTabs):
    new = copy.deepcopy(RAW_SETTINGS)
    _set(key, value)(new)
    changed = {tab for tab in ("segment", "model")
               if analysis.tabSettings(RAW_SETTINGS, tab) != analysis.tabSettings(new, tab)}
    assert changed == changedTabs
