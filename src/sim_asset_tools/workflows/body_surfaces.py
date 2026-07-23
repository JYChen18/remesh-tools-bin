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
relative to the manifest.
"""

from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
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


@dataclass(frozen=True)
class BodyPlan:
    """One bounded collidable MuJoCo body."""

    body_id: int
    name: str
    geom_ids: tuple[int, ...]


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
                errors.append(
                    f"body {name or f'body_{body_id}'!r} mixes a procedural geom with other collisions"
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
    available = {body.name: body for body in plan.bodies.values() if body.name}
    if names:
        missing = sorted(set(names) - set(available))
        if missing:
            raise ValueError(
                f"Selected body names do not have bounded collision geoms: {', '.join(missing)}"
            )
        return [available[name] for name in dict.fromkeys(names)]
    selected = list(plan.bodies.values())
    unnamed = [body.body_id for body in selected if not body.name]
    if unnamed:
        ids = ", ".join(str(body_id) for body_id in unnamed)
        raise ValueError(
            f"Body-surface assets require named bodies; unnamed IDs: {ids}"
        )
    return selected


def prepare_body_surfaces(
    model_path: str | Path,
    output_directory: str | Path | None = None,
    *,
    recipe: BodySurfaceRecipe | None = None,
    bodies: list[str] | None = None,
    overwrite: bool = False,
) -> Path:
    """Prepare one body-local surface per bounded collision body."""
    model_path = Path(model_path).expanduser().resolve()
    output_directory = _output_directory(model_path, output_directory)
    recipe = recipe or BodySurfaceRecipe()
    model = load_mujoco_model(model_path)
    plan = analyze_geometry(model)
    if plan.errors:
        raise ValueError(
            "Body-surface geometry is unsupported:\n" + "\n".join(plan.errors)
        )
    selected = _selected_bodies(plan, bodies)
    filenames = _body_filenames(selected)
    manifest_path = output_directory / MANIFEST_NAME
    if manifest_path.exists() and not overwrite:
        existing_errors = check_body_surfaces(model_path, manifest_path, bodies=bodies)
        existing = load_manifest(manifest_path)
        if not existing_errors and existing.get("recipe") == asdict(recipe):
            return manifest_path
        raise FileExistsError(
            f"Existing body-surface asset is not reusable: {manifest_path}; "
            "pass overwrite=True to replace it"
        )
    ensure_safe_output(model_path, output_directory)
    with staged_directory(output_directory, overwrite=overwrite) as staging_directory:
        surfaces: dict[str, str] = {}
        hashes: dict[str, str] = {}
        with tempfile.TemporaryDirectory(
            prefix=".work-",
            dir=staging_directory,
        ) as work_value:
            work_directory = Path(work_value)
            for body in selected:
                source_mesh = build_body_source_mesh(model, body)
                filename = filenames[body.body_id]
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
                surfaces[body.name] = filename
                hashes[filename] = sha256_file(output_path)

        recipe_value = asdict(recipe)
        for name, value in (
            ("schema", SCHEMA_VERSION),
            ("surfaces", surfaces),
            ("recipe", recipe_value),
        ):
            hashes[name] = sha256_json(value)
        hashes["sha256"] = sha256_json(hashes)
        manifest = {
            "schema": SCHEMA_VERSION,
            "surfaces": surfaces,
            "recipe": recipe_value,
            "sha256": hashes,
        }
        write_manifest(staging_directory / MANIFEST_NAME, manifest)
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
    model = load_mujoco_model(model_path)
    plan = analyze_geometry(model)
    errors = list(plan.errors)
    try:
        selected = _selected_bodies(plan, bodies)
    except ValueError as exc:
        return errors + [str(exc)]

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
    artifact_hashes = {
        path: digest
        for path, digest in hashes.items()
        if path not in _RESERVED_SHA256_KEYS
    }
    root = manifest_path.parent
    errors.extend(verify_sha256_map(root, artifact_hashes))
    surfaces = manifest.get("surfaces")
    if not isinstance(surfaces, dict):
        return errors + ["manifest surfaces must be an object"]

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
