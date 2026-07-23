"""Raw-mesh normalization."""

from __future__ import annotations


def normalize_mesh(mesh):
    """Center a mesh and scale its axis-aligned bounding-box half-diagonal to one.

    For source center ``c`` and full extents ``e``, transformed vertices are
    ``2 * (vertices - c) / norm(e)``.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Mesh normalization requires numpy") from exc

    result = mesh.copy()
    vertices = np.asarray(result.vertices, dtype=np.float64)
    bounds_min = vertices.min(axis=0)
    bounds_max = vertices.max(axis=0)
    center = (bounds_min + bounds_max) / 2.0
    scale = float(np.linalg.norm(bounds_max - bounds_min) / 2.0)
    if scale <= 0.0:
        raise ValueError("Cannot normalize a degenerate mesh with zero bounding box")
    result.vertices = (vertices - center[None, :]) / scale
    return result, center.tolist(), scale
