"""MuJoCo XML and MJB input adapter."""

from __future__ import annotations

from pathlib import Path


def _model_path(path: str | Path) -> Path:
    """Resolve and validate a supported MuJoCo model path."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"MuJoCo model does not exist: {path}")
    if path.suffix.lower() not in (".xml", ".mjcf", ".mjb"):
        raise ValueError(f"Expected MuJoCo XML/MJCF or MJB model: {path}")
    return path


def load_mujoco_model(path: str | Path):
    """Compile a MuJoCo XML model or load an MJB binary."""
    import mujoco

    path = _model_path(path)
    if path.suffix.lower() == ".mjb":
        return mujoco.MjModel.from_binary_path(path.as_posix())
    return mujoco.MjSpec.from_file(path.as_posix()).compile()


def resolve_mujoco_mesh_directory(path: str | Path) -> Path:
    """Resolve the XML compiler mesh directory, or the model directory for MJB."""
    import mujoco

    path = _model_path(path)
    if path.suffix.lower() == ".mjb":
        return path.parent

    mesh_directory = Path(mujoco.MjSpec.from_file(path.as_posix()).meshdir or ".")
    if not mesh_directory.is_absolute():
        mesh_directory = path.parent / mesh_directory
    return mesh_directory.expanduser().resolve()
