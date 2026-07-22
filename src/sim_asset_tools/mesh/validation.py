"""Mesh validation shared by raw-mesh operations and prepared assets."""

from __future__ import annotations


def _component_volumes(vertices, faces, np) -> list[float]:
    """Compute signed volumes without Trimesh's optional graph backends."""
    parents = list(range(len(vertices)))

    def find(vertex: int) -> int:
        while parents[vertex] != vertex:
            parents[vertex] = parents[parents[vertex]]
            vertex = parents[vertex]
        return vertex

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for first, second, third in faces:
        union(int(first), int(second))
        union(int(first), int(third))

    signed_face_volumes = (
        np.einsum(
            "ij,ij->i",
            vertices[faces[:, 0]],
            np.cross(vertices[faces[:, 1]], vertices[faces[:, 2]]),
        )
        / 6.0
    )
    volumes: dict[int, float] = {}
    for face, volume in zip(faces, signed_face_volumes, strict=True):
        root = find(int(face[0]))
        volumes[root] = volumes.get(root, 0.0) + float(volume)
    return list(volumes.values())


def validate_mesh(mesh, *, watertight: bool = False) -> list[str]:
    """Return structural and optional closed-surface validation errors."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Mesh validation requires numpy from sim-asset-tools"
        ) from exc

    errors: list[str] = []
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    if vertices.ndim != 2 or vertices.shape[1:] != (3,):
        errors.append("mesh vertices must have shape (n, 3)")
    if faces.ndim != 2 or faces.shape[1:] != (3,):
        errors.append("mesh faces must have shape (n, 3)")
    if vertices.size == 0 or faces.size == 0:
        errors.append("mesh must contain at least one triangle")
    if vertices.size and not np.isfinite(vertices).all():
        errors.append("mesh vertices must be finite")
    if faces.size and (faces.min() < 0 or faces.max() >= len(vertices)):
        errors.append("mesh faces reference invalid vertices")
    if (
        faces.size
        and len(getattr(mesh, "area_faces", ()))
        and bool(np.any(mesh.area_faces <= 1.0e-20))
    ):
        errors.append("mesh must not contain degenerate faces")
    if watertight and not errors:
        if not mesh.is_watertight:
            errors.append("mesh must be watertight")
        elif not mesh.is_winding_consistent:
            errors.append("mesh winding must be consistent")
        elif any(volume <= 0.0 for volume in _component_volumes(vertices, faces, np)):
            errors.append("mesh normals must face outward")
    return errors
