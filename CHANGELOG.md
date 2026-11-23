# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `installMissingModels` passes extra options (such as `weightsUrl`) on to pyCERR's
  `install_utils`.
- README.md, CHANGELOG.md and LICENSE.
- Header: "Start from" choice, Data (DICOM/NIfTI) or Pre-computed predictors.
- Segment tab: "Weights URL" field, to install an AI model's weights from a download link
- `psutil` dependency, used to abort runs and installs.
- Tests for fractionation correction, NTCP from pre-computed predictors, one run at a
  time, and clearing results when settings change.
- Tutorials: SCRR segmentation on H&N CT (with a xerostomia NTCP demo using a synthetic
  dose), and xerostomia NTCP from a DICOM cohort, with sample settings.

### Changed

- GUI redesign: altered layout, spacing, tab appearance; disabled controls keep their state visible.
- Font sizes follow the platform's default font (at least 10 pt) for legible display across different OS.
- Plan info moved to the header (shared by Segment and Model tabs).
- Only one run or install at a time; settings can't be saved while one is in progress.
- Model tab: structures default to Derive where a recipe is registered.
- Oral cavity, Submandibular glands and Parotids-SCRR are derived from CT_HN_SMIT
  (model 7) outputs instead of CT_HeadAndNeck_OARs (model 3).
- The Device setting is passed to AI models that accept `--device`; the task log records
  only the GPU used.
- Run progress: a busy bar with the current step and "n/total patients done".
- Test suite: hermetic and faster, without duplicate or trivial tests.
- SCRR inputs are passed to pyCERR by side (left/right parotid and masseter); requires
  the matching pyCERR update.

### Fixed

- NRRD scans are converted to NIfTI for the AI models, which read only NIfTI or DICOM.
- Derived Oral cavity is named as the model expects (CT_HN_SMIT outputs `Oral_Cavity`).
- A run with no patient folders stops with "No patient folders found in <data_dir>",
  instead of appearing to stall.

### Removed

- Unused `diffSettings`.

## [0.5.0] - 2026-11-13

### Added

- Function to derive all modeled structures for one patient (`deriveModelStructures`),
  used by the Model run, and a derive-only cohort run (`deriveStructuresForCohort`).
- Derived structure exports are recorded in the task log, under each patient's
  `segment` section, and included in the summary CSV.
- Segment tab: Install asks whether to re-install when the AI model is already in the
  chosen folder, or switches to "Use existing install".
- Segment tab: "Finish" section with Generate summary and Next.
- Window title shows the installed package version.
- `pyproject.toml`: validate installs as a package (`pip install -e .`) and launches
  with `validate` or `python -m validate`.
- pytest suite for settings, task log, input reading, patient records, the AI model
  install registry, and the Segment and Model runs.

### Changed

- Model tab: "Plan CSV" renamed to "Plan info", and "Predictors CSV" to "Predictor values".
- Tab labels are violet, and the selected tab is underlined in violet.
- Window opens at 780 × 830.
- Install clears the previous run's progress.

### Removed

- Reinstall button; re-installing is offered from the Install prompt instead.

## [0.4.0] - 2026-11-12

### Added

- GUI split into Segment, Model and Review (placeholder) tabs, under a shared
  Data / Model / Output header.
- Segment tab runs only the AI segmentation models the dosimetric model needs.
- One analysis folder per dosimetric model, defaulting to `<Data>/analysis_<model>`.
- Pop-up to confirm saving settings to `analysis.yaml` before a run.
- Choosing a different dosimetric model starts a new analysis.
- Task log (`task_log.yaml`) with a settings check per tab, per-patient Segment and
  NTCP results, and provenance (validate, pyCERR and AI model commits, weights hash,
  hardware).
- Summary CSV of the Segment outputs (`segment_summary.csv`).

### Changed

- The Model tab derives structures from the recorded AI outputs, or uses existing
  ones, then computes NTCP.

### Removed

- AI model availability CSVs; the task log records the outputs instead.

## [0.3.0] - 2026-11-12

### Added

- Settings grouped by tab, with the ability to save changes to `analysis.yaml`.
- Registry of installed AI autoseg models, including a hash of the weights, checked
  at each run.

## [0.2.0] - 2026-11-11

### Added

- Patient records built from the cohort directory and CSV inputs.
- Logging for auto-segmentation.

## [0.1.0] - 2026-10-08

### Added

- PyQt GUI for applying a dosimetric (NTCP) model to a patient cohort.
- Data structure (`DataCapsule`) holding the patient records and analysis settings.
- Raw data inputs (DICOM, NIfTI, NRRD) or pre-computed predictors (CSV).
- Cohort-wide run that applies a model to every patient.
- Auto-segmentation pipeline and registry of structure derivation recipes.
- The first scan is used by default.
