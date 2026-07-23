"""Read, write, and validate ``sim-object/v1`` manifests.

Geometry records the source axis-aligned bounds, the processed visual's
oriented bounds, and mass properties derived from the published collision
parts. Inertia is stored per unit mass about the recorded center of mass.

The ``sha256`` object maps ordinary artifact paths directly to file digests.
Reserved entries fingerprint ``schema``, ``geometry``, and ``recipe``; the
``collision`` entry fingerprints every collision-relative filename and file
digest; and ``sha256`` fingerprints all other entries in the hash map. Thus
metadata edits and collision changes, additions, removals, or renames are
detectable without recomputing geometry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .manifest import (
    MANIFEST_NAME,
    OBJECT_SCHEMA_VERSION,
    load_manifest,
    relative_artifact_path,
    sha256_directory,
    sha256_file,
    sha256_json,
    verify_sha256_map,
    write_manifest,
)

_RESERVED_SHA256_KEYS = frozenset(
    {"schema", "geometry", "recipe", "collision", "sha256"}
)


def write_object_manifest(
    path: str | Path,
    *,
    source_aabb_center: list[float],
    source_aabb_extents: list[float],
    obb: dict[str, object],
    mass_properties: dict[str, object],
    recipe: dict[str, object],
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
    hashes = {
        relative_artifact_path(root, artifact): sha256_file(artifact)
        for artifact in artifact_paths
    }
    hashes["collision"] = sha256_directory(root / "collision")
    for name, value in (
        ("schema", OBJECT_SCHEMA_VERSION),
        ("geometry", geometry),
        ("recipe", recipe),
    ):
        hashes[name] = sha256_json(value)
    hashes["sha256"] = sha256_json(hashes)
    manifest: dict[str, object] = {
        "schema": OBJECT_SCHEMA_VERSION,
        "geometry": geometry,
        "sha256": hashes,
        "recipe": recipe,
    }
    write_manifest(path, manifest)


def check_object_manifest(path_or_directory: str | Path) -> list[str]:
    """Verify an object manifest's fingerprints and artifact hashes."""
    manifest_path = Path(path_or_directory)
    if manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    if manifest.get("schema") != OBJECT_SCHEMA_VERSION:
        raise ValueError(
            f"Manifest schema is not an object: {manifest.get('schema')!r}"
        )
    root = manifest_path.parent
    errors: list[str] = []

    geometry = manifest.get("geometry")
    recipe = manifest.get("recipe")
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        return ["manifest sha256 must be an object"]

    for name, value in (
        ("schema", manifest.get("schema")),
        ("geometry", geometry),
        ("recipe", recipe),
    ):
        _check_fingerprint(name, value, hashes.get(name), errors)
    other_hashes = {name: value for name, value in hashes.items() if name != "sha256"}
    _check_fingerprint("sha256", other_hashes, hashes.get("sha256"), errors)

    _check_collision_fingerprint(root / "collision", hashes.get("collision"), errors)
    artifact_hashes = {
        path: digest
        for path, digest in hashes.items()
        if path not in _RESERVED_SHA256_KEYS
    }
    errors.extend(verify_sha256_map(root, artifact_hashes))
    return errors


def _check_collision_fingerprint(
    directory: Path,
    expected: object,
    errors: list[str],
) -> None:
    """Report an invalid or mismatched aggregate collision fingerprint."""
    if not directory.is_dir():
        errors.append("collision directory is missing")
        return
    _check_digest(
        "collision",
        expected,
        sha256_directory(directory),
        errors,
    )


def _check_fingerprint(
    name: str,
    value: object,
    expected: object,
    errors: list[str],
) -> None:
    """Report a missing, malformed, or mismatched manifest fingerprint."""
    try:
        actual = sha256_json(value)
    except (TypeError, ValueError):
        errors.append(f"manifest {name} cannot be fingerprinted as JSON")
        return
    _check_digest(name, expected, actual, errors)


def _check_digest(
    name: str,
    expected: object,
    actual: str,
    errors: list[str],
) -> None:
    """Report a missing, malformed, or mismatched SHA-256 fingerprint."""
    if expected is None:
        errors.append(f"manifest sha256 is missing the {name} fingerprint")
        return
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        errors.append(f"manifest sha256 has an invalid {name} fingerprint")
        return
    if actual != expected:
        errors.append(f"manifest {name} fingerprint does not match")
