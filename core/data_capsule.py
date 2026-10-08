"""Defines Validate's data structure, DataCapsule, created per analysis.
It holds analysis-level choices plus one PatientRecord per patient.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlanInfo:
    """Plan data summary"""
    name: str | None = None
    prescribed_dose: float | None = None
    fx_size: float | None = None
    fx_num: int | None = None
    dose_index: int | None = None


@dataclass
class PatientRecord:
    """Patient-level data summary"""
    pt_id: str
    data_dir: str | None = None
    plan_info: PlanInfo | None = None
    structures: dict[str, str] = field(default_factory=dict)                # modelled structure mapped to structure name in planC
    predictors: dict[str, float | None] = field(default_factory=dict)  # If None, compute on the fly
    ntcp: float | None = None
    outcome: float | None = None


@dataclass
class DataCapsule:
    """Analysis-level data summary"""
    start_from: str                                                    # dicom | nifti | nrrd | predictors
    model: dict[str, str | None]                                       # {name, file}: ROE model name and its JSON path
    device: str = "cpu"                                                # cpu | gpu
    data_dir: str | None = None                                        # If beginning from raw data, otherwise None
    predictors_csv: str | None = None                                  # If pre-computed predictors are input via CSV, otherwise None
    plan_structures_csv: str | None = None                             # Optional input CSV specifying structure names, dose plan ID, and fractionation information
    outcomes_csv: str | None = None                                    # Optional input CSV specifying patient outcomes
    structures: dict[str, dict] = field(default_factory=dict)          # modelled structure mapped to a source (AI, classic, existing)
                                                                       # and method of derivation (union, intersection, diff)
    patients: dict[str, PatientRecord] = field(default_factory=dict)   # List of PatientRecords
