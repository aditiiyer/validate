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
    structures:
      Parotids: {source: existing, name: Parotid_Total}
"""

import hashlib
import os
import yaml

from cerr.roe import dosimetric_models as doseModels

from validate.core.data_capsule import DataCapsule


# VALID FIELDS AND SETTINGS
FILE_NAME = "analysis.yaml"

TOP_LEVEL_KEYS = {"input", "compute", "model", "structures"}
SECTION_KEYS = {
    "input": {"start_from", "data_dir", "predictors_csv", "plan_structures_csv", "outcomes_csv"},
    "compute": {"device"},
    "model": {"name", "file"},
}
RAW_DATA_FORMATS = ("dicom", "nifti", "nrrd")
START_FROM_VALUES = RAW_DATA_FORMATS + ("predictors",)
DEVICE_VALUES = ("cpu", "gpu")
STRUCTURES_REQUIRED_KEYS = {
    "existing": (),
    "ai": ("ai_model",),
    "classic": ("method",),
    "derived": ("from",),
}


def checkSettings(analysisDict):
    """Check analysis.yaml's contents."""
    problems = []
    inputs = analysisDict.get("input") or {}
    compute = analysisDict.get("compute") or {}
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
    elif startFrom in RAW_DATA_FORMATS:
        if inputs.get("data_dir") is None:
            problems.append(f"input.data_dir is required when start_from is {startFrom!r}.")

    # Structure recipes
    for structName, recipe in structures.items():
        recipe = recipe or {}
        source = recipe.get("source")
        if source not in STRUCTURES_REQUIRED_KEYS:
            problems.append(f"structures.{structName}.source must be one of "
                            f"{list(STRUCTURES_REQUIRED_KEYS)}, got {source!r}.")
            continue
        for key in STRUCTURES_REQUIRED_KEYS[source]:
            if key not in recipe:
                problems.append(f"structures.{structName} has source '{source}' "
                                f"but no '{key}'.")

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
        "structures": dataCapsule.structures,
    }
    return analysisDict


def writeSettings(dataCapsule, analysisDir):
    """Write analysis.yaml to analysisDir.
    If analysis.yaml already exists with the same settings, it is
    retained, and the run resumes.

    Returns:
        str: path to analysis.yaml.
    """
    path = os.path.join(analysisDir, FILE_NAME)
    analysisDict = toAnalysisDict(dataCapsule)

    if os.path.exists(path):
        with open(path, "r") as f:
            existing = yaml.safe_load(f)
        if existing != analysisDict:
            raise ValueError(
                f"{path} already holds a different analysis. Choose a new "
                f"folder or remove existing analysis.yaml.")
        return path

    os.makedirs(analysisDir, exist_ok=True)
    # Write to a temporary file and rename, so a crash never leaves a partial file
    tmpPath = path + ".tmp"
    with open(tmpPath, "w") as f:
        yaml.safe_dump(analysisDict, f, sort_keys=False)
    os.replace(tmpPath, path)
    return path


def toDataCapsule(path):
    """Read and translate analysis.yaml into DataCapsule."""
    with open(path, "r") as f:
        analysisDict = yaml.safe_load(f)
    checkSettings(analysisDict)
    inputs = analysisDict.get("input", {})
    return DataCapsule(
        start_from=inputs["start_from"],
        model=analysisDict["model"],
        device=analysisDict.get("compute", {}).get("device", "cpu"),
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
