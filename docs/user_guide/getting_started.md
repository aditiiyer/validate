# Getting started

This page takes you from nothing installed to the VALIDATE window open.

## What you need

- A computer running macOS, Linux or Windows.
- [git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/getting-started/installation/).
  uv installs Python, VALIDATE and the AI segmentation models.
- Disk space for the AI model weights (1–3 GB per model).
- Optional: an NVIDIA GPU (CUDA) or an Apple silicon Mac. Without one, segmentation runs on
  the CPU, which is slower.

## Install

1. Open a terminal, go to the folder you want to install into, and create a Python environment:

   ::::{tab-set}
   :::{tab-item} macOS / Linux
   ```bash
   uv venv --python 3.11
   source .venv/bin/activate
   ```
   :::
   :::{tab-item} Windows
   ```bash
   uv venv --python 3.11
   .venv\Scripts\activate
   ```
   :::
   ::::

2. Download and install pyCERR and VALIDATE:

   ```bash
   git clone https://github.com/cerr/pyCERR.git
   uv pip install -e ./pyCERR
   git clone https://github.com/aditiiyer/validate.git
   uv pip install -e ./validate
   ```

3. Check that both installed:

   ```bash
   python -c "import cerr, validate; print('ok')"
   ```

   You should see `ok`.

:::{note}
Both are installed from their git folders, so each run can record the exact VALIDATE and
pyCERR versions used.
:::

## Open VALIDATE

With the environment active, run:

```bash
python -m validate
```

The VALIDATE window opens on the **Segment** tab:

```{image} /_static/images/gui_overview.png
:alt: The VALIDATE window when first opened. The Analysis section at the top has Start from, Data, Plan info, Model and Output. Below it are the Segment, Model and Review tabs, with Segment selected.
:class: screenshot
:width: 640px
```

:::{tip}
To open VALIDATE with the **Data** folder already filled in, add the folder to the command:
`python -m validate /path/to/cohort`.
:::

## Next steps

- {doc}`gui_tour` explains each part of the window.
- {doc}`tutorials/index` walk through complete analyses.
