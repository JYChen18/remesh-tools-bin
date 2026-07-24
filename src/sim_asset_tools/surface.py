"""Generic OpenVDB-to-ACVD surface-generation primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mesh.acvd import acvd_remesh
from .mesh.openvdb import openvdb_sdf


@dataclass(frozen=True)
class SurfaceRecipe:
    """Parameters for producing a watertight, reduced surface mesh."""

    resolution: float = 50.0
    level_set: float = 0.1
    target_vertices: int = 1024
    gradation: float = 1.5
    force_manifold: int = 1


def prepare_surface(
    input_path: str | Path,
    output_path: str | Path,
    work_directory: str | Path,
    recipe: SurfaceRecipe,
) -> Path:
    """Apply OpenVDB cleanup followed by ACVD reduction."""
    work_directory = Path(work_directory)
    work_directory.mkdir(parents=True, exist_ok=True)
    sdf_path = openvdb_sdf(
        input_path,
        work_directory / "openvdb.obj",
        resolution=recipe.resolution,
        level_set=recipe.level_set,
    )
    return acvd_remesh(
        sdf_path,
        output_path,
        vertices=recipe.target_vertices,
        gradation=recipe.gradation,
        force_manifold=recipe.force_manifold,
    )
