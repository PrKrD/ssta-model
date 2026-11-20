"""Smoke checks for the installed package."""

import importlib
from importlib.metadata import version


def test_installed_package_imports():
    """Resolve distribution metadata and import every initial package boundary."""
    assert version("ssta-model")
    for name in ("ssta_model", "core", "physics", "forcing", "data", "analysis"):
        qualified_name = name if name == "ssta_model" else f"ssta_model.{name}"
        module = importlib.import_module(qualified_name)
        assert module.__name__ == qualified_name
