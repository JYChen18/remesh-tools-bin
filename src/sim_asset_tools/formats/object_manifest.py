"""Read, write, and validate object-shaped ``sim-asset/v2`` manifests.

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

from pathlib import Path
from typing import Iterable

from .manifest import (
    MANIFEST_NAME,
    SCHEMA_VERSION,
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

_RESERVED_SHA256_KEYS = frozenset(
    {"schema", "geometry", "surfaces", "recipe", "collision", "sha256"}
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
        ("schema", SCHEMA_VERSION),
        ("geometry", geometry),
        ("surfaces", surfaces),
        ("recipe", recipe),
    ):
        hashes[name] = sha256_json(value)
    hashes["sha256"] = sha256_json(hashes)
    manifest: dict[str, object] = {
        "schema": SCHEMA_VERSION,
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
    root = manifest_path.parent
    errors: list[str] = []

    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        return ["manifest sha256 must be an object"]

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
    return errors


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


def _check_collision_fingerprint(
    directory: Path,
    expected: object,
    errors: list[str],
) -> None:
    """Report an invalid or mismatched aggregate collision fingerprint."""
    if not directory.is_dir():
        errors.append("collision directory is missing")
        return
    verify_digest(
        "collision",
        expected,
        sha256_directory(directory),
        errors,
    )
