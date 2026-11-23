"""Sphinx configuration for the Validate documentation.

Build from the repository root:

    pip install -r docs/requirements.txt
    sphinx-build -W -b html docs docs/_build/html

The repository root is itself the "validate" package, so its parent folder is put on
sys.path for the API reference. The heavy dependencies (pyCERR, PyQt5, ...) are mocked,
so the docs build without installing them.
"""

import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO.parent))

with open(REPO / "pyproject.toml", "rb") as f:
    _project = tomllib.load(f)["project"]

project = "VALIDATE"
author = "Aditi Iyer"
copyright = "2026, the VALIDATE consortium"
release = _project["version"]
version = release

extensions = [
    "myst_parser",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinxcontrib.mermaid",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

exclude_patterns = ["_build", "_scripts", "api/generated/*.rst.tmp", "Thumbs.db", ".DS_Store"]
templates_path = ["_templates"]

# MyST: ::: fences for directives, {attribution} etc., and anchors for ## headings
myst_enable_extensions = ["colon_fence", "deflist", "attrs_block", "attrs_inline", "substitution"]
myst_heading_anchors = 3
myst_substitutions = {"version": release}

# API reference (Google-style docstrings)
autosummary_generate = True
autodoc_mock_imports = ["cerr", "PyQt5", "SimpleITK", "pydicom", "psutil", "pandas", "yaml"]
autodoc_default_options = {"members": True, "undoc-members": False, "show-inheritance": True}
autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_rtype = False

# Mermaid diagrams: sized to their content, without the full-screen button
mermaid_height = "auto"
mermaid_fullscreen = False

# HTML
html_theme = "pydata_sphinx_theme"
html_title = f"VALIDATE {release}"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "navbar_align": "left",
    "header_links_before_dropdown": 4,
    "show_toc_level": 2,
    "navigation_with_keys": False,
    "secondary_sidebar_items": ["page-toc"],
    "icon_links": [
        {"name": "GitHub", "url": "https://github.com/aditiiyer/validate", "icon": "fa-brands fa-github"},
    ],
    "footer_start": ["copyright"],
    "footer_end": ["sphinx-version"],
}
html_context = {"default_mode": "auto"}
