# 1. AI segmentation of a cohort

In this tutorial you auto-contour, for every patient in a head-and-neck cohort, the
structures the **Xerostomia (grade 2+)** model is built from. VALIDATE picks the AI model
for you, installs it, and runs it.

**You need:** a cohort folder with one subfolder per patient, each holding that patient's
CT (DICOM, NIfTI or NRRD). See {doc}`../reference/inputs`.

**Time:** installing the AI model is a one-time download of 1–3 GB. How long the run takes
depends on your hardware; it is much faster on a GPU.

## Set up the analysis

1. Open VALIDATE (see {doc}`../getting_started`).
2. Under **Start from**, keep **Data (DICOM/NIfTI)** selected.
3. Next to **Data**, click **Browse...** and select your cohort folder.
4. In **Model**, select **Xerostomia (grade 2+)**.
5. Check **Output**. It is filled in for you, as `analysis_Xerostomia (grade 2+)` inside the
   cohort folder. Click **Browse...** to choose another folder.

```{image} /_static/images/seg_analysis.png
:alt: The Analysis section with Data set to ~/validate_tutorial/hn_cohort, Model set to Xerostomia (grade 2+), and Output set to the analysis_Xerostomia (grade 2+) folder inside it.
:class: screenshot
:width: 640px
```

:::{admonition} NIfTI or NRRD scans?
:class: note
For NIfTI or NRRD, also select a **Plan info** CSV with a **Scan file** column, giving each
patient's scan file name (or a pattern such as `*_CT.nrrd`). DICOM folders need no CSV.
See {ref}`plan-info-csv`.
:::

## Install the AI model

The **Segment** tab lists the AI models the model's structures are made from, here
**CT_HN_SMIT**. The dot next to it shows whether it is installed:

```{image} /_static/images/seg_not_installed.png
:alt: The Segment tab listing CT_HN_SMIT with a red dot and the words Not installed.
:class: screenshot
:width: 640px
```

If it says **Installed** (green), skip to [Run the AI model](#run-the-ai-model).
If you installed it before in another folder, select **Use existing install**, click
**Browse...** and select that folder.

To install it:

1. Select **Install to:**, click **Browse...** and choose a folder with a few GB free.
   You can reuse this folder for every analysis.
2. If the model's maintainers gave you a download link for the weights, paste it in
   **Weights URL**. Otherwise leave it empty.
3. Click **Install**.

```{image} /_static/images/seg_install.png
:alt: Install to is selected, with the install folder filled in and the Install button enabled.
:class: screenshot
:width: 640px
```

A progress bar shows while it downloads the model's code and weights and sets up its own
Python environment. This can take a while.

```{image} /_static/images/seg_installing.png
:alt: The Segment tab while installing, showing "Installing model 7..." and a busy progress bar.
:class: screenshot
:width: 640px
```

When it finishes, the dot turns green and says **Installed**, and **Use existing install**
is selected with your install folder:

```{image} /_static/images/seg_installed.png
:alt: CT_HN_SMIT now shows a green dot and the word Installed. Use existing install is selected.
:class: screenshot
:width: 640px
```

## Run the AI model

1. Under **Device**, select **GPU** to use an NVIDIA GPU or Apple silicon, or **CPU**.
   **GPU** falls back to the CPU if there is no GPU.
2. Optional: click **Notify when done** and enter your email address to get an email when the
   run ends. It contains the run's status and where to find its files, but no patient data.
3. Click **Run**.
4. VALIDATE asks to save the settings. Click **Save and continue**.

While it runs, VALIDATE shows the AI model being applied and how many patients are done:

```{image} /_static/images/seg_running.png
:alt: The Segment tab during a run, showing "Applying CT_HN_SMIT AI segmentation model... 2/5 patients done" above a progress bar. Run is grayed out and Stop is enabled.
:class: screenshot
:width: 640px
```

To stop early, click **Stop**. VALIDATE finishes the patient it is working on, then stops.
Click **Run** again later to carry on: it asks whether to keep the patients already done or
run them again.

When the run ends, the progress bar says **Done** with the number of patients:

```{image} /_static/images/seg_done.png
:alt: The Segment tab after the run, with a full progress bar reading "Done (5/5 patients)".
:class: screenshot
:width: 640px
```

## Check the results

1. Click **View error log**. If it is empty, every patient ran. Otherwise it lists each
   patient that failed and why. See {doc}`../troubleshooting`.
2. Click **Generate summary**. VALIDATE writes `segment_summary.csv` in the analysis folder
   and opens it. It has one row per patient, AI model, output file and structure. See
   {ref}`segment-summary`.
3. Click **View outputs** to open the analysis folder. Each patient's AI contours are in a
   subfolder named after the patient: an RTSTRUCT for DICOM data, NIfTI masks otherwise.
   Open them in your treatment planning system or viewer to review them.

:::{important}
Review the AI contours before using them. VALIDATE doesn't check them for you.
:::

## Next

Click **Next** to go to the **Model** tab, and continue with {doc}`ai_seg_to_ntcp`.
