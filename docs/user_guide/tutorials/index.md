# Tutorials

Each tutorial is a complete analysis, from an empty window to results. Pick the one that
matches your data.

::::{grid} 1 1 2 2
:gutter: 3

:::{grid-item-card} 1. AI segmentation of a cohort
:link: segment_cohort
:link-type: doc

Install an AI model and auto-contour the structures a model needs, for every patient.
:::

:::{grid-item-card} 2. From AI segmentation to NTCP
:link: ai_seg_to_ntcp
:link-type: doc

Segment, derive the model's structures, add clinical predictors, and compute NTCP.
:::

:::{grid-item-card} 3. NTCP from your own structures
:link: existing_structures
:link-type: doc

Use the contours already in your data, with fractionation correction.
:::

:::{grid-item-card} 4. NTCP from pre-computed predictors
:link: precomputed_predictors
:link-type: doc

No images: compute NTCP from a table of dose metrics and clinical factors.
:::
::::

## Example files

The tutorials use these example CSVs. Download them to see the expected layout, or use them
as templates. Their values are made up.

| File | Used in |
|---|---|
| {download}`clinical_predictors_xerostomia.csv </_static/examples/clinical_predictors_xerostomia.csv>` | Tutorial 2 |
| {download}`plan_info_esophagitis.csv </_static/examples/plan_info_esophagitis.csv>` | Tutorial 3 |
| {download}`clinical_predictors_esophagitis.csv </_static/examples/clinical_predictors_esophagitis.csv>` | Tutorial 3 |
| {download}`precomputed_predictors_xerostomia.csv </_static/examples/precomputed_predictors_xerostomia.csv>` | Tutorial 4 |

The screenshots show paths under `~/validate_tutorial`. Use your own folders instead.

```{toctree}
:hidden:

segment_cohort
ai_seg_to_ntcp
existing_structures
precomputed_predictors
```
