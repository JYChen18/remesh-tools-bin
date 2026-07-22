"""OpenVDB signed-distance-field raw-mesh processing."""

from __future__ import annotations

from pathlib import Path

from ..native import run_native


def openvdb_sdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    resolution: float = 50.0,
    level_set: float = 0.1,
    normalize: bool = True,
) -> Path:
    """Convert a mesh through an OpenVDB SDF and require a non-empty output."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    arguments = [
        str(input_path),
        str(output_path),
        "--resolution",
        str(resolution),
        "--level-set",
        str(level_set),
    ]
    if not normalize:
        arguments.append("--no-normalize")
    result = run_native("OpenVDBSdfRemesh", arguments)
    if result.returncode != 0:
        raise RuntimeError(
            f"OpenVDB processing failed with exit code {result.returncode}"
        )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"OpenVDB did not create {output_path}")
    return output_path
