# Copyright 2026 The Newton Developers
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Prepare reusable, body-local surface assets from compiled MuJoCo models.

New assets use the common ``sim-asset/v2`` manifest. The ``surfaces`` mapping
keys meshes by exact model-local body name and stores safe, readable filenames
relative to the manifest. Only multi-geom collision bodies need prepared
surfaces; single-geom bodies use their compiled MuJoCo collision surfaces.
Models with the same output directory share the flat mapping, while
``surface_sets`` records model-scoped ownership and source-geometry identity.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..formats.manifest import (
    MANIFEST_NAME,
    SCHEMA_VERSION,
    load_manifest,
    resolve_artifact,
    sha256_file,
    sha256_json,
    verify_manifest_metadata,
    verify_sha256_map,
    write_manifest,
)
from ..formats.mujoco_model import (
    load_mujoco_model,
    resolve_mujoco_mesh_directory,
)
from ..mesh.io import load_mesh
from ..mesh.validation import validate_mesh
from .._publish import (
    ensure_safe_output,
    staged_directory,
)
from ._surface import SurfaceRecipe, prepare_surface

_RESERVED_SHA256_KEYS = frozenset({"schema", "surfaces", "recipe", "sha256"})
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class BodyPlan:
    """One bounded collidable MuJoCo body."""

    body_id: int
    name: str
    geom_ids: tuple[int, ...]

    @property
    def is_multi_geom(self) -> bool:
        """Whether the body requires a prepared collision surface."""
        return len(self.geom_ids) > 1


@dataclass(frozen=True)
class GeometryPlan:
    """Bounded collision bodies and unsupported geometry errors."""

    bodies: dict[int, BodyPlan]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class BodySurfaceRecipe(SurfaceRecipe):
    """Parameters for body-surface preparation."""


def _dependencies():
    import mujoco
    import numpy as np
    import trimesh

    return mujoco, np, trimesh


def _body_name(model, body_id: int) -> str:
    mujoco, _, _ = _dependencies()
    return mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or ""


def _geom_name(model, geom_id: int) -> str:
    mujoco, _, _ = _dependencies()
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id) or f"geom_{geom_id}"
    )


def _geom_type_name(value: int) -> str:
    mujoco, _, _ = _dependencies()
    return mujoco.mjtGeom(value).name.removeprefix("mjGEOM_").lower()


def analyze_geometry(model) -> GeometryPlan:
    """Analyze bounded and procedural collision geometry in a compiled model."""
    mujoco, _, _ = _dependencies()
    bounded_types = {
        int(mujoco.mjtGeom.mjGEOM_SPHERE),
        int(mujoco.mjtGeom.mjGEOM_CAPSULE),
        int(mujoco.mjtGeom.mjGEOM_CYLINDER),
        int(mujoco.mjtGeom.mjGEOM_BOX),
        int(mujoco.mjtGeom.mjGEOM_ELLIPSOID),
        int(mujoco.mjtGeom.mjGEOM_MESH),
    }
    procedural_types = {
        int(mujoco.mjtGeom.mjGEOM_PLANE),
        int(mujoco.mjtGeom.mjGEOM_HFIELD),
    }
    pair_geoms: set[int] = set()
    for pair_id in range(model.npair):
        pair_geoms.add(int(model.pair_geom1[pair_id]))
        pair_geoms.add(int(model.pair_geom2[pair_id]))

    grouped: dict[int, list[int]] = {}
    errors: list[str] = []
    for geom_id in range(model.ngeom):
        collidable = (
            int(model.geom_contype[geom_id]) != 0
            or int(model.geom_conaffinity[geom_id]) != 0
            or geom_id in pair_geoms
        )
        if not collidable:
            continue
        geom_type = int(model.geom_type[geom_id])
        body_id = int(model.geom_bodyid[geom_id])
        if geom_type not in bounded_types | procedural_types:
            errors.append(
                f"geom {_geom_name(model, geom_id)!r} (id {geom_id}, type {_geom_type_name(geom_type)}) "
                f"on body {_body_name(model, body_id) or f'body_{body_id}'!r} is unsupported"
            )
            continue
        grouped.setdefault(body_id, []).append(geom_id)

    bodies: dict[int, BodyPlan] = {}
    for body_id, geom_ids in grouped.items():
        procedural_ids = [
            geom_id
            for geom_id in geom_ids
            if int(model.geom_type[geom_id]) in procedural_types
        ]
        name = _body_name(model, body_id)
        if procedural_ids:
            if len(geom_ids) != 1:
                descriptions = ", ".join(
                    f"geom {_geom_name(model, geom_id)!r} "
                    f"(id {geom_id}, type {_geom_type_name(int(model.geom_type[geom_id]))})"
                    for geom_id in geom_ids
                )
                errors.append(
                    "a plane or heightfield must be the only collidable geom on "
                    f"body {name or f'body_{body_id}'!r} (id {body_id}): "
                    f"{descriptions}"
                )
        else:
            bodies[body_id] = BodyPlan(body_id, name, tuple(geom_ids))
    return GeometryPlan(bodies, tuple(errors))


def _rotation_matrix(quaternion):
    _, np, _ = _dependencies()
    w, x, y, z = quaternion
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float32,
    )


def _mesh_geom(model, geom_id: int):
    _, np, trimesh = _dependencies()
    mesh_id = int(model.geom_dataid[geom_id])
    vertex_start = int(model.mesh_vertadr[mesh_id])
    vertex_count = int(model.mesh_vertnum[mesh_id])
    vertices = np.asarray(
        model.mesh_vert[vertex_start : vertex_start + vertex_count], dtype=np.float32
    )
    if hasattr(model, "mesh_polyadr"):
        polygon_start = int(model.mesh_polyadr[mesh_id])
        polygon_count = int(model.mesh_polynum[mesh_id])
        polygons = []
        for polygon_id in range(polygon_start, polygon_start + polygon_count):
            start = int(model.mesh_polyvertadr[polygon_id])
            count = int(model.mesh_polyvertnum[polygon_id])
            if count >= 3:
                polygons.append(model.mesh_polyvert[start : start + count])
        faces = trimesh.geometry.triangulate_quads(polygons)
    else:
        face_start = int(model.mesh_faceadr[mesh_id])
        face_count = int(model.mesh_facenum[mesh_id])
        faces = np.asarray(
            model.mesh_face[face_start : face_start + face_count], dtype=np.int32
        )
    used, inverse = np.unique(np.asarray(faces).reshape(-1), return_inverse=True)
    return trimesh.Trimesh(
        vertices=vertices[used], faces=inverse.reshape((-1, 3)), process=False
    )


def _primitive_geom(model, geom_id: int):
    mujoco, np, trimesh = _dependencies()
    geom_type = int(model.geom_type[geom_id])
    size = np.asarray(model.geom_size[geom_id], dtype=np.float32)
    if geom_type == int(mujoco.mjtGeom.mjGEOM_SPHERE):
        return trimesh.creation.icosphere(radius=float(size[0]), subdivisions=2)
    if geom_type == int(mujoco.mjtGeom.mjGEOM_CAPSULE):
        return trimesh.creation.capsule(
            radius=float(size[0]), height=float(2 * size[1])
        )
    if geom_type == int(mujoco.mjtGeom.mjGEOM_CYLINDER):
        return trimesh.creation.cylinder(
            radius=float(size[0]), height=float(2 * size[1])
        )
    if geom_type == int(mujoco.mjtGeom.mjGEOM_BOX):
        return trimesh.creation.box(extents=2 * size[:3])
    if geom_type == int(mujoco.mjtGeom.mjGEOM_ELLIPSOID):
        mesh = trimesh.creation.icosphere(radius=1.0, subdivisions=2)
        mesh.vertices = np.asarray(mesh.vertices, dtype=np.float32) * size[:3]
        return mesh
    raise AssertionError(
        f"unsupported primitive geom type: {_geom_type_name(geom_type)}"
    )


def _geom_mesh(model, geom_id: int):
    mujoco, np, trimesh = _dependencies()
    if int(model.geom_type[geom_id]) == int(mujoco.mjtGeom.mjGEOM_MESH):
        mesh = _mesh_geom(model, geom_id)
    else:
        mesh = _primitive_geom(model, geom_id)
    rotation = _rotation_matrix(np.asarray(model.geom_quat[geom_id], dtype=np.float32))
    position = np.asarray(model.geom_pos[geom_id], dtype=np.float32)
    return trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices, dtype=np.float32) @ rotation.T + position,
        faces=mesh.faces,
        process=False,
    )


def build_body_source_mesh(model, body: BodyPlan):
    """Build a single body-local surface from compiled collision geoms."""
    _, _, trimesh = _dependencies()
    return trimesh.util.concatenate(
        [_geom_mesh(model, geom_id) for geom_id in body.geom_ids]
    )


def _filename(body: BodyPlan) -> str:
    if not body.name:
        raise ValueError(f"Body-surface asset body ID {body.body_id} must have a name")
    encoded = quote(body.name, safe="-_.()@")
    windows_reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
    if encoded.casefold() in windows_reserved:
        first = encoded[0].encode("ascii")
        encoded = f"%{first[0]:02X}{encoded[1:]}"
    filename = f"{encoded}.obj"
    if len(filename.encode("utf-8")) > 240:
        raise ValueError(
            f"Body name is too long for a portable surface filename: {body.name!r}"
        )
    return filename


def _body_filenames(bodies: list[BodyPlan]) -> dict[int, str]:
    """Build portable filenames and reject case-insensitive conflicts."""
    filenames: dict[int, str] = {}
    owners: dict[str, str] = {}
    for body in bodies:
        filename = _filename(body)
        key = filename.casefold()
        previous = owners.get(key)
        if previous is not None and previous != body.name:
            raise ValueError(
                "Body names produce conflicting surface filenames: "
                f"{previous!r} and {body.name!r}"
            )
        owners[key] = body.name
        filenames[body.body_id] = filename
    return filenames


def _output_directory(
    model_path: Path,
    output_directory: str | Path | None,
) -> Path:
    """Resolve an explicit output or the model compiler meshdir/surfaces."""
    if output_directory is not None:
        return Path(output_directory).expanduser().resolve()
    return resolve_mujoco_mesh_directory(model_path) / "surfaces"


def _selected_bodies(plan: GeometryPlan, names: list[str] | None) -> list[BodyPlan]:
    required = [body for body in plan.bodies.values() if body.is_multi_geom]
    available = {body.name: body for body in required if body.name}
    if names:
        missing = sorted(set(names) - set(available))
        if missing:
            raise ValueError(
                "Selected body names are not named multi-geom collision bodies: "
                + ", ".join(missing)
            )
        return [available[name] for name in dict.fromkeys(names)]
    unnamed = [body.body_id for body in required if not body.name]
    if unnamed:
        ids = ", ".join(str(body_id) for body_id in unnamed)
        raise ValueError(
            f"Body-surface assets require named bodies; unnamed IDs: {ids}"
        )
    return required


def _surface_set_name(model_path: Path) -> str:
    """Return the portable identity used to own one model's provider records."""
    return model_path.name


def _body_source_meshes(model, bodies: list[BodyPlan]) -> dict[int, Any]:
    """Build the exact body-local geometry consumed by surface preparation."""
    return {body.body_id: build_body_source_mesh(model, body) for body in bodies}


def _source_geometry_sha256(
    bodies: list[BodyPlan],
    source_meshes: dict[int, Any],
) -> str:
    """Fingerprint only the canonical geometry consumed by surface preparation."""
    _, np, _ = _dependencies()
    records = []
    for body in sorted(bodies, key=lambda value: value.name):
        mesh = source_meshes[body.body_id]
        vertices = np.ascontiguousarray(mesh.vertices, dtype="<f4")
        faces = np.ascontiguousarray(mesh.faces, dtype="<i4")
        records.append(
            {
                "body": body.name,
                "faces": hashlib.sha256(faces.tobytes()).hexdigest(),
                "faces_shape": list(faces.shape),
                "vertices": hashlib.sha256(vertices.tobytes()).hexdigest(),
                "vertices_shape": list(vertices.shape),
            }
        )
    return sha256_json(records)


def _surface_sets(
    manifest: dict[str, Any],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    """Validate and return optional model ownership metadata."""
    value = manifest.get("surface_sets", {})
    if not isinstance(value, dict):
        errors.append("manifest surface_sets must be an object")
        return {}

    result: dict[str, dict[str, Any]] = {}
    for set_name, record in value.items():
        if not isinstance(set_name, str) or not set_name:
            errors.append("manifest surface set names must be non-empty strings")
            continue
        if not isinstance(record, dict):
            errors.append(f"manifest surface set must be an object: {set_name!r}")
            continue
        bodies = record.get("bodies")
        source_digest = record.get("source_geometry_sha256")
        if (
            not isinstance(bodies, list)
            or any(not isinstance(body, str) or not body for body in bodies)
            or len(set(bodies)) != len(bodies)
        ):
            errors.append(
                f"manifest surface set bodies must be unique non-empty strings: "
                f"{set_name!r}"
            )
            continue
        if (
            not isinstance(source_digest, str)
            or _SHA256_PATTERN.fullmatch(source_digest) is None
        ):
            errors.append(
                "manifest surface set has an invalid source geometry SHA-256: "
                f"{set_name!r}"
            )
            continue
        result[set_name] = {
            "bodies": list(bodies),
            "source_geometry_sha256": source_digest,
        }
    return result


def _surface_owners(
    surface_sets: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    """Map each body record to the model sets that own it."""
    owners: dict[str, set[str]] = {}
    for set_name, record in surface_sets.items():
        for body_name in record["bodies"]:
            owners.setdefault(body_name, set()).add(set_name)
    return owners


def _artifact_hashes(manifest: dict[str, Any]) -> dict[Any, Any]:
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        return {}
    return {
        path: digest
        for path, digest in hashes.items()
        if path not in _RESERVED_SHA256_KEYS
    }


def _check_provider_manifest(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> list[str]:
    """Validate the shared provider independently of any one source model."""
    errors: list[str] = []
    recipe = manifest.get("recipe")
    if not isinstance(recipe, dict):
        errors.append("manifest recipe must be an object")
    errors.extend(
        verify_manifest_metadata(
            manifest,
            ("schema", "surfaces", "recipe"),
        )
    )
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        return errors

    artifact_hashes = _artifact_hashes(manifest)
    root = manifest_path.parent
    errors.extend(verify_sha256_map(root, artifact_hashes))
    surfaces = manifest.get("surfaces")
    if not isinstance(surfaces, dict):
        return errors + ["manifest surfaces must be an object"]

    filenames: dict[str, str] = {}
    for body_name, relative in surfaces.items():
        if not isinstance(body_name, str) or not body_name:
            errors.append("manifest surface body names must be non-empty strings")
            continue
        if not isinstance(relative, str):
            errors.append(f"body surface path must be a string for {body_name!r}")
            continue
        relative_path = Path(relative)
        if len(relative_path.parts) != 1 or relative_path.suffix.lower() != ".obj":
            errors.append(
                f"body surface path must be a direct .obj filename for "
                f"{body_name!r}: {relative!r}"
            )
            continue
        previous = filenames.get(relative.casefold())
        if previous is not None and previous != body_name:
            errors.append(
                "manifest body surfaces have a case-insensitive filename conflict: "
                f"{previous!r} and {body_name!r}"
            )
        filenames[relative.casefold()] = body_name
        try:
            path = resolve_artifact(root, relative)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if relative not in artifact_hashes:
            errors.append(
                f"body surface is not fingerprinted for {body_name!r}: {relative}"
            )
        if not path.is_file():
            errors.append(f"body surface is missing for {body_name!r}: {path}")

    surface_sets = _surface_sets(manifest, errors)
    for set_name, record in surface_sets.items():
        for body_name in record["bodies"]:
            if body_name not in surfaces:
                errors.append(
                    f"manifest surface set {set_name!r} references a missing body: "
                    f"{body_name!r}"
                )
    return errors


def _write_body_surface_manifest(
    directory: Path,
    *,
    surfaces: dict[str, str],
    surface_sets: dict[str, dict[str, Any]],
    recipe: dict[str, Any],
) -> None:
    """Write one complete shared-provider manifest."""
    surfaces = dict(sorted(surfaces.items()))
    surface_sets = dict(sorted(surface_sets.items()))
    hashes = {
        relative: sha256_file(directory / relative)
        for relative in sorted(set(surfaces.values()))
    }
    for name, value in (
        ("schema", SCHEMA_VERSION),
        ("surfaces", surfaces),
        ("recipe", recipe),
    ):
        hashes[name] = sha256_json(value)
    hashes["sha256"] = sha256_json(hashes)
    manifest = {
        "schema": SCHEMA_VERSION,
        "surfaces": surfaces,
        "surface_sets": surface_sets,
        "recipe": recipe,
        "sha256": hashes,
    }
    write_manifest(directory / MANIFEST_NAME, manifest)


def _copy_provider_surfaces(
    source_directory: Path,
    staging_directory: Path,
    surfaces: dict[str, str],
) -> None:
    """Copy only referenced provider artifacts, dropping unreferenced stale files."""
    for relative in sorted(set(surfaces.values())):
        shutil.copy2(source_directory / relative, staging_directory / relative)


def _ensure_provider_unchanged(
    manifest_path: Path,
    expected_digest: str | None,
) -> None:
    """Prevent concurrent provider updates from silently losing a model set."""
    if expected_digest is None:
        if manifest_path.exists():
            raise RuntimeError(
                f"Body-surface provider changed while it was being prepared: "
                f"{manifest_path}"
            )
        return
    if not manifest_path.is_file() or sha256_file(manifest_path) != expected_digest:
        raise RuntimeError(
            f"Body-surface provider changed while it was being prepared: "
            f"{manifest_path}"
        )


def prepare_body_surfaces(
    model_path: str | Path,
    output_directory: str | Path | None = None,
    *,
    recipe: BodySurfaceRecipe | None = None,
    bodies: list[str] | None = None,
    overwrite: bool = False,
) -> Path:
    """Prepare or update one model set in a shared body-surface provider."""
    model_path = Path(model_path).expanduser().resolve()
    output_directory = _output_directory(model_path, output_directory)
    recipe = recipe or BodySurfaceRecipe()
    recipe_value = asdict(recipe)
    model = load_mujoco_model(model_path)
    plan = analyze_geometry(model)
    if plan.errors:
        raise ValueError(
            "Body-surface geometry is unsupported:\n" + "\n".join(plan.errors)
        )
    selected = _selected_bodies(plan, bodies)
    filenames = _body_filenames(selected)
    selected_names = sorted(body.name for body in selected)
    source_meshes = _body_source_meshes(model, selected)
    source_geometry_sha256 = _source_geometry_sha256(selected, source_meshes)
    set_name = _surface_set_name(model_path)
    manifest_path = output_directory / MANIFEST_NAME

    existing: dict[str, Any] | None = None
    existing_manifest_digest: str | None = None
    if manifest_path.exists():
        existing = load_manifest(manifest_path)
        provider_errors = _check_provider_manifest(manifest_path, existing)
        if provider_errors:
            raise ValueError(
                f"Existing body-surface provider is invalid: {manifest_path}\n"
                + "\n".join(provider_errors)
            )
        existing_manifest_digest = sha256_file(manifest_path)
    elif output_directory.exists() and any(output_directory.iterdir()):
        raise FileExistsError(
            f"Output directory is not an existing body-surface provider: "
            f"{output_directory}"
        )

    existing_surfaces: dict[str, str] = (
        dict(existing["surfaces"]) if existing is not None else {}
    )
    existing_sets = _surface_sets(existing, []) if existing is not None else {}
    current_record = existing_sets.get(set_name)
    if current_record is not None and not overwrite:
        reusable = (
            existing is not None
            and existing.get("recipe") == recipe_value
            and sorted(current_record["bodies"]) == selected_names
            and current_record["source_geometry_sha256"] == source_geometry_sha256
        )
        if reusable:
            existing_errors = check_body_surfaces(
                model_path,
                manifest_path,
                bodies=bodies,
            )
            if not existing_errors:
                return manifest_path
        raise FileExistsError(
            f"Existing body-surface set is not reusable: {set_name!r} in "
            f"{manifest_path}; pass overwrite=True to update it"
        )

    ensure_safe_output(model_path, output_directory)
    surfaces = existing_surfaces
    surface_sets = existing_sets
    owners = _surface_owners(surface_sets)

    if overwrite and current_record is not None:
        surface_sets.pop(set_name)
        for body_name in current_record["bodies"]:
            body_owners = owners.get(body_name, set())
            body_owners.discard(set_name)
            if not body_owners:
                surfaces.pop(body_name, None)
                owners.pop(body_name, None)
            else:
                owners[body_name] = body_owners
    elif overwrite and current_record is None:
        # Adopt and replace matching records from manifests created before
        # surface-set ownership metadata existed.
        for body_name in selected_names:
            if body_name in surfaces and not owners.get(body_name):
                surfaces.pop(body_name)

    if existing is not None and existing.get("recipe") != recipe_value:
        if not overwrite:
            raise FileExistsError(
                f"Existing body-surface provider uses a different recipe: "
                f"{manifest_path}; pass overwrite=True to update this model set"
            )
        if surfaces:
            raise ValueError(
                "A shared body-surface provider cannot mix preparation recipes; "
                f"other model surfaces remain in {manifest_path}"
            )

    generation_targets: list[BodyPlan] = []
    for body in selected:
        body_name = body.name
        foreign_owners = owners.get(body_name, set())
        if body_name not in surfaces or foreign_owners:
            generation_targets.append(body)

    with staged_directory(output_directory, overwrite=True) as staging_directory:
        if existing is not None:
            _copy_provider_surfaces(
                output_directory,
                staging_directory,
                surfaces,
            )
        with tempfile.TemporaryDirectory(
            prefix=".work-",
            dir=staging_directory,
        ) as work_value:
            work_directory = Path(work_value)
            for body in generation_targets:
                source_mesh = source_meshes[body.body_id]
                filename = filenames[body.body_id]
                for existing_body, existing_filename in surfaces.items():
                    if (
                        existing_body != body.name
                        and existing_filename.casefold() == filename.casefold()
                    ):
                        raise ValueError(
                            "Body names produce conflicting surface filenames in "
                            f"the shared provider: {existing_body!r} and "
                            f"{body.name!r}"
                        )
                source_path = work_directory / f"source-{body.body_id}.obj"
                generated_path = work_directory / f"generated-{body.body_id}.ply"
                source_mesh.export(source_path)
                prepare_surface(
                    source_path,
                    generated_path,
                    work_directory / f"body-{body.body_id}",
                    recipe,
                )
                generated_mesh = load_mesh(generated_path)
                output_path = staging_directory / filename
                generated_mesh.export(output_path)
                published_mesh = load_mesh(output_path)
                errors = validate_mesh(published_mesh, watertight=True)
                if errors:
                    raise ValueError(
                        f"Generated body surface for {body.name!r} is invalid: "
                        + "; ".join(errors)
                    )
                generated_digest = sha256_file(output_path)
                existing_relative = surfaces.get(body.name)
                if existing_relative is not None:
                    assert existing is not None
                    expected_digest = _artifact_hashes(existing).get(existing_relative)
                    if generated_digest != expected_digest:
                        foreign_sets = sorted(owners.get(body.name, set()))
                        raise ValueError(
                            f"Body-surface conflict for {body.name!r}: model set "
                            f"{set_name!r} differs from existing set(s) "
                            f"{foreign_sets}"
                        )
                    if existing_relative != filename:
                        output_path.unlink()
                else:
                    surfaces[body.name] = filename

        surface_sets[set_name] = {
            "bodies": selected_names,
            "source_geometry_sha256": source_geometry_sha256,
        }
        _write_body_surface_manifest(
            staging_directory,
            surfaces=surfaces,
            surface_sets=surface_sets,
            recipe=recipe_value,
        )
        _ensure_provider_unchanged(manifest_path, existing_manifest_digest)
    return manifest_path


def check_body_surfaces(
    model_path: str | Path,
    manifest_path_or_directory: str | Path | None = None,
    *,
    bodies: list[str] | None = None,
) -> list[str]:
    """Check a body-surface manifest against a compiled MuJoCo model."""
    model_path = Path(model_path).expanduser().resolve()
    if manifest_path_or_directory is None:
        manifest_path = _output_directory(model_path, None) / MANIFEST_NAME
    else:
        manifest_path = Path(manifest_path_or_directory).expanduser().resolve()
    if manifest_path_or_directory is not None and manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    errors = _check_provider_manifest(manifest_path, manifest)
    model = load_mujoco_model(model_path)
    plan = analyze_geometry(model)
    errors.extend(plan.errors)
    try:
        selected = _selected_bodies(plan, bodies)
    except ValueError as exc:
        return errors + [str(exc)]
    artifact_hashes = _artifact_hashes(manifest)
    root = manifest_path.parent
    surfaces = manifest.get("surfaces")
    if not isinstance(surfaces, dict):
        return errors

    for body in selected:
        relative = surfaces.get(body.name)
        if not isinstance(relative, str):
            errors.append(f"body is missing from surfaces: {body.name!r}")
            continue
        relative_path = Path(relative)
        if len(relative_path.parts) != 1 or relative_path.suffix.lower() != ".obj":
            errors.append(
                f"body surface path must be a direct .obj filename for {body.name!r}: "
                f"{relative!r}"
            )
            continue
        try:
            path = resolve_artifact(root, relative)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if relative not in artifact_hashes:
            errors.append(
                f"body surface is not fingerprinted for {body.name!r}: {relative}"
            )
        if not path.is_file():
            errors.append(f"body surface is missing for {body.name!r}: {path}")
            continue
        _validate_body_surface(body.name, path, errors)

    surface_sets = _surface_sets(manifest, [])
    record = surface_sets.get(_surface_set_name(model_path))
    if record is not None:
        record_names = set(record["bodies"])
        selected_names = {body.name for body in selected}
        if bodies is None and record_names != selected_names:
            errors.append(
                "surface set body names do not match the model: "
                f"{_surface_set_name(model_path)!r}"
            )
        elif bodies is not None and not selected_names <= record_names:
            errors.append(
                "selected bodies are not contained in the model surface set: "
                f"{_surface_set_name(model_path)!r}"
            )
        available = {
            body.name: body
            for body in plan.bodies.values()
            if body.is_multi_geom and body.name
        }
        missing_record_bodies = sorted(record_names - set(available))
        if missing_record_bodies:
            errors.append(
                "surface set contains bodies that are no longer multi-geom "
                f"collision bodies: {', '.join(missing_record_bodies)}"
            )
        else:
            record_bodies = [available[name] for name in sorted(record_names)]
            source_meshes = _body_source_meshes(model, record_bodies)
            actual = _source_geometry_sha256(record_bodies, source_meshes)
            if actual != record["source_geometry_sha256"]:
                errors.append(
                    "surface set source geometry fingerprint does not match: "
                    f"{_surface_set_name(model_path)!r}"
                )
    return errors


def _validate_body_surface(
    body_name: str,
    path: Path,
    errors: list[str],
) -> None:
    """Load one published body mesh and append structural errors."""
    try:
        asset_mesh = load_mesh(path)
        mesh_errors = validate_mesh(asset_mesh, watertight=True)
    except ValueError as exc:
        errors.append(f"could not load body mesh for {body_name!r}: {exc}")
        return
    errors.extend(f"{body_name!r}: {error}" for error in mesh_errors)
