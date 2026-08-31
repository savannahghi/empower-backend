"""Sphinx documentation configuration."""
project = "Advantage Backend"
copyright = "2023, Savannah Informatics Limited"
author = "Savannah Informatics Limited"

extensions = [
    "sphinx_rtd_theme",
    "sphinx_diagrams",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
