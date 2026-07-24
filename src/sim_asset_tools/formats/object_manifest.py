"""Read, write, and validate ``sim-asset/object/v1`` manifests.

Geometry records the source axis-aligned bounds, the processed visual's
oriented bounds, and mass properties derived from the published collision
parts. Inertia is stored per unit mass about the recorded center of mass.

The ``sha256`` object maps ordinary artifact paths directly to file digests.
Reserved entries fingerprint ``schema``, ``geometry``, ``surfaces``, and
``recipe``; the ``collision`` entry fingerprints every collision-relative
filename and file digest; and ``sha256`` fingerprints all other entries in the
hash map. Thus metadata edits and collision changes, additions, removals, or
renames are detectable without recomputing geometry.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

from .manifest import (
    MANIFEST_NAME,
    load_manifest,
    relative_artifact_path,
    resolve_artifact,
    sha256_directory,
    sha256_file,
    sha256_json,
    verify_digest,
    verify_manifest_metadata,
    verify_sha256_map,
    write_manifest,
)

OBJECT_MANIFEST_SCHEMA = "sim-asset/object/v1"

_RESERVED_SHA256_KEYS = frozenset(
    {"schema", "geometry", "surfaces", "recipe", "collision", "sha256"}
)
_TOP_LEVEL_KEYS = frozenset({"schema", "geometry", "recipe", "sha256", "surfaces"})
_GEOMETRY_KEYS = frozenset(
    {
        "source_aabb_center",
        "source_aabb_extents",
        "obb_center",
        "obb_axes",
        "obb_extents",
        "volume",
        "center_of_mass",
        "inertia_per_unit_mass",
    }
)


def write_object_manifest(
    path: str | Path,
    *,
    source_aabb_center: list[float],
    source_aabb_extents: list[float],
    obb: dict[str, object],
    mass_properties: dict[str, object],
    recipe: dict[str, object],
    surface: Path,
    artifacts: Iterable[Path],
) -> None:
    """Build, fingerprint, and atomically write an object manifest."""
    path = Path(path)
    root = path.parent
    geometry = {
        "source_aabb_center": source_aabb_center,
        "source_aabb_extents": source_aabb_extents,
        "obb_center": obb["center"],
        "obb_axes": obb["axes"],
        "obb_extents": obb["extents"],
        "volume": mass_properties["volume"],
        "center_of_mass": mass_properties["center_of_mass"],
        "inertia_per_unit_mass": mass_properties["inertia_per_unit_mass"],
    }
    artifact_paths = sorted(
        artifacts,
        key=lambda artifact: relative_artifact_path(root, artifact),
    )
    surfaces = {"object": relative_artifact_path(root, surface)}
    hashes = {
        relative_artifact_path(root, artifact): sha256_file(artifact)
        for artifact in artifact_paths
    }
    hashes["collision"] = sha256_directory(root / "collision")
    for name, value in (
        ("schema", OBJECT_MANIFEST_SCHEMA),
        ("geometry", geometry),
        ("surfaces", surfaces),
        ("recipe", recipe),
    ):
        hashes[name] = sha256_json(value)
    hashes["sha256"] = sha256_json(hashes)
    manifest: dict[str, object] = {
        "schema": OBJECT_MANIFEST_SCHEMA,
        "geometry": geometry,
        "recipe": recipe,
        "sha256": hashes,
        "surfaces": surfaces,
    }
    write_manifest(path, manifest)


def check_object_manifest(path_or_directory: str | Path) -> list[str]:
    """Verify an object manifest's fingerprints and artifact hashes."""
    manifest_path = Path(path_or_directory)
    if manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    schema = manifest.get("schema")
    if schema != OBJECT_MANIFEST_SCHEMA:
        raise ValueError(
            f"Unsupported object manifest schema {schema!r}; "
            f"expected {OBJECT_MANIFEST_SCHEMA!r}. Regenerate the object bundle."
        )
    root = manifest_path.parent
    errors: list[str] = []

    _check_metadata_shapes(manifest, errors)
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        errors.append("manifest sha256 must be an object")
        return errors

    errors.extend(
        verify_manifest_metadata(
            manifest,
            ("schema", "geometry", "surfaces", "recipe"),
        )
    )

    _check_collision_fingerprint(root / "collision", hashes.get("collision"), errors)
    artifact_hashes = {
        path: digest
        for path, digest in hashes.items()
        if path not in _RESERVED_SHA256_KEYS
    }
    errors.extend(verify_sha256_map(root, artifact_hashes))
    _check_object_surfaces(
        root,
        manifest.get("surfaces"),
        artifact_hashes,
        errors,
    )
    _check_object_meshes(root, manifest.get("surfaces"), errors)
    return errors


def _check_metadata_shapes(
    manifest: dict[str, object],
    errors: list[str],
) -> None:
    """Validate the object schema's required top-level metadata structures."""
    if set(manifest) != _TOP_LEVEL_KEYS:
        errors.append(
            "object manifest must contain exactly: "
            + ", ".join(sorted(_TOP_LEVEL_KEYS))
        )

    geometry = manifest.get("geometry")
    if not isinstance(geometry, dict):
        errors.append("manifest geometry must be an object")
    else:
        _check_geometry_shape(geometry, errors)

    if not isinstance(manifest.get("recipe"), dict):
        errors.append("manifest recipe must be an object")

    if not isinstance(manifest.get("surfaces"), dict):
        errors.append("manifest surfaces must be an object")


def _check_geometry_shape(
    geometry: dict[object, object],
    errors: list[str],
) -> None:
    """Validate required object geometry fields and their numeric shapes."""
    if set(geometry) != _GEOMETRY_KEYS:
        errors.append(
            "manifest geometry must contain exactly: "
            + ", ".join(sorted(_GEOMETRY_KEYS))
        )
        return

    for name in (
        "source_aabb_center",
        "obb_center",
        "center_of_mass",
    ):
        if not _is_numeric_array(geometry[name], (3,)):
            errors.append(f"manifest geometry {name} must be a finite 3-vector")

    source_extents = geometry["source_aabb_extents"]
    if not _is_numeric_array(source_extents, (3,)) or not all(
        item >= 0 for item in source_extents
    ):
        errors.append(
            "manifest geometry source_aabb_extents must be a nonnegative finite "
            "3-vector"
        )

    obb_extents = geometry["obb_extents"]
    if not _is_numeric_array(obb_extents, (3,)) or not all(
        item > 0 for item in obb_extents
    ):
        errors.append(
            "manifest geometry obb_extents must be a positive finite 3-vector"
        )

    for name in ("obb_axes", "inertia_per_unit_mass"):
        if not _is_numeric_array(geometry[name], (3, 3)):
            errors.append(f"manifest geometry {name} must be a finite 3-by-3 matrix")

    if not _is_finite_number(geometry["volume"]) or geometry["volume"] <= 0:
        errors.append("manifest geometry volume must be a positive finite number")


def _is_finite_number(value: object) -> bool:
    """Return whether a JSON value is a finite, non-boolean number."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_numeric_array(value: object, shape: tuple[int, ...]) -> bool:
    """Return whether nested lists have one exact shape and finite numbers."""
    if not shape:
        return _is_finite_number(value)
    if not isinstance(value, list) or len(value) != shape[0]:
        return False
    return all(_is_numeric_array(item, shape[1:]) for item in value)


def _check_object_surfaces(
    root: Path,
    value: object,
    artifact_hashes: dict[object, object],
    errors: list[str],
) -> None:
    """Validate the required object-local sampling surface."""
    if not isinstance(value, dict):
        errors.append("manifest surfaces must be an object")
        return
    if set(value) != {"object"}:
        errors.append("object manifest surfaces must contain exactly 'object'")
        return
    relative = value.get("object")
    if not isinstance(relative, str):
        errors.append("object surface path must be a string")
        return
    try:
        path = resolve_artifact(root, relative)
    except ValueError as exc:
        errors.append(str(exc))
        return
    if relative not in artifact_hashes:
        errors.append(f"object surface is not fingerprinted: {relative}")
    if not path.is_file():
        errors.append(f"object surface is missing: {relative}")


def _check_object_meshes(
    root: Path,
    surfaces: object,
    errors: list[str],
) -> None:
    """Load and validate the visual mesh and every published collision OBJ."""
    if isinstance(surfaces, dict) and isinstance(surfaces.get("object"), str):
        try:
            visual_path = resolve_artifact(root, surfaces["object"])
        except ValueError:
            pass
        else:
            if visual_path.is_file():
                _check_mesh(visual_path, "visual", errors)

    collision_directory = root / "collision"
    if collision_directory.is_symlink() or not collision_directory.is_dir():
        return
    collision_paths: list[Path] = []
    for path in sorted(collision_directory.iterdir()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            errors.append(f"unexpected collision symlink: {relative}")
            continue
        if not path.is_file() or path.suffix.lower() != ".obj":
            errors.append(f"unexpected collision artifact: {relative}")
            continue
        collision_paths.append(path)
    if not collision_paths:
        errors.append("collision directory must contain at least one OBJ mesh")
        return
    for path in collision_paths:
        relative = path.relative_to(root).as_posix()
        _check_mesh(path, f"collision mesh {relative}", errors)


def _check_mesh(path: Path, label: str, errors: list[str]) -> None:
    """Append loading or structural validation errors for one published mesh."""
    from ..mesh.io import load_mesh
    from ..mesh.validation import validate_mesh

    try:
        mesh = load_mesh(path)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        errors.append(f"{label} could not be loaded: {exc}")
        return
    for error in validate_mesh(mesh, watertight=True):
        errors.append(f"{label} is invalid: {error}")


def _check_collision_fingerprint(
    directory: Path,
    expected: object,
    errors: list[str],
) -> None:
    """Report an invalid or mismatched aggregate collision fingerprint."""
    if directory.is_symlink():
        errors.append("collision directory must not be a symbolic link")
        return
    if not directory.is_dir():
        errors.append("collision directory is missing")
        return
    try:
        actual = sha256_directory(directory)
    except (OSError, ValueError) as exc:
        errors.append(f"could not fingerprint collision directory: {exc}")
        return
    verify_digest(
        "collision",
        expected,
        actual,
        errors,
    )
