"""Python launchers for packaged native remeshing tools."""

from __future__ import annotations

__all__ = ["available_methods", "native_bin_dir", "run_native"]


def available_methods() -> tuple[str, ...]:
    from ._cli import available_methods as _available_methods

    return _available_methods()


def native_bin_dir():
    from ._cli import native_bin_dir as _native_bin_dir

    return _native_bin_dir()


def run_native(*args, **kwargs):
    from ._cli import run_native as _run_native

    return _run_native(*args, **kwargs)
