"""Prepare self-describing visual, collision, MJCF, and URDF object assets."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .. import __version__
from ..formats.manifest import (
    MANIFEST_NAME,
    SCHEMA_VERSION,
    load_manifest,
    relative_artifact_path,
    resolve_artifact,
    sha256_file,
    verify_file_records,
    write_manifest,
)
from ..formats.mjcf import write_object_mjcf
from ..formats.urdf import write_object_urdf
from ..mesh.coacd import decompose_mesh
from ..mesh.io import load_mesh
from ..mesh.normalize import normalize_mesh
from ..mesh.validation import validate_mesh
from .._publish import (
    create_staging_directory,
    ensure_output_available,
    ensure_safe_output,
    publish_directory,
)
from ._surface import SurfaceRecipe, prepare_surface

SUPPORTED_INPUT_SUFFIXES = frozenset({".glb", ".obj", ".ply", ".stl"})


@dataclass(frozen=True)
class ObjectRecipe:
    """Deterministic object preparation settings."""

    normalize: bool = True
    resolution: float = 50.0
    level_set: float = 0.1
    target_vertices: int = 1024
    gradation: float = 1.5
    force_manifold: int = 1
    coacd_threshold: float = 0.05
    coacd_max_convex_hull: int = -1
    coacd_preprocess_mode: str = "auto"
    coacd_preprocess_resolution: int = 50
    coacd_real_metric: bool = False
    seed: int | None = 0

    @property
    def surface(self) -> SurfaceRecipe:
        return SurfaceRecipe(
            resolution=self.resolution,
            level_set=self.level_set,
            target_vertices=self.target_vertices,
            gradation=self.gradation,
            force_manifold=self.force_manifold,
        )


@dataclass(frozen=True)
class ObjectResult:
    """Paths produced for one prepared object."""

    output_directory: Path
    manifest_path: Path
    mjcf_path: Path | None
    urdf_path: Path | None


def _record(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": relative_artifact_path(root, path),
        "sha256": sha256_file(path),
    }


def _mass_properties(mesh) -> dict[str, object]:
    import numpy as np

    volume = float(mesh.volume)
    return {
        "reference_density": 1.0,
        "volume": volume,
        "mass": volume,
        "center_of_mass": np.asarray(mesh.center_mass, dtype=float).tolist(),
        "inertia": np.asarray(mesh.moment_inertia, dtype=float).tolist(),
    }


def prepare_object(
    input_path: str | Path,
    output_directory: str | Path,
    *,
    recipe: ObjectRecipe | None = None,
    formats: tuple[str, ...] = ("mjcf", "urdf"),
    overwrite: bool = False,
) -> ObjectResult:
    """Prepare one input mesh as a versioned simulation object bundle."""
    import trimesh

    input_path = Path(input_path).expanduser().resolve()
    output_directory = Path(output_directory).expanduser().resolve()
    recipe = recipe or ObjectRecipe()
    formats = tuple(dict.fromkeys(formats))
    if not formats:
        raise ValueError("At least one object output format is required")
    unsupported_formats = sorted(set(formats) - {"mjcf", "urdf"})
    if unsupported_formats:
        raise ValueError(
            f"Unsupported object output formats: {', '.join(unsupported_formats)}"
        )
    if not input_path.is_file():
        raise ValueError(f"Input mesh does not exist: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
        raise ValueError(f"Unsupported input mesh suffix: {input_path.suffix}")
    ensure_safe_output(input_path, output_directory)
    ensure_output_available(output_directory, overwrite=overwrite)
    staging_directory = create_staging_directory(output_directory)

    try:
        source_directory = staging_directory / "source"
        visual_directory = staging_directory / "visual"
        collision_directory = staging_directory / "collision" / "coacd"
        models_directory = staging_directory / "models"
        for directory in (
            source_directory,
            visual_directory,
            collision_directory,
            models_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        source_copy = source_directory / f"source{input_path.suffix.lower()}"
        shutil.copy2(input_path, source_copy)
        mesh = load_mesh(input_path)
        if recipe.normalize:
            processing_mesh, center, scale = normalize_mesh(mesh)
        else:
            processing_mesh, center, scale = mesh.copy(), [0.0, 0.0, 0.0], 1.0

        with tempfile.TemporaryDirectory(
            prefix=".work-", dir=staging_directory
        ) as work_value:
            work_directory = Path(work_value)
            processing_source = work_directory / "source.obj"
            processing_mesh.export(processing_source)
            acvd_output = work_directory / "simplified.ply"
            prepare_surface(
                processing_source,
                acvd_output,
                work_directory / "surface",
                recipe.surface,
            )
            visual_mesh = load_mesh(acvd_output)
            visual_path = visual_directory / "mesh.obj"
            visual_mesh.export(visual_path)

        collision_meshes = decompose_mesh(
            visual_mesh,
            threshold=recipe.coacd_threshold,
            max_convex_hull=recipe.coacd_max_convex_hull,
            preprocess_mode=recipe.coacd_preprocess_mode,
            preprocess_resolution=recipe.coacd_preprocess_resolution,
            real_metric=recipe.coacd_real_metric,
            seed=recipe.seed,
        )
        if not collision_meshes:
            raise RuntimeError("CoACD did not produce any collision parts")
        collision_paths: list[Path] = []
        for index, collision_mesh in enumerate(collision_meshes):
            errors = validate_mesh(collision_mesh)
            if errors:
                raise ValueError(f"CoACD part {index} is invalid: {'; '.join(errors)}")
            collision_path = collision_directory / f"part_{index:03d}.obj"
            collision_mesh.export(collision_path)
            collision_paths.append(collision_path)

        mjcf_path = models_directory / "model.xml" if "mjcf" in formats else None
        urdf_path = models_directory / "model.urdf" if "urdf" in formats else None
        if mjcf_path is not None:
            write_object_mjcf(mjcf_path, visual_path, collision_paths)
        if urdf_path is not None:
            write_object_urdf(urdf_path, visual_path, collision_paths)
        combined_collision = trimesh.util.concatenate(collision_meshes)
        manifest = {
            "schema": SCHEMA_VERSION,
            "kind": "object",
            "tool": {"name": "sim-asset-tools", "version": __version__},
            "source": _record(staging_directory, source_copy),
            "transform": {
                "normalized": recipe.normalize,
                "center": center,
                "scale": scale,
            },
            "visual": {"mesh": _record(staging_directory, visual_path)},
            "collision": {
                "type": "convex_decomposition",
                "parts": [_record(staging_directory, path) for path in collision_paths],
            },
            "models": {
                name: _record(staging_directory, path)
                for name, path in (("mjcf", mjcf_path), ("urdf", urdf_path))
                if path is not None
            },
            "mass_properties": _mass_properties(combined_collision),
            "recipes": {"object": asdict(recipe)},
        }
        write_manifest(staging_directory / MANIFEST_NAME, manifest)
        publish_directory(
            staging_directory,
            output_directory,
            overwrite=overwrite,
        )
    except BaseException:
        if staging_directory.exists():
            shutil.rmtree(staging_directory)
        raise

    final_models_directory = output_directory / "models"
    return ObjectResult(
        output_directory,
        output_directory / MANIFEST_NAME,
        final_models_directory / "model.xml" if "mjcf" in formats else None,
        final_models_directory / "model.urdf" if "urdf" in formats else None,
    )


def check_object(path_or_directory: str | Path) -> list[str]:
    """Return consistency errors for one object bundle."""
    manifest_path = Path(path_or_directory)
    if manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    if manifest.get("kind") != "object":
        return [f"manifest kind is not object: {manifest.get('kind')!r}"]
    root = manifest_path.parent
    errors: list[str] = []
    records: list[dict[str, object]] = []
    mesh_records: list[dict[str, object]] = []

    source = manifest.get("source")
    if isinstance(source, dict):
        records.append(source)
    else:
        errors.append("manifest source must be an object")

    visual = manifest.get("visual")
    visual_mesh = visual.get("mesh") if isinstance(visual, dict) else None
    if isinstance(visual_mesh, dict):
        records.append(visual_mesh)
        mesh_records.append(visual_mesh)
    else:
        errors.append("manifest visual mesh must be an object")

    collision = manifest.get("collision")
    collision_parts = collision.get("parts") if isinstance(collision, dict) else None
    if isinstance(collision_parts, list):
        for index, record in enumerate(collision_parts):
            if isinstance(record, dict):
                records.append(record)
                mesh_records.append(record)
            else:
                errors.append(f"manifest collision part {index} must be an object")
    else:
        errors.append("manifest collision parts must be an array")

    models = manifest.get("models")
    if isinstance(models, dict):
        for name, record in models.items():
            if isinstance(record, dict):
                records.append(record)
            else:
                errors.append(f"manifest model {name!r} must be an object")
    else:
        errors.append("manifest models must be an object")

    errors.extend(verify_file_records(root, records))
    for record in mesh_records:
        if not isinstance(record.get("path"), str):
            continue
        try:
            artifact = resolve_artifact(root, record["path"])
            if artifact.is_file():
                errors.extend(
                    f"{record['path']}: {error}"
                    for error in validate_mesh(load_mesh(artifact))
                )
        except ValueError as exc:
            errors.append(str(exc))
    return errors
