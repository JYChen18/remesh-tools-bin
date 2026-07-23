"""Prepare portable, simulation-ready mesh and model assets."""

from __future__ import annotations

from .formats.manifest import (
    MANIFEST_NAME,
    SCHEMA_VERSION,
    load_manifest,
)
from .native import native_bin_dir, run_native

__all__ = [
    "MANIFEST_NAME",
    "SCHEMA_VERSION",
    "load_manifest",
    "native_bin_dir",
    "run_native",
]

__version__ = "0.2.0"
