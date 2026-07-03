from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


_TOOLS = {
    "ACVD",
    "ACVDP",
    "ACVDQ",
    "ACVDQP",
    "AnisotropicRemeshing",
    "AnisotropicRemeshingQ",
    "AnisotropicRemeshingQP",
    "VolumeAnalysis",
}


def native_bin_dir() -> Path:
    return Path(__file__).resolve().parent / "_native" / "bin"


def _native_lib_dir() -> Path:
    return Path(__file__).resolve().parent / "_native" / "lib"


def _vtkmodules_dir() -> Path:
    try:
        import vtkmodules
    except ImportError as exc:
        raise RuntimeError("acvd-bin requires vtk==9.4.0 to be installed in this Python environment") from exc

    if vtkmodules.__file__ is None:
        raise RuntimeError("Could not locate the installed vtkmodules package")
    return Path(vtkmodules.__file__).resolve().parent


def available_tools() -> tuple[str, ...]:
    return tuple(sorted(_TOOLS))


def _tool_path(tool: str) -> Path:
    if tool not in _TOOLS:
        raise ValueError(f"Unknown ACVD tool {tool!r}. Available tools: {', '.join(available_tools())}")

    exe_name = f"{tool}.exe" if os.name == "nt" else tool
    path = native_bin_dir() / exe_name
    if not path.exists():
        raise RuntimeError(f"Native ACVD executable is missing: {path}")
    return path


def _prepend_path(env: dict[str, str], key: str, paths: Iterable[Path]) -> None:
    existing = env.get(key)
    prefix = os.pathsep.join(str(path) for path in paths)
    env[key] = prefix if not existing else f"{prefix}{os.pathsep}{existing}"


def _native_env() -> dict[str, str]:
    env = os.environ.copy()
    lib_paths = [_native_lib_dir(), _vtkmodules_dir()]

    if os.name == "nt":
        _prepend_path(env, "PATH", lib_paths)
    elif sys.platform == "darwin":
        _prepend_path(env, "DYLD_LIBRARY_PATH", lib_paths)
    else:
        _prepend_path(env, "LD_LIBRARY_PATH", lib_paths)

    return env


def run(tool: str, args: Iterable[str] | None = None, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    argv = [str(_tool_path(tool)), *(args or ())]
    return subprocess.run(argv, env=_native_env(), check=check, text=True)


def _exec(tool: str) -> int:
    path = _tool_path(tool)
    os.execvpe(str(path), [str(path), *sys.argv[1:]], _native_env())
    return 127


def dispatch() -> int:
    if len(sys.argv) < 2:
        print("Available ACVD tools:", file=sys.stderr)
        for tool in available_tools():
            print(f"  {tool}", file=sys.stderr)
        return 2

    tool = sys.argv[1]
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    return _exec(tool)


def acvd() -> int:
    return _exec("ACVD")


def acvdp() -> int:
    return _exec("ACVDP")


def acvdq() -> int:
    return _exec("ACVDQ")


def acvdqp() -> int:
    return _exec("ACVDQP")


def anisotropic_remeshing() -> int:
    return _exec("AnisotropicRemeshing")


def anisotropic_remeshing_q() -> int:
    return _exec("AnisotropicRemeshingQ")


def anisotropic_remeshing_qp() -> int:
    return _exec("AnisotropicRemeshingQP")


def volume_analysis() -> int:
    return _exec("VolumeAnalysis")
