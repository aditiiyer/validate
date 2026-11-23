# Troubleshooting

Start with **View error log** on the tab that failed. It lists each patient that failed and
why. The full results are in **View task log**.

## Installing

### `CERTIFICATE_VERIFY_FAILED` when installing an AI model (Linux)

**What you see:** **Install** fails with a download error (`URLError`). The underlying error
is `SSL: CERTIFICATE_VERIFY_FAILED`.

**Why:** Python can't find your system's list of trusted certificates.

**Fix:** before opening VALIDATE, point Python at the system's certificate file. Add the line
for your system to `~/.bashrc`:

::::{tab-set}
:::{tab-item} RHEL / CentOS / Rocky
```bash
export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt
```
:::
:::{tab-item} Debian / Ubuntu
```bash
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
```
:::
::::

If your institution's network inspects HTTPS traffic, ask IT for its root certificate and
point `SSL_CERT_FILE` at that instead. Don't turn off certificate checks.

### "A weights URL applies to one AI model"

A **Weights URL** is the link for one model's weights. Tick only the AI model it is for,
then click **Install**.

## Segment tab

### "Not installed in …: Install them first"

The ticked AI model isn't in the folder next to **Use existing install**. Select the folder
you installed it in, or install it (see {doc}`tutorials/segment_cohort`).

### "No 'Scan file' given for patient …"

Your data is NIfTI or NRRD, so VALIDATE needs to be told which file is the scan. Add a
**Scan file** column to the **Plan info** CSV. See {ref}`plan-info-csv`.

### "… holds both DICOM and NIfTI/NRRD files"

A patient folder can hold only one format. Move the other files out of it.

## Model tab

### "Run Segment first"

Some structures are set to **Derive**, but their AI model hasn't run for every patient.
Click **Go to Segment** and run it, or choose **Use existing** for those structures.

### "Missing structure(s): … Available: …"

A **Use existing** structure wasn't found in that patient's data. The message lists the
names that are there. Fix the name on the **Model** tab, or give that patient's name in the
**Plan info** CSV (see {ref}`plan-info-csv`). Names must match in full; case doesn't matter.

### "No dose found in plan."

The patient's folder has no dose. Add the RTDOSE (DICOM), or give the **Dose file** in the
**Plan info** CSV (NIfTI/NRRD).

### A patient fails with a missing predictor or fractionation value

The model needs a value that isn't there. Check that:

- the predictor values CSV has a column for each clinical predictor (see {doc}`reference/models`)
  and no empty cells;
- for a model with fractionation correction, the **Plan info** CSV gives two of
  **Prescribed dose (Gy)**, **Fraction size (Gy)** and **Fraction number**.

## Settings

### "The settings changed since the … results were made"

The settings in `analysis.yaml` no longer match the ones the results were made with, for
example because the file was edited by hand. **Clear and run** clears that tab's results and
runs again.

### Changing the model starts a new analysis

Each analysis holds one model. To try another model on the same data, let VALIDATE start a
new analysis in another folder. Your first analysis is kept.
