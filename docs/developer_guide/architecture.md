# Architecture

VALIDATE is a PyQt5 GUI over a small set of functions that run one step on every patient of
a cohort. pyCERR does the imaging work: reading DICOM/NIfTI/NRRD, running AI models,
structure operations, DVH metrics and the dosimetric models.

## Modules

The repository root is itself the `validate` package.

| Module | Role |
|---|---|
| `__main__.py` | Entry point (`python -m validate`): applies the theme and opens the main window. |
| `gui/main_window.py` | Shared **Analysis** settings, the tabs, and saving settings (`ensureSaved`). |
| `gui/segment_tab.py`, `gui/model_tab.py` | The **Segment** and **Model** tabs. |
| `gui/progress_and_logging.py` | `ManageRun`, the run/stop/log/progress behaviour both tabs share. |
| `gui/worker.py` | `QThread` workers that install AI models and run the cohort functions off the GUI thread. |
| `gui/theme.py` | The dark theme and font sizing. |
| `run.py` | The cohort functions: `applyAutoSegToCohort`, `applyModelToCohort`, `deriveStructuresForCohort`. |
| `core/analysis.py` | Reading, checking and writing `analysis.yaml`. |
| `core/data_capsule.py` | `DataCapsule` (analysis-level settings) and `PatientRecord` (one per patient). |
| `data_io/read_inputs.py` | Finding patients, reading the CSVs, loading a patient's data into pyCERR's `planC`. |
| `data_io/build_capsule.py` | Building the `DataCapsule` and its `PatientRecord`s from the settings and CSVs. |
| `seg/structures.py` | The structures each dosimetric model needs, and the recipes that derive them. |
| `seg/autoseg_pipeline.py` | Installing and running AI models through pyCERR. |
| `seg/model_registry.py` | `ai_model_installs.yaml`: where each AI model is installed, with a hash of its weights. |
| `modeling/apply_model.py` | Fractionation-correction inputs for a dosimetric model. |
| `logs.py` | The task log, error logs, provenance and `segment_summary.csv`. |
| `notify.py` | Optional email when a run ends. |

## How a run works

The GUI never runs the analysis itself. It writes the settings to `analysis.yaml`, then a
worker calls a function in `run.py` with the analysis folder. The same functions can be
called from a script or notebook.

```{mermaid}
flowchart TD
    GUI["GUI form<br>(main_window, tabs)"] -->|ensureSaved| YAML[(analysis.yaml)]
    GUI -->|Run| W[RunWorker<br>QThread]
    W --> R["run.py<br>applyAutoSegToCohort /<br>applyModelToCohort"]
    YAML --> C["build_capsule<br>DataCapsule + PatientRecords"]
    CSV[(Plan info CSV<br>Predictors CSV)] --> C
    C --> R
    R -->|per patient| P["pyCERR<br>load planC, AI models,<br>derive structures, NTCP"]
    R --> TL[(task_log.yaml)]
    R --> EL[(error log)]
    R --> OUT[(patient output folders)]
    W -->|signals: stage, progress,<br>finishedOk, failed| GUI
```

### Segment: `applyAutoSegToCohort`

For each patient: load the scan, run each AI model in `segment.ai_models` (each in its own
environment, through pyCERR), and record its output files and labels in the task log. A model
already run for a patient, with its outputs still on disk, is skipped unless `overwrite=True`.

### Model: `applyModelToCohort`

For each patient:

1. Build the patient's record from the settings, plan info CSV and predictors CSV.
2. Load the patient's data, add the AI outputs recorded by Segment, and derive the
   structures set to `derive` (classic recipes first, since others may use them).
   Derived structures are exported to the patient's output folder.
3. Rename the model's structures to the patient's names, set the clinical predictors, and
   compute the NTCP with pyCERR, applying fractionation correction if the model needs it.

When starting from pre-computed predictors, steps 2 and 3 are replaced by
`doseModels.runFromPredictors` on the CSV row.

Errors are per patient: a failure is recorded for that patient and the run moves on.

## Design decisions

**Each AI model runs in its own environment.**
: AI models pin conflicting versions of PyTorch, MONAI and so on. pyCERR installs each one
  into its own virtual environment and runs it as a subprocess, so VALIDATE's environment
  stays small and models can't break each other.

**Settings live in a file, not in the GUI.**
: `analysis.yaml` is the single source of truth for a run, so the same analysis can be run
  from a script, shared, or re-opened, and the task log can tie results to the exact
  settings (see {doc}`settings_and_logs`).

**Results are tied to the settings that made them.**
: Each tab's results are recorded with a hash of the settings they depend on. Changing those
  settings clears the results (after the user confirms), so results never describe settings
  other than the current ones.

**Provenance is recorded for every run.**
: The task log records the VALIDATE, pyCERR and AI model commits (and whether they were
  modified), a hash of the AI model weights, and the hardware, so results can be traced and
  compared across sites.
