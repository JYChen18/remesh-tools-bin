"""CoACD raw-mesh processing."""

from __future__ import annotations

from typing import Any


def _part_to_mesh(part: Any):
    import trimesh

    if isinstance(part, trimesh.Trimesh):
        return part
    if hasattr(part, "vertices") and hasattr(part, "faces"):
        return trimesh.Trimesh(vertices=part.vertices, faces=part.faces, process=False)
    if isinstance(part, (tuple, list)) and len(part) == 2:
        return trimesh.Trimesh(vertices=part[0], faces=part[1], process=False)
    raise TypeError(f"Unsupported CoACD part type: {type(part)!r}")


def decompose_mesh(
    mesh,
    *,
    threshold: float = 0.05,
    max_convex_hull: int = -1,
    preprocess_mode: str = "auto",
    preprocess_resolution: int = 50,
    real_metric: bool = False,
    seed: int | None = 0,
) -> list:
    """Decompose a triangle mesh into approximately convex parts."""
    try:
        import coacd
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Convex decomposition requires sim-asset-tools[coacd]"
        ) from exc
    coacd_mesh = coacd.Mesh(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int32),
    )
    kwargs: dict[str, object] = {
        "threshold": threshold,
        "max_convex_hull": max_convex_hull,
        "preprocess_mode": preprocess_mode,
        "preprocess_resolution": preprocess_resolution,
        "real_metric": real_metric,
    }
    if seed is not None:
        kwargs["seed"] = seed
    return [_part_to_mesh(part) for part in coacd.run_coacd(coacd_mesh, **kwargs)]
