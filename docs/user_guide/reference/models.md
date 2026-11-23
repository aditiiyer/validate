# Built-in models

The dosimetric models come from pyCERR. The **Model** list in the window shows the ones in
your installed version; this table was made from pyCERR at the time of writing.

| Model | Structure: dose metric | Clinical predictors | Fractionation correction |
|---|---|---|---|
| Bronchial stenosis (cox) | Bronchi: meanDose | | No |
| Bronchial stenosis (logistic) | Bronchi: meanDose | | No |
| Bronchial toxicity (Grade 3+) | PBT: D0.1 | | Fraction size |
| Bronchial toxicity (Grade 5) | PBT_protocol: D0.1 | | Fraction size |
| Esophagitis (Huang) | Esophagus: meanDose | concurrentChemo | Fraction number |
| Esophagitis (Jackson_cox) | Esophagus: D3 | | Fraction size |
| Esophagitis (Jackson_logistic) | Esophagus: D3 | | Fraction size |
| Esophagitis (Wijsman) | Esophagus: meanDose | gender, concurrentChemo, tumorStage | Fraction size |
| Pneumonitis (Appelt) | Lung_GTV: meanDose | formerSmoker, currentSmoker, over63yrs, pulmonaryComorbidity, sequentialChemo, lowerMidLobe | Fraction number |
| Rectal bleeding (grade 2+) | Rectum: gEUD | | Fraction size |
| Xerostomia (grade 2+) | SCRR, Parotids-SCRR, Submandibular glands, Oral cavity: meanDose | pretreatment_toxicity | No |

- **Clinical predictors** are the values you supply in the predictor values CSV. Their
  numeric codes are in the model's file (in pyCERR's `cerr/roe/model_parameters/`).
- **Pre-computed predictors** columns are named `<structure> <metric>`, for example
  `Esophagus D3`.
- For **Fraction size** and **Fraction number** correction, give any two of prescribed
  dose, fraction size and fraction number in the plan info CSV.

## Structures VALIDATE can derive

**Derive** is offered on the **Model** tab only for these structures:

| Structure | Made from |
|---|---|
| Oral cavity | CT_HN_SMIT AI model |
| Submandibular glands | CT_HN_SMIT AI model (left and right glands combined) |
| SCRR (stem-cell rich region) | pyCERR's SCRR method, from the AI model's parotids, masseters and mandible |
| Parotids-SCRR | CT_HN_SMIT AI model (both parotids, minus the SCRR) |

All other structures must come from your data (**Use existing**).
