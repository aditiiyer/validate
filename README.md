# VALIDATE

Software for the [VALIDATE](https://validate4rt.org) consortium (VALIdation of Decision
support models for rAdioThErapy), to verify published radiotherapy
outcome models on independent patient cohorts.

Validate applies a dosimetric (NTCP) model to a local patient cohort. This includes auto-segmenting
the structures the model needs, computing dose-volume metrics and NTCPs for each patient, and
assessing model discrimination and calibration. Models are shared; patient data stay at your site.

## Core functions

- **Segment:** Runs validated, pre-trained AI models to auto-segment structures of interest. 
Each AI model runs in its own isolated environment via [pyCERR](https://www.github.com/cerr/pycerr.git).
- **Model:** Derives modeled structures from the AI outputs or uses input structures to compute dose-volume metrics,
including fractionation correction where needed. Computes NTCPs from user-input and/or dynamically computed predictors. 
- **Review:** Visualize model discrimination and calibration (in development).

Supports DICOM, NIfTI/NRRD, or a CSV of pre-computed predictors.

## Install

### Requirements

- Python 3.9–3.13 (tested on 3.11).
- [git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/getting-started/installation/).  
  _uv_ installs _Validate_ and selected AI segmentation models along with dependencies.
- Disk space for model weights
- Optional: an NVIDIA GPU (CUDA) or Apple silicon (MPS). Alternatively, segmentation falls back to the
  CPU, which is slower.

### 1. Create an environment

```bash
uv venv --python 3.11        # creates .venv/, downloading Python 3.11 if needed
source .venv/bin/activate    # Windows: .venv\Scripts\activate
```

### 2. Install pyCERR and Validate

```bash
uv pip install -e "pycerr @ git+https://github.com/cerr/pyCERR.git"
git clone https://github.com/aditiiyer/validate.git
uv pip install -e ./validate
```

### 3. Verify

```bash
python -c "import cerr, validate; print('ok')"
```

## Run

Launch the GUI using
```bash
python -m validate
```
Select the data folder (one DICOM directory per patient) and a
dosimetric model, then work through the tabs from left to right.

## Outputs

Each dosimetric model gets its own analysis folder, by default `<Data>/analysis_<model>`:

| File | Contents |
|---|---|
| `analysis.yaml` | Analysis settings (plain YAML). |
| `task_log.yaml` | Per-patient results, plus provenance for each run: the validate, pyCERR and AI model commits, a hash of the weights, and the hardware. |
| `<patient>/` | AI segmentations and derived structures (RTSTRUCT for DICOM input, NIfTI otherwise). |
| `_autoseg_logs/` | Error logs for each run. |


## License

GPL-3.0-or-later. See [LICENSE](LICENSE). The release history is in [CHANGELOG.md](CHANGELOG.md).
