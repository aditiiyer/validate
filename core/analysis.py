"""Create, read, or modify analysis.yaml, which contains the user configurations for an analysis.

analysis.yaml:

    input:
      start_from: dicom            # dicom | nifti | nrrd | predictors
      data_dir: /data/cohort       # null if start_from: predictors
      predictors_csv: null
      plan_structures_csv: null
      outcomes_csv: null
    compute:
      device: cpu                  # cpu | gpu
    model:
      name: Xerostomia (grade 2+)  # ROE model name
      file: /path/to/Xerostomia (grade 2+).json   # filled in automatically for built-in models
    segment:
      ai_models: [CT_HeadAndNeck_OARs]   # AI models to run (cerr.ai_models names)
      install_dir: /models               # required if ai_models is not empty
    structures:
      Parotids: {source: existing, name: Parotid_Total}
      Oral cavity: {source: derive}
"""

import hashlib
import os
import yaml

from cerr.roe import dosimetric_models as doseModels
from cerr.ai_models import install_utils

from validate.core.data_capsule import DataCapsule


# VALID FIELDS AND SETTINGS
FILE_NAME = "analysis.yaml"

TOP_LEVEL_KEYS = {"input", "compute", "model", "segment", "structures"}
SECTION_KEYS = {
    "input": {"start_from", "data_dir", "predictors_csv", "plan_structures_csv", "outcomes_csv"},
    "compute": {"device"},
    "model": {"name", "file"},
    "segment": {"ai_models", "install_dir"},
}
RAW_DATA_FORMATS = ("dicom", "nifti", "nrrd")
START_FROM_VALUES = RAW_DATA_FORMATS + ("predictors",)
DEVICE_VALUES = ("cpu", "gpu")
STRUCTURE_SOURCES = ("existing", "derive")

# The settings each tab's results depend on.
# A change to a tab's settings clears that tab's results (see tabSettings).
TAB_SETTINGS = {
    "segment": {"input": ("start_from", "data_dir"), "compute": ("device",),
                "segment": ("ai_models", "install_dir")},
    "model": {"input": None, "structures": None},
}


def checkSettings(analysisDict):
    """Check analysis.yaml's contents."""
    problems = []
    if not isinstance(analysisDict, dict):
        found = "it is empty" if analysisDict is None else f"found {type(analysisDict).__name__}"
        raise ValueError(f"Invalid analysis.yaml: expected a mapping of settings, but {found}.")
    inputs = analysisDict.get("input") or {}
    compute = analysisDict.get("compute") or {}
    segment = analysisDict.get("segment") or {}
    structures = analysisDict.get("structures") or {}
    startFrom = inputs.get("start_from")

    # Required keys
    if startFrom is None:
        problems.append("input.start_from is required.")
    if analysisDict.get("model") is None:
        problems.append("model is required.")

    # Unknown keys
    for key in sorted(set(analysisDict) - TOP_LEVEL_KEYS):
        problems.append(f"Unknown key '{key}'.")
    for section, allowedKeys in SECTION_KEYS.items():
        sectionDict = analysisDict.get(section)
        if isinstance(sectionDict, dict):
            for key in sorted(set(sectionDict) - allowedKeys):
                problems.append(f"Unknown key '{section}.{key}'.")

    # Allowed values
    if startFrom is not None and startFrom not in START_FROM_VALUES:
        problems.append(f"input.start_from must be one of {list(START_FROM_VALUES)}, got {startFrom!r}.")
    device = compute.get("device", "cpu")
    if device not in DEVICE_VALUES:
        problems.append(f"compute.device must be one of {list(DEVICE_VALUES)}, got {device!r}.")

    # Check restricted fields
    if startFrom == "predictors":
        if inputs.get("data_dir") is not None:
            problems.append("input.data_dir must be null when start_from is 'predictors'.")
        if inputs.get("predictors_csv") is None:
            problems.append("input.predictors_csv is required when start_from is 'predictors'.")
        if inputs.get("plan_structures_csv") is not None:
            problems.append("input.plan_structures_csv applies to raw data only; "
                            "it must be null when start_from is 'predictors'.")
        if structures:
            problems.append("structures apply to raw data only; "
                            "they must be empty when start_from is 'predictors'.")
        if segment.get("ai_models"):
            problems.append("segment.ai_models apply to raw data only; "
                            "they must be empty when start_from is 'predictors'.")
    elif startFrom in RAW_DATA_FORMATS:
        if inputs.get("data_dir") is None:
            problems.append(f"input.data_dir is required when start_from is {startFrom!r}.")

    # AI models
    aiModels = segment.get("ai_models") or []
    if not isinstance(aiModels, list):
        problems.append(f"segment.ai_models must be a list, got {aiModels!r}.")
        aiModels = []
    for aiModel in aiModels:
        try:
            install_utils.getModel(aiModel)
        except ValueError as exc:
            problems.append(f"segment.ai_models: {exc}")
    if aiModels and segment.get("install_dir") is None:
        problems.append("segment.install_dir is required when segment.ai_models is not empty.")

    # Structure sources
    for structName, recipe in structures.items():
        source = (recipe or {}).get("source")
        if source not in STRUCTURE_SOURCES:
            problems.append(f"structures.{structName}.source must be one of "
                            f"{list(STRUCTURE_SOURCES)}, got {source!r}.")

    if problems:
        raise ValueError("Invalid analysis.yaml:\n  - " + "\n  - ".join(problems))


def toAnalysisDict(dataCapsule):
    """Returns the analysis-level fields of dataCapsule.
    """
    model = dict(dataCapsule.model)
    if not model.get("file"):
        model["file"] = doseModels.mapModelToFile(model["name"])

    analysisDict = {
        "input": {
            "start_from": dataCapsule.start_from,
            "data_dir": dataCapsule.cohort_dir,
            "predictors_csv": dataCapsule.predictors_csv,
            "plan_structures_csv": dataCapsule.plan_structures_csv,
            "outcomes_csv": dataCapsule.outcomes_csv,
        },
        "compute": {"device": dataCapsule.device},
        "model": {"name": model.get("name"), "file": model["file"]},
        "segment": {"ai_models": list(dataCapsule.ai_models), "install_dir": dataCapsule.ai_install_dir},
        "structures": dataCapsule.structures,
    }
    return analysisDict


def readSettings(analysisDir):
    """Return the settings in analysisDir's analysis.yaml, or None if there are none yet."""
    path = os.path.join(analysisDir, FILE_NAME)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return yaml.safe_load(f)


def saveSettings(analysisDict, analysisDir):
    """Write analysisDict to analysisDir's analysis.yaml, replacing any earlier settings.

    Only called once the user has confirmed the changes (see diffSettings) and the
    settings have been checked.

    Returns:
        str: path to analysis.yaml.
    """
    analysisDict = {**analysisDict}
    model = dict(analysisDict.get("model") or {})
    if model.get("name") and not model.get("file"):
        model["file"] = doseModels.mapModelToFile(model["name"])
        analysisDict["model"] = model
    checkSettings(analysisDict)

    os.makedirs(analysisDir, exist_ok=True)
    path = os.path.join(analysisDir, FILE_NAME)
    # Write to a temporary file and rename, so a crash never leaves a partial file
    tmpPath = path + ".tmp"
    with open(tmpPath, "w") as f:
        yaml.safe_dump(analysisDict, f, sort_keys=False)
    os.replace(tmpPath, path)
    return path


def diffSettings(old, new):
    """List the settings that differ between old and new (either may be None).

    Returns:
        list of (key, oldValue, newValue), key in dotted form (e.g. "model.name"),
        in the order the keys appear. A value missing on one side is None.
    """
    changes = []
    _diff(old or {}, new or {}, "", changes)
    return changes


def _diff(old, new, prefix, changes):
    for key in list(old) + [k for k in new if k not in old]:
        oldVal, newVal = old.get(key), new.get(key)
        path = f"{prefix}{key}"
        # Sections are compared key by key, even when one side has no such section yet
        bothDicts = isinstance(oldVal, dict) and isinstance(newVal, dict)
        newSection = not prefix and (oldVal is None or newVal is None) and isinstance(oldVal or newVal, dict)
        if bothDicts or newSection:
            _diff(oldVal or {}, newVal or {}, path + ".", changes)
        elif oldVal != newVal:
            changes.append((path, oldVal, newVal))


def tabSettings(analysisDict, tab):
    """The part of the settings a tab's results depend on (see TAB_SETTINGS).

    Args:
        analysisDict (dict): the analysis settings.
        tab (str): "segment" or "model".

    Returns:
        dict: {section: {key: value}} or {section: whole section}.
    """
    selected = {}
    for section, keys in TAB_SETTINGS[tab].items():
        sectionDict = (analysisDict or {}).get(section) or {}
        selected[section] = sectionDict if keys is None else {key: sectionDict.get(key) for key in keys}
    return selected


def toDataCapsule(path):
    """Read and translate analysis.yaml into DataCapsule."""
    with open(path, "r") as f:
        analysisDict = yaml.safe_load(f)
    checkSettings(analysisDict)
    inputs = analysisDict.get("input", {})
    return DataCapsule(
        start_from=inputs["start_from"],
        model=analysisDict["model"],
        device=(analysisDict.get("compute") or {}).get("device", "cpu"),
        ai_models=list((analysisDict.get("segment") or {}).get("ai_models") or []),
        ai_install_dir=(analysisDict.get("segment") or {}).get("install_dir"),
        cohort_dir=inputs.get("data_dir"),
        predictors_csv=inputs.get("predictors_csv"),
        plan_structures_csv=inputs.get("plan_structures_csv"),
        outcomes_csv=inputs.get("outcomes_csv"),
        structures=analysisDict.get("structures") or {},
    )


def analysisHash(path):
    """Return the SHA-256 of analysis.yaml's exact bytes, for run_log.yaml."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
