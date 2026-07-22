"""ACVD raw-mesh processing."""

from __future__ import annotations

import os
from pathlib import Path

from ..native import run_native


METHOD_TO_TOOL = {
    "acvd": "ACVD",
    "acvd-parallel": "ACVDP",
    "acvd-quadric": "ACVDQ",
    "acvd-quadric-parallel": "ACVDQP",
    "acvd-anisotropic": "AnisotropicRemeshing",
    "acvd-anisotropic-quadric": "AnisotropicRemeshingQ",
    "acvd-anisotropic-quadric-parallel": "AnisotropicRemeshingQP",
}

_ANISOTROPIC_OUTPUTS = {
    "AnisotropicRemeshing": "output.ply",
    "AnisotropicRemeshingQ": "Remeshing.ply",
    "AnisotropicRemeshingQP": "Remeshing.ply",
}


def available_methods() -> tuple[str, ...]:
    """Return the available ACVD variants."""
    return tuple(sorted(METHOD_TO_TOOL))


def _append(arguments: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        arguments.extend((flag, str(value)))


def acvd_remesh(
    input_path: str | Path,
    output_path: str | Path,
    *,
    method: str = "acvd",
    vertices: int = 1024,
    gradation: float = 1.5,
    force_manifold: int = 1,
    threads: int | None = None,
    quadric_level: int | None = None,
    boundary_fixing: int | None = None,
    subsample: int | None = None,
    split_long_edges: float | None = None,
    display: int | None = None,
) -> Path:
    """Run one ACVD variant and require a non-empty output."""
    if method not in METHOD_TO_TOOL:
        raise ValueError(f"Unsupported ACVD method: {method!r}")
    tool = METHOD_TO_TOOL[method]
    is_anisotropic = tool in _ANISOTROPIC_OUTPUTS
    if threads is not None and "parallel" not in method:
        raise ValueError(f"Method {method!r} does not accept threads")
    if quadric_level is not None and "quadric" not in method:
        raise ValueError(f"Method {method!r} does not accept a quadric level")
    if boundary_fixing is not None and is_anisotropic and "quadric" not in method:
        raise ValueError(f"Method {method!r} does not accept boundary fixing")

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parent = f"{output_path.parent}{os.sep}"
    arguments = [str(input_path), str(vertices), f"{gradation:g}", "-o", parent]
    if not is_anisotropic:
        arguments.extend(("-of", output_path.name))
    _append(arguments, "-s", subsample)
    _append(arguments, "-l", split_long_edges)
    _append(arguments, "-d", display)
    _append(arguments, "-b", boundary_fixing)
    if not is_anisotropic:
        _append(arguments, "-m", force_manifold)
    _append(arguments, "-q", quadric_level)
    _append(arguments, "-np", threads)

    generated = output_path
    if is_anisotropic:
        generated = output_path.parent / _ANISOTROPIC_OUTPUTS[tool]
        if generated.exists() and generated != output_path:
            generated.unlink()
    result = run_native(tool, arguments)
    if result.returncode != 0:
        raise RuntimeError(f"ACVD failed with exit code {result.returncode}")
    if is_anisotropic and generated != output_path:
        if not generated.is_file():
            raise RuntimeError(f"ACVD did not create {generated}")
        os.replace(generated, output_path)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"ACVD did not create {output_path}")
    return output_path
