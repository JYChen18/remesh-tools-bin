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

"""Prepare backend-neutral, body-local surface assets from compiled models.

The ``body-surfaces/v1`` contract keys records by exact compiled body name and
stores meshes under hash-derived filenames. Body names containing path
separators therefore remain data rather than becoming filesystem paths.
"""

from __future__ import annotations

import hashlib
import shutil
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
    write_manifest,
)
from ..formats.mujoco_model import load_mujoco_model
from ..mesh.io import load_mesh
from ..mesh.validation import validate_mesh
from .._publish import (
    ensure_safe_output,
    staged_directory,
)
from ._surface import SurfaceRecipe, prepare_surface

CONTRACT_VERSION = "body-surfaces/v1"


@dataclass(frozen=True)
class BodyPlan:
    """One bounded collidable MuJoCo body."""

    body_id: int
    name: str
    geom_ids: tuple[int, ...]


@dataclass(frozen=True)
class GeometryPlan:
    """Bounded, procedural, and unsupported collision bodies."""

    bodies: dict[int, BodyPlan]
    procedural: dict[int, BodyPlan]
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
    procedural: dict[int, BodyPlan] = {}
    for body_id, geom_ids in grouped.items():
        procedural_ids = [
            geom_id
            for geom_id in geom_ids
            if int(model.geom_type[geom_id]) in procedural_types
        ]
        name = _body_name(model, body_id)
        body = BodyPlan(body_id, name, tuple(geom_ids))
        if procedural_ids:
            if len(geom_ids) != 1:
                errors.append(
                    f"body {name or f'body_{body_id}'!r} mixes a procedural geom with other collisions"
                )
            else:
                procedural[body_id] = body
        else:
            bodies[body_id] = body
    return GeometryPlan(bodies, procedural, tuple(errors))


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


def mesh_fingerprint(mesh) -> str:
    """Hash canonical float32 vertices and int32 faces."""
    _, np, _ = _dependencies()
    digest = hashlib.sha256(CONTRACT_VERSION.encode("ascii"))
    for label, values in (
        (b"vertices", np.ascontiguousarray(mesh.vertices, dtype="<f4")),
        (b"faces", np.ascontiguousarray(mesh.faces, dtype="<i4")),
    ):
        digest.update(label)
        digest.update(np.asarray(values.shape, dtype="<i8").tobytes())
        digest.update(values.tobytes())
    return digest.hexdigest()


def _filename(body: BodyPlan) -> str:
    if not body.name:
        raise ValueError(f"Body-surface asset body ID {body.body_id} must have a name")
    token = hashlib.sha256(body.name.encode("utf-8")).hexdigest()[:12]
    return f"body-{body.body_id:04d}-{token}.obj"


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
    output_directory: str | Path,
    *,
    recipe: BodySurfaceRecipe | None = None,
    bodies: list[str] | None = None,
    overwrite: bool = False,
) -> Path:
    """Prepare one body-local surface per bounded collision body."""
    model_path = Path(model_path).expanduser().resolve()
    output_directory = Path(output_directory).expanduser().resolve()
    recipe = recipe or BodySurfaceRecipe()
    model = load_mujoco_model(model_path)
    plan = analyze_geometry(model)
    if plan.errors:
        raise ValueError(
            "Body-surface geometry is unsupported:\n" + "\n".join(plan.errors)
        )
    selected = _selected_bodies(plan, bodies)
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
        meshes_directory = staging_directory / "meshes"
        meshes_directory.mkdir()
        work_directory = staging_directory / ".work"
        work_directory.mkdir()
        body_records: dict[str, dict[str, object]] = {}
        for body in selected:
            source_mesh = build_body_source_mesh(model, body)
            filename = _filename(body)
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
            output_path = meshes_directory / filename
            generated_mesh.export(output_path)
            published_mesh = load_mesh(output_path)
            errors = validate_mesh(published_mesh, watertight=True)
            if errors:
                raise ValueError(
                    f"Generated body surface for {body.name!r} is invalid: {'; '.join(errors)}"
                )
            body_records[body.name] = {
                "body_id": body.body_id,
                "mesh": {
                    "path": relative_artifact_path(staging_directory, output_path),
                    "sha256": sha256_file(output_path),
                },
                "source_mesh_sha256": mesh_fingerprint(source_mesh),
                "asset_mesh_sha256": mesh_fingerprint(published_mesh),
            }
        manifest = {
            "schema": SCHEMA_VERSION,
            "kind": "body-surfaces",
            "contract": CONTRACT_VERSION,
            "tool": {"name": "sim-asset-tools", "version": __version__},
            "source": {
                "format": "mjb" if model_path.suffix.lower() == ".mjb" else "mjcf",
                "name": model_path.name,
                "sha256": sha256_file(model_path),
            },
            "recipe": asdict(recipe),
            "bodies": body_records,
            "procedural_bodies": [
                body.name or f"body_{body.body_id}" for body in plan.procedural.values()
            ],
        }
        shutil.rmtree(work_directory)
        write_manifest(staging_directory / MANIFEST_NAME, manifest)
    return manifest_path


def check_body_surfaces(
    model_path: str | Path,
    manifest_path_or_directory: str | Path,
    *,
    bodies: list[str] | None = None,
) -> list[str]:
    """Check a body-surface manifest against a compiled MuJoCo model."""
    manifest_path = Path(manifest_path_or_directory)
    if manifest_path.is_dir():
        manifest_path = manifest_path / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    errors: list[str] = []
    if manifest.get("kind") != "body-surfaces":
        return [f"manifest kind is not body-surfaces: {manifest.get('kind')!r}"]
    if manifest.get("contract") != CONTRACT_VERSION:
        errors.append(
            f"unsupported body-surface contract: {manifest.get('contract')!r}"
        )
    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("sha256") != sha256_file(model_path):
        errors.append("source model hash does not match")
    model = load_mujoco_model(model_path)
    plan = analyze_geometry(model)
    errors.extend(plan.errors)
    try:
        selected = _selected_bodies(plan, bodies)
    except ValueError as exc:
        return errors + [str(exc)]
    records = manifest.get("bodies")
    if not isinstance(records, dict):
        return errors + ["manifest bodies must be an object"]
    root = manifest_path.parent
    for body in selected:
        record = records.get(body.name)
        if not isinstance(record, dict):
            errors.append(f"body is missing from manifest: {body.name!r}")
            continue
        mesh_record = record.get("mesh")
        if not isinstance(mesh_record, dict) or not isinstance(
            mesh_record.get("path"), str
        ):
            errors.append(f"body mesh record is invalid: {body.name!r}")
            continue
        try:
            path = resolve_artifact(root, mesh_record["path"])
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"body mesh is missing for {body.name!r}: {path}")
            continue
        if mesh_record.get("sha256") != sha256_file(path):
            errors.append(f"body mesh file hash does not match for {body.name!r}")
            continue
        source_mesh = build_body_source_mesh(model, body)
        if record.get("source_mesh_sha256") != mesh_fingerprint(source_mesh):
            errors.append(f"compiled collision surface changed for {body.name!r}")
        try:
            asset_mesh = load_mesh(path)
            mesh_errors = validate_mesh(asset_mesh, watertight=True)
        except ValueError as exc:
            errors.append(f"could not load body mesh for {body.name!r}: {exc}")
            continue
        errors.extend(f"{body.name!r}: {error}" for error in mesh_errors)
        if record.get("asset_mesh_sha256") != mesh_fingerprint(asset_mesh):
            errors.append(f"body asset surface hash does not match for {body.name!r}")
    return errors
