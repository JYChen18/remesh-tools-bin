"""Deprecated command compatibility for remesh-tools-bin users."""

from __future__ import annotations

import warnings
from typing import Sequence

from remesh_tools_bin._cli import main as _legacy_main


def main(argv: Sequence[str] | None = None) -> int:
    """Run the legacy ``remesh`` command with a deprecation warning."""
    warnings.warn(
        "remesh is deprecated; use sim-assets mesh openvdb or sim-assets mesh acvd",
        FutureWarning,
        stacklevel=2,
    )
    return _legacy_main(argv)
