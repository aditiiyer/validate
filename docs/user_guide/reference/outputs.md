# Outputs

Everything VALIDATE writes goes in the analysis folder (**Output**). By default this is
`analysis_<model>` inside the **Data** folder.

```text
analysis_Xerostomia (grade 2+)/
    analysis.yaml          your settings
    task_log.yaml          each patient's results, and how each run was made
    segment_summary.csv    written by Generate summary
    _autoseg_logs/         one error log per run
    pt_001/                AI contours and derived structures for pt_001
    pt_002/
```

| File | Contents |
|---|---|
| `analysis.yaml` | The settings from the window, saved when you confirm. Opening this folder as **Output** loads them again. |
| `task_log.yaml` | Each patient's results, plus each run's provenance: the VALIDATE, pyCERR and AI model versions, a hash of the AI model weights, and the hardware. Written only by VALIDATE. |
| `_autoseg_logs/error_log_<date>_<time>.txt` | One line per patient that failed in that run, with the reason. |
| `<patient>/` | The AI contours (**Segment**) and derived structures (**Model**): an RTSTRUCT for DICOM data, NIfTI masks otherwise. Derived structures are named `<patient>_<structure>_autoseg`. |

:::{important}
Results are tied to the settings that made them. If you change settings that a tab's results
depend on, VALIDATE warns you, and clears those results when you save.
:::

(segment-summary)=
## segment_summary.csv

Written by **Generate summary** on the **Segment** tab. One row per patient, AI model,
output file and label.

| Column | Meaning |
|---|---|
| `patient_id` | Patient ID. |
| `ai_model` | AI model name, or `derived` for structures the **Model** tab derived. |
| `status` | `ok` or `error`. |
| `run` | The run that made it (its number in `task_log.yaml`). |
| `file` | Output file, relative to the analysis folder. |
| `label` | Label number in the file. |
| `structure` | Structure name. |
| `message` | Why it failed, on error. |

(ntcp-results)=
## NTCP results CSV

Saved with **Export CSV...** on the **Model** tab, after a run. One row per patient.

| Column | Meaning |
|---|---|
| `patient_id` | Patient ID. |
| `ntcp` | Normal tissue complication probability, from 0 to 1. Empty on error. |
| `status` | `ok` or `error`. |
| `message` | Why it failed, on error. |
