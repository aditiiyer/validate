# Inputs

## Cohort folder

The **Data** folder holds one subfolder per patient. The subfolder's name is the patient's
ID, used to match rows in the CSVs.

```text
hn_cohort/
    pt_001/
    pt_002/
    pt_003/
```

Each patient folder holds that patient's files in one format:

::::{tab-set}
:::{tab-item} DICOM
All of the patient's DICOM files in the folder: the CT, the RTDOSE and, if you use your own
structures, the RTSTRUCT. If there is more than one RTDOSE, give the one to use in the
**Plan name** column of the plan info CSV.
:::
:::{tab-item} NIfTI / NRRD
The scan, the dose and any structure masks, as `.nii`, `.nii.gz` or `.nrrd` files.
VALIDATE needs the plan info CSV to know which file is which: the **Scan file** and
**Dose file** columns, and a column per structure.
:::
::::

A folder can't mix DICOM and NIfTI/NRRD files.

(plan-info-csv)=
## Plan info CSV

Optional. One row per patient; only **ID** is required.

| Column | Format | Meaning |
|---|---|---|
| **ID** | All | Patient folder name. |
| **Plan name** | DICOM | RTDOSE file name, if a patient has more than one dose. |
| **Prescribed dose (Gy)** | All | Total prescribed dose, in Gy. |
| **Fraction size (Gy)** | All | Dose per fraction, in Gy. |
| **Fraction number** | All | Number of fractions. |
| **Scan file** | NIfTI/NRRD | Scan file name or pattern, such as `*_CT.nrrd`. Needed to run **Segment**. |
| **Dose file** | NIfTI/NRRD | Dose file name or pattern. |
| *<structure>* | All | One column per structure the model needs, named as in the model. DICOM: its name in the RTSTRUCT. NIfTI/NRRD: its mask file, or `file:label` for a label map (for example `labels.nii.gz:3`). |

- If the model corrects for fractionation, give any two of the three fractionation columns.
- File names and patterns are relative to the patient's folder and must match exactly one file.
- A structure name given here overrides the **Use existing** name on the **Model** tab, for
  that patient.

Example:

```text
ID,Prescribed dose (Gy),Fraction size (Gy),Fraction number,Scan file,Dose file,Oral cavity
pt_001,70,2,35,scan_*.nii.gz,dose_*.nii.gz,labels.nii.gz:3
```

(predictors-csv)=
## Predictor values CSV

Set on the **Model** tab. One row per patient; only **ID** is required.

| Column | Meaning |
|---|---|
| **ID** | Patient ID (the folder name when starting from **Data**). |
| *<structure> <metric>* | A dose metric, named as in the model, such as `Oral cavity meanDose`. In Gy, already corrected for fractionation if the model needs it. Only read when starting from **Pre-computed predictors**. |
| *<predictor>* | A clinical predictor, named as in the model, such as `concurrentChemo`, as the model's numeric code. |

- When starting from **Data**, only the clinical predictors are read. The dose metrics are
  computed from the images.
- An empty cell leaves the model's own value for that predictor, if it has one; otherwise
  the patient fails with a missing predictor.
- A warning is logged for IDs that match no patient.

See {doc}`models` for each model's metrics and predictors.
