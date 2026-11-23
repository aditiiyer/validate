# Settings and logs

## analysis.yaml

Every analysis is described by `analysis.yaml` in its analysis folder. The GUI writes it;
`core/analysis.py` reads and checks it.

```yaml
input:
  start_from: dicom            # dicom | nifti | nrrd | predictors
  data_dir: /data/cohort       # null if start_from: predictors
  predictors_csv: null
  plan_structures_csv: null
  outcomes_csv: null
compute:
  device: gpu                  # cpu | gpu
model:
  name: Xerostomia (grade 2+)  # pyCERR ROE model name
  file: /path/to/Xerostomia (grade 2+).json   # filled in for built-in models
segment:
  ai_models: [CT_HN_SMIT]      # AI models to run (cerr.ai_models names)
  install_dir: /models         # required if ai_models is not empty
structures:
  Oral cavity: {source: derive}
  Esophagus: {source: existing, name: ESOPHAGUS}
```

`core.analysis.checkSettings` validates the keys and values. The settings can be written
from a script with `core.analysis.saveSettings` and run with the functions in `run.py`, as in
the notebook in `tutorials/`.

### Which settings each tab depends on

`core.analysis.TAB_SETTINGS` lists the settings each tab's results depend on:

| Tab | Depends on |
|---|---|
| Segment | `input.start_from`, `input.data_dir`, `input.plan_structures_csv`, `compute.device`, `segment.*` |
| Model | all of `input`, and `structures` |

## task_log.yaml

Written only by VALIDATE (`logs.py`), atomically (a temporary file, then a rename).

```yaml
settings_hash:
  segment: <SHA-256 of the Segment settings>
  model: <SHA-256 of the Model settings>
runs:
- tab: segment
  started: '2026-11-19T10:22:38'
  finished: '2026-11-19T10:41:02'
  provenance_id: <hash of the provenance below>
  provenance:
    validate_commit: <commit>
    validate_user_modified: false
    pycerr_commit: <commit>
    ai_models: [{number, name, install_dir, repo_commit, weights_sha256, ...}]
  device: gpu
  hardware: {os, machine, processor, gpus}
  error_log: _autoseg_logs/error_log_20261119_102238.txt
patients:
  pt_001:
    segment:
      CT_HN_SMIT: {status: ok, run: 0, files: [...], labels: {...}}
      derived: {status: ok, run: 1, files: {Oral cavity: ...}}
    ntcp: {status: ok, value: 0.31, run: 1}
```

- `runs` has one entry per invocation of a tab. Each patient result's `run` is its index.
- `settings_hash` holds, per tab, the hash of the settings its results were made with
  (`logs.settingsHashes`, over a canonical form, so formatting and comments don't count).

### When results are cleared

Before a run, and when the GUI saves settings, the current settings are compared with the
recorded hash. If a tab's settings changed, the user is asked, and on confirmation
`logs.clearResults` removes that tab's results from every patient. Output files stay on disk
until the tab runs again.

## Error logs

`logs.ErrorLog` writes one file per invocation, `_autoseg_logs/error_log_<date>_<time>.txt`,
with one line per patient error (and setup errors as `(setup)`). Nothing else goes in it.

## ai_model_installs.yaml

`seg/model_registry.py` keeps a record, in the repository folder, of where each AI model is
installed, when, and the SHA-256 of its weights (rehashed only when their size or modified
time changes). The Segment tab uses it for the default install folder, and the task log
copies the hash into each run's provenance.
