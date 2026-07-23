"""Lazy mesh loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SUPPORTED_MESH_SUFFIXES = frozenset({".glb", ".obj", ".ply", ".stl"})


def _trimesh():
    try:
        import trimesh
    except ImportError as exc:
        raise RuntimeError(
            "Mesh loading requires numpy and trimesh from sim-asset-tools"
        ) from exc
    return trimesh


def as_single_mesh(loaded: Any):
    """Convert a trimesh mesh or scene into one triangle mesh."""
    trimesh = _trimesh()
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    if isinstance(loaded, trimesh.Scene):
        meshes = [
            geometry
            for geometry in loaded.geometry.values()
            if isinstance(geometry, trimesh.Trimesh)
        ]
        if not meshes:
            raise ValueError("Scene does not contain any triangle meshes")
        return trimesh.util.concatenate(meshes)
    raise TypeError(f"Unsupported mesh type: {type(loaded)!r}")


def load_mesh(path: str | Path, *, process: bool = False):
    """Load one non-empty mesh from a file."""
    trimesh = _trimesh()
    path = Path(path)
    try:
        mesh = as_single_mesh(trimesh.load(path, force="mesh", process=process))
    except Exception as exc:
        raise ValueError(f"Could not load mesh {path}: {exc}") from exc
    if len(mesh.vertices) == 0 or len(mesh.faces) == 0:
        raise ValueError(f"Mesh has no vertices or faces: {path}")
    return mesh
