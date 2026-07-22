"""Runtime access to packaged ACVD and OpenVDB executables."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


NATIVE_TOOLS = frozenset(
    {
        "ACVD",
        "ACVDP",
        "ACVDQ",
        "ACVDQP",
        "AnisotropicRemeshing",
        "AnisotropicRemeshingQ",
        "AnisotropicRemeshingQP",
        "OpenVDBSdfRemesh",
        "VolumeAnalysis",
    }
)


def _native_root() -> Path:
    source_candidate = Path(__file__).resolve().parent / "_native"
    if source_candidate.is_dir():
        return source_candidate
    for entry in sys.path:
        candidate = Path(entry or ".").resolve() / "sim_asset_tools" / "_native"
        if candidate.is_dir():
            return candidate
    return source_candidate


def native_bin_dir() -> Path:
    """Return the directory containing packaged native executables."""
    return _native_root() / "bin"


def _native_lib_dir() -> Path:
    return _native_root() / "lib"


def _vendored_library_dirs() -> tuple[Path, ...]:
    package_dir = Path(__file__).resolve().parent
    candidates = [package_dir.parent / "sim_asset_tools.libs"]
    for entry in sys.path:
        root = Path(entry or ".").resolve()
        candidates.append(root / "sim_asset_tools.libs")
    return tuple(dict.fromkeys(path for path in candidates if path.is_dir()))


def _vtkmodules_dir() -> Path:
    try:
        import vtkmodules
    except ImportError as exc:
        raise RuntimeError(
            "Native OpenVDB and ACVD operations require vtk==9.6.2"
        ) from exc
    if vtkmodules.__file__ is None:
        raise RuntimeError("Could not locate the installed vtkmodules package")
    return Path(vtkmodules.__file__).resolve().parent


def _vtk_library_dirs() -> tuple[Path, ...]:
    vtkmodules_dir = _vtkmodules_dir()
    candidates = (
        vtkmodules_dir / ".dylibs",
        vtkmodules_dir / ".libs",
        vtkmodules_dir.parent / "vtk.libs",
        vtkmodules_dir,
    )
    return tuple(path for path in candidates if path.exists())


def _prepend_path(env: dict[str, str], key: str, paths: Iterable[Path]) -> None:
    prefix = os.pathsep.join(str(path) for path in paths)
    existing = env.get(key)
    env[key] = prefix if not existing else f"{prefix}{os.pathsep}{existing}"


def _native_env() -> dict[str, str]:
    env = os.environ.copy()
    library_paths = (
        native_bin_dir(),
        _native_lib_dir(),
        *_vendored_library_dirs(),
        *_vtk_library_dirs(),
    )
    if os.name == "nt":
        _prepend_path(env, "PATH", library_paths)
    elif sys.platform == "darwin":
        _prepend_path(env, "DYLD_LIBRARY_PATH", library_paths)
    else:
        _prepend_path(env, "LD_LIBRARY_PATH", library_paths)
    return env


def _tool_path(tool: str) -> Path:
    if tool not in NATIVE_TOOLS:
        raise ValueError(f"Unknown native tool {tool!r}")
    executable = native_bin_dir() / (f"{tool}.exe" if os.name == "nt" else tool)
    if not executable.is_file():
        raise RuntimeError(f"Native executable is missing: {executable}")
    return executable


def run_native(
    tool: str,
    args: Iterable[str] | None = None,
    *,
    check: bool = False,
    cwd: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one packaged native executable."""
    return subprocess.run(
        [str(_tool_path(tool)), *(args or ())],
        env=_native_env(),
        check=check,
        cwd=cwd,
        text=True,
    )
