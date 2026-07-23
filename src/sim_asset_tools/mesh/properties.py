"""Geometry properties measured from in-memory triangle meshes."""

from __future__ import annotations


def oriented_bounding_box(mesh) -> dict[str, object]:
    """Return a deterministic oriented bounding box for a mesh."""
    import numpy as np
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkFiltersGeneral import vtkOBBTree

    points = vtkPoints()
    vertices = np.asarray(mesh.vertices, dtype=float)
    points.SetNumberOfPoints(len(vertices))
    for index, vertex in enumerate(vertices):
        points.SetPoint(index, *vertex)

    corner = [0.0, 0.0, 0.0]
    maximum = [0.0, 0.0, 0.0]
    middle = [0.0, 0.0, 0.0]
    minimum = [0.0, 0.0, 0.0]
    sizes = [0.0, 0.0, 0.0]
    vtkOBBTree.ComputeOBB(points, corner, maximum, middle, minimum, sizes)

    vectors = np.asarray([maximum, middle, minimum], dtype=float)
    lengths = np.linalg.norm(vectors, axis=1)
    if not np.isfinite(lengths).all() or np.any(lengths <= 0.0):
        raise ValueError("Could not compute a nondegenerate oriented bounding box")
    center = np.asarray(corner, dtype=float) + vectors.sum(axis=0) / 2.0
    axes = vectors / lengths[:, None]
    for axis in axes:
        dominant = int(np.argmax(np.abs(axis)))
        if axis[dominant] < 0.0:
            axis *= -1.0
    if np.linalg.det(axes) < 0.0:
        axes[-1] *= -1.0
    return {
        "center": center.tolist(),
        "axes": axes.tolist(),
        "extents": lengths.tolist(),
    }


def collision_properties(mesh) -> dict[str, object]:
    """Return density-independent aggregate collision properties."""
    import numpy as np

    volume = float(mesh.volume)
    if not np.isfinite(volume) or volume <= 0.0:
        raise ValueError("Aggregate collision volume must be positive and finite")
    inertia = np.asarray(mesh.moment_inertia, dtype=float) / volume
    return {
        "volume": volume,
        "center_of_mass": np.asarray(mesh.center_mass, dtype=float).tolist(),
        "inertia_per_unit_mass": inertia.tolist(),
    }
