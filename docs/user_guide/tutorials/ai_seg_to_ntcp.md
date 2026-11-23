# 2. From AI segmentation to NTCP

In this tutorial you compute each patient's risk of grade 2+ xerostomia with the
**Xerostomia (grade 2+)** model. Its four structures are made from AI contours, and it adds
one clinical predictor, pre-treatment xerostomia, which you supply in a CSV.

The steps are:

```{mermaid}
flowchart LR
    A[Segment:<br>AI contours] --> B[Model:<br>derive structures] --> C[Model:<br>add clinical predictors] --> D[Model:<br>compute NTCP]
```

**You need:**

- A cohort folder with one subfolder per patient, each holding the planning CT **and dose**
  (DICOM RTDOSE, or a NIfTI/NRRD dose file).
- A CSV of each patient's pre-treatment xerostomia, for example
  {download}`clinical_predictors_xerostomia.csv </_static/examples/clinical_predictors_xerostomia.csv>`.

## Segment the cohort

Follow {doc}`segment_cohort` with the same cohort and **Model**. When the **Segment** run
is done, click **Next** to go to the **Model** tab.

## Choose how each structure is made

The **Structures** table lists the four structures the model needs. Each has two options:

**Derive**
: Make the structure from the AI contours. For example, **Parotids-SCRR** is both parotids
  minus the stem-cell rich region (SCRR). **Derive** is only offered for structures VALIDATE
  has a recipe for.

**Use existing**
: Take the structure from your data, by the name you type. See {doc}`existing_structures`.

Keep **Derive** selected for all four:

```{image} /_static/images/derive_inputs.png
:alt: The Model tab. The Structures table lists SCRR, Parotids-SCRR, Submandibular glands and Oral cavity, each with Derive selected. Predictor values is set to clinical_predictors_xerostomia.csv.
:class: screenshot
:width: 640px
```

## Add the clinical predictor

The model also uses **pretreatment_toxicity**: whether the patient had xerostomia before
treatment, coded `0` for No and `1` for Yes. Put it in a CSV with one row per patient:

```text
ID,pretreatment_toxicity
pt_001,0
pt_002,1
pt_003,0
```

- **ID** is the patient's folder name.
- The other column names must match the predictor names in the model. Hover over the **i**
  next to **Predictor values** for the rules, or see {ref}`predictors-csv`.

Next to **Predictor values**, click **Select CSV** and choose your file.

:::{note}
When you start from **Data**, VALIDATE reads only the clinical predictors from this CSV.
It computes the dose metrics (here, the mean dose to each structure) from the images.
:::

## Compute the NTCP

1. Click **Run**.
2. VALIDATE asks to save the settings. Click **Save and continue**.

VALIDATE then derives the four structures for each patient, computes their mean doses and
the NTCP. When it finishes, the progress bar says **Done** and **Export CSV...** is enabled:

```{image} /_static/images/derive_done.png
:alt: The Model tab after the run, with "Done (5/5 patients)" and the Export CSV button enabled.
:class: screenshot
:width: 640px
```

:::{admonition} "Run Segment first"
:class: warning
If you click **Run** before the AI model has run on every patient, VALIDATE stops and says so:

```{image} /_static/images/derive_segment_first.png
:alt: A pop-up saying the structures are derived from CT_HN_SMIT, which hasn't been run yet (0 of 5 patients), with Cancel and Go to Segment buttons.
:class: screenshot
:width: 420px
```

Click **Go to Segment** and run it. If only some patients are missing, you can instead run
the patients that are ready.
:::

## Get the results

1. Click **Export CSV...** and choose where to save the results. The CSV has one row per
   patient: `patient_id`, `ntcp` (between 0 and 1), `status` (`ok` or `error`) and
   `message` (why it failed). See {ref}`ntcp-results`.
2. Click **View error log** to see why any patient failed.
3. The derived structures are saved in the analysis folder, in each patient's subfolder,
   so you can review them.

## Next

- To use contours you already have for some structures, see {doc}`existing_structures`.
- The **Review** tab, which will compare these NTCPs with observed outcomes, is coming soon.
