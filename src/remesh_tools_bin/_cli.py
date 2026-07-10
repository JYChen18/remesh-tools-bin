from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence


_NATIVE_TOOLS = {
    "ACVD",
    "ACVDP",
    "ACVDQ",
    "ACVDQP",
    "AnisotropicRemeshing",
    "AnisotropicRemeshingQ",
    "AnisotropicRemeshingQP",
    "OpenVDBSdfRemesh",
    "VolumeAnalysis",
}

_METHOD_TO_NATIVE = {
    "acvd": "ACVD",
    "acvd-parallel": "ACVDP",
    "acvd-quadric": "ACVDQ",
    "acvd-quadric-parallel": "ACVDQP",
    "acvd-anisotropic": "AnisotropicRemeshing",
    "acvd-anisotropic-quadric": "AnisotropicRemeshingQ",
    "acvd-anisotropic-quadric-parallel": "AnisotropicRemeshingQP",
    "openvdb-sdf": "OpenVDBSdfRemesh",
}

_ANISOTROPIC_OUTPUTS = {
    "AnisotropicRemeshing": "output.ply",
    "AnisotropicRemeshingQ": "Remeshing.ply",
    "AnisotropicRemeshingQP": "Remeshing.ply",
}


def native_bin_dir() -> Path:
    return Path(__file__).resolve().parent / "_native" / "bin"


def _native_lib_dir() -> Path:
    return Path(__file__).resolve().parent / "_native" / "lib"


def _vendored_library_dirs() -> tuple[Path, ...]:
    package_dir = Path(__file__).resolve().parent
    candidate = package_dir.parent / "remesh_tools_bin.libs"
    return (candidate,) if candidate.is_dir() else ()


def _vtkmodules_dir() -> Path:
    try:
        import vtkmodules
    except ImportError as exc:
        raise RuntimeError("remesh-tools-bin requires vtk==9.5.2 to be installed in this Python environment") from exc

    if vtkmodules.__file__ is None:
        raise RuntimeError("Could not locate the installed vtkmodules package")
    return Path(vtkmodules.__file__).resolve().parent


def _vtk_library_dirs() -> tuple[Path, ...]:
    vtkmodules_dir = _vtkmodules_dir()
    candidates = (
        vtkmodules_dir / ".dylibs",
        vtkmodules_dir / ".libs",
        vtkmodules_dir,
    )
    return tuple(path for path in candidates if path.exists())


def available_methods() -> tuple[str, ...]:
    return tuple(sorted(_METHOD_TO_NATIVE))


def _tool_path(tool: str) -> Path:
    if tool not in _NATIVE_TOOLS:
        raise ValueError(f"Unknown native tool {tool!r}")

    exe_name = f"{tool}.exe" if os.name == "nt" else tool
    path = native_bin_dir() / exe_name
    if not path.exists():
        raise RuntimeError(f"Native executable is missing: {path}")
    return path


def _prepend_path(env: dict[str, str], key: str, paths: Iterable[Path]) -> None:
    existing = env.get(key)
    prefix = os.pathsep.join(str(path) for path in paths)
    env[key] = prefix if not existing else f"{prefix}{os.pathsep}{existing}"


def _native_env() -> dict[str, str]:
    env = os.environ.copy()
    lib_paths = [
        native_bin_dir(),
        _native_lib_dir(),
        *_vendored_library_dirs(),
        *_vtk_library_dirs(),
    ]

    if os.name == "nt":
        _prepend_path(env, "PATH", lib_paths)
    elif sys.platform == "darwin":
        _prepend_path(env, "DYLD_LIBRARY_PATH", lib_paths)
    else:
        _prepend_path(env, "LD_LIBRARY_PATH", lib_paths)

    return env


def run_native(
    tool: str,
    args: Iterable[str] | None = None,
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    argv = [str(_tool_path(tool)), *(args or ())]
    return subprocess.run(argv, env=_native_env(), check=check, text=True)


def _run_native(tool: str, args: Sequence[str]) -> int:
    return run_native(tool, args).returncode


def _output_parent_for_native(output: Path) -> str:
    parent = output.parent if str(output.parent) else Path(".")
    parent_text = str(parent)
    if parent_text == "":
        parent_text = "."
    if not parent_text.endswith((os.sep, "/")):
        parent_text += os.sep
    return parent_text


def _format_number(value: float | int) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _strip_separator(args: Sequence[str]) -> list[str]:
    args = list(args)
    if args and args[0] == "--":
        return args[1:]
    return args


def _append_option(argv: list[str], flag: str, value: object | None) -> None:
    if value is not None:
        argv.extend([flag, str(value)])


def _acvd_args(args: argparse.Namespace, extra: Sequence[str]) -> list[str]:
    output = Path(args.output)
    argv = [
        args.input,
        str(args.vertices),
        _format_number(args.gradation),
        "-o",
        _output_parent_for_native(output),
        "-of",
        output.name,
    ]
    _append_option(argv, "-s", args.subsample)
    _append_option(argv, "-l", args.split_long_edges)
    _append_option(argv, "-d", args.display)
    _append_option(argv, "-b", args.boundary_fixing)
    _append_option(argv, "-m", args.force_manifold)
    _append_option(argv, "-q", args.quadric_level)
    _append_option(argv, "-np", args.threads)
    argv.extend(_strip_separator(extra))
    return argv


def _anisotropic_args(args: argparse.Namespace, extra: Sequence[str]) -> list[str]:
    output = Path(args.output)
    if output.suffix and output.suffix.lower() != ".ply":
        raise ValueError("ACVD anisotropic methods write PLY; use a .ply output path")

    argv = [
        args.input,
        str(args.vertices),
        _format_number(args.gradation),
        "-o",
        _output_parent_for_native(output),
    ]
    _append_option(argv, "-s", args.subsample)
    _append_option(argv, "-l", args.split_long_edges)
    _append_option(argv, "-d", args.display)
    _append_option(argv, "-b", args.boundary_fixing)
    _append_option(argv, "-q", args.quadric_level)
    _append_option(argv, "-np", args.threads)
    argv.extend(_strip_separator(extra))
    return argv


def _run_anisotropic(tool: str, argv: Sequence[str], output: Path) -> int:
    generated = output.parent / _ANISOTROPIC_OUTPUTS[tool]
    if generated.exists() and generated != output:
        generated.unlink()

    result = _run_native(tool, argv)
    if result != 0 or generated == output:
        return result
    if not generated.exists():
        print(f"remesh: expected native output was not created: {generated}", file=sys.stderr)
        return 1
    os.replace(generated, output)
    return 0


def _run_method(args: argparse.Namespace, extra: Sequence[str]) -> int:
    tool = _METHOD_TO_NATIVE[args.method]
    if tool == "OpenVDBSdfRemesh":
        argv = [args.input, args.output]
        _append_option(argv, "--resolution", args.resolution)
        _append_option(argv, "--level-set", args.level_set)
        if args.no_normalize:
            argv.append("--no-normalize")
        argv.extend(_strip_separator(extra))
        return _run_native(tool, argv)

    if tool in _ANISOTROPIC_OUTPUTS:
        return _run_anisotropic(tool, _anisotropic_args(args, extra), Path(args.output))

    return _run_native(tool, _acvd_args(args, extra))


def _add_common_mesh_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", help="input mesh path")
    parser.add_argument("output", help="output mesh path")


def _add_acvd_args(
    parser: argparse.ArgumentParser,
    *,
    parallel: bool = False,
    quadric: bool = False,
    anisotropic: bool = False,
) -> None:
    _add_common_mesh_args(parser)
    parser.add_argument("--vertices", "-n", required=True, type=int, help="target vertex count")
    parser.add_argument("--gradation", "-g", default=0.0, type=float, help="curvature gradation, 0 for uniform")
    parser.add_argument("--subsample", "-s", type=int, help="native ACVD subsampling threshold")
    parser.add_argument("--split-long-edges", "-l", type=float, help="split edges longer than ratio times average length")
    parser.add_argument("--display", "-d", type=int, choices=(0, 1, 2), help="native display mode")
    if not anisotropic:
        parser.add_argument("--force-manifold", "-m", type=int, choices=(0, 1), help="force manifold output")
    if not anisotropic or quadric:
        parser.add_argument("--boundary-fixing", "-b", type=int, choices=(0, 1), help="fix mesh boundaries")
    if quadric:
        parser.add_argument("--quadric-level", "-q", type=int, choices=(1, 2, 3), help="quadric optimization level")
    else:
        parser.set_defaults(quadric_level=None)
    if parallel:
        parser.add_argument("--threads", "-j", type=int, help="number of worker threads")
    else:
        parser.set_defaults(threads=None)
    if anisotropic:
        parser.set_defaults(force_manifold=None)
    if anisotropic and not quadric:
        parser.set_defaults(boundary_fixing=None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remesh",
        description="Run packaged native remeshing methods.",
    )
    subparsers = parser.add_subparsers(dest="method", metavar="method", required=True)

    acvd = subparsers.add_parser("acvd", help="ACVD isotropic remeshing")
    _add_acvd_args(acvd)

    acvd_parallel = subparsers.add_parser("acvd-parallel", help="parallel ACVD isotropic remeshing")
    _add_acvd_args(acvd_parallel, parallel=True)

    acvd_quadric = subparsers.add_parser("acvd-quadric", help="ACVD isotropic remeshing with quadric relocation")
    _add_acvd_args(acvd_quadric, quadric=True)

    acvd_quadric_parallel = subparsers.add_parser(
        "acvd-quadric-parallel",
        help="parallel ACVD isotropic remeshing with quadric relocation",
    )
    _add_acvd_args(acvd_quadric_parallel, parallel=True, quadric=True)

    acvd_anisotropic = subparsers.add_parser("acvd-anisotropic", help="ACVD anisotropic remeshing")
    _add_acvd_args(acvd_anisotropic, anisotropic=True)

    acvd_anisotropic_quadric = subparsers.add_parser(
        "acvd-anisotropic-quadric",
        help="ACVD anisotropic remeshing with quadric relocation",
    )
    _add_acvd_args(acvd_anisotropic_quadric, anisotropic=True, quadric=True)

    acvd_anisotropic_quadric_parallel = subparsers.add_parser(
        "acvd-anisotropic-quadric-parallel",
        help="parallel ACVD anisotropic remeshing with quadric relocation",
    )
    _add_acvd_args(acvd_anisotropic_quadric_parallel, anisotropic=True, quadric=True, parallel=True)

    openvdb = subparsers.add_parser("openvdb-sdf", help="OpenVDB SDF surface remeshing for OBJ meshes")
    _add_common_mesh_args(openvdb)
    openvdb.add_argument("--resolution", "-r", default=50.0, type=float, help="preprocessing resolution")
    openvdb.add_argument("--level-set", "-l", default=0.1, type=float, help="volumeToMesh level set value")
    openvdb.add_argument("--no-normalize", action="store_true", help="apply OpenVDB directly in input coordinates")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args, extra = parser.parse_known_args(argv)
    try:
        return _run_method(args, extra)
    except (RuntimeError, ValueError) as exc:
        print(f"remesh: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
