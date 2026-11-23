# VALIDATE

**VALIDATE** (VALIdation of Decision support models for rAdioThErapy) checks published
radiotherapy outcome models on your own patients. It applies a dosimetric (NTCP) model to a
local cohort: it auto-segments the structures the model needs, computes dose-volume metrics
and the NTCP for each patient, and (soon) assesses how well the model performs.
The models are shared; patient data stay at your site.

::::{grid} 1 1 3 3
:gutter: 3

:::{grid-item-card} {octicon}`person` User Guide
:link: user_guide/index
:link-type: doc

Install VALIDATE and use the GUI: segment a cohort, run a model, read the results.
:::

:::{grid-item-card} {octicon}`code` Developer Guide
:link: developer_guide/index
:link-type: doc

How the code fits together, how to extend it, and how to test and release it.
:::

:::{grid-item-card} {octicon}`book` API Reference
:link: api/index
:link-type: doc

Every module, class and function, from the docstrings.
:::
::::

```{toctree}
:hidden:
:maxdepth: 2

user_guide/index
developer_guide/index
api/index
```
