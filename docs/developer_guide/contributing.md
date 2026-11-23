# Contributing

## Development install

Follow {doc}`../user_guide/getting_started`. Both pyCERR and VALIDATE are installed in
editable mode from their git folders, so your changes take effect without reinstalling, and
the task log records each one's commit and whether it was modified.

## Code style

- Names are camelCase (`applyModelToCohort`, `analysisDir`), matching pyCERR.
- Every public module, class and function has a Google-style docstring (`Args:`,
  `Returns:`, `Raises:`). They appear in the {doc}`../api/index`.
- Comments say *why*, not *what*.

## Tests

From the repository folder:

```bash
python -m pytest tests/
```

The tests don't need a GPU, AI models or patient data. `tests/conftest.py` stubs the git and
`nvidia-smi` calls made for provenance, and provides an `analysisDir` fixture holding a
minimal `analysis.yaml`.

## Documentation

The documentation is in `docs/`, written in Markdown (MyST) and built with Sphinx. The rules
are in `documentation_policy.md`. To build it:

```bash
pip install -r docs/requirements.txt
sphinx-build -W -b html docs docs/_build/html
```

Then open `docs/_build/html/index.html`. `-W` turns warnings into errors; fix them all.

The docs build without pyCERR or PyQt5 installed: `docs/conf.py` mocks them for the API
reference. Building needs Python 3.11 or later.

(regenerating-screenshots)=
### Regenerating screenshots

The User Guide's screenshots are made by a script that drives the real GUI off screen:

```bash
python docs/_scripts/make_screenshots.py
```

Run it in VALIDATE's environment (it needs PyQt5 and pyCERR). It writes
`docs/_static/images/*.png`. It uses a demo cohort of empty folders and the example CSVs in
`docs/_static/examples/`, so no patient data appears in the images. Runs and installs aren't
executed; their progress is set directly.

Rerun it whenever the GUI changes, and commit the updated images with the change. To add a
screenshot, add a step to the script and reference the image from the page:

````markdown
```{image} /_static/images/<name>.png
:alt: What the image shows.
:class: screenshot
:width: 640px
```
````

## Releases

1. Add the changes under **Unreleased** in `CHANGELOG.md` as you go
   ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format).
2. To release, set the version in `pyproject.toml`
   ([Semantic Versioning](https://semver.org/spec/v2.0.0.html)), move the **Unreleased**
   entries under the new version, and tag the commit.
3. Check the links in the docs:

   ```bash
   sphinx-build -b linkcheck docs docs/_build/linkcheck
   ```
