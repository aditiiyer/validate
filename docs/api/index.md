# API Reference

Every module, class and function, generated from the docstrings. For how they fit together,
see {doc}`../developer_guide/architecture`.

## Running an analysis

```{eval-rst}
.. autosummary::
   :toctree: generated
   :nosignatures:

   validate.run
   validate.logs
   validate.notify
```

## Settings and data

```{eval-rst}
.. autosummary::
   :toctree: generated
   :nosignatures:

   validate.core.analysis
   validate.core.data_capsule
   validate.data_io.read_inputs
   validate.data_io.build_capsule
```

## Segmentation and modelling

```{eval-rst}
.. autosummary::
   :toctree: generated
   :nosignatures:

   validate.seg.structures
   validate.seg.autoseg_pipeline
   validate.seg.model_registry
   validate.modeling.apply_model
```

## GUI

```{eval-rst}
.. autosummary::
   :toctree: generated
   :nosignatures:

   validate.gui.main_window
   validate.gui.segment_tab
   validate.gui.model_tab
   validate.gui.performance_tab
   validate.gui.progress_and_logging
   validate.gui.worker
   validate.gui.theme
```
