"""MuJoCo XML and MJB input adapter."""

from __future__ import annotations

from pathlib import Path


def _mujoco():
    try:
        import mujoco
    except ImportError as exc:
        raise RuntimeError("MuJoCo input requires sim-asset-tools[mujoco]") from exc
    return mujoco


def load_mujoco_model(path: str | Path):
    """Compile a MuJoCo XML model or load an MJB binary."""
    mujoco = _mujoco()
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"MuJoCo model does not exist: {path}")
    if path.suffix.lower() == ".mjb":
        return mujoco.MjModel.from_binary_path(path.as_posix())
    if path.suffix.lower() not in (".xml", ".mjcf"):
        raise ValueError(f"Expected MuJoCo XML/MJCF or MJB model: {path}")
    return mujoco.MjSpec.from_file(path.as_posix()).compile()
