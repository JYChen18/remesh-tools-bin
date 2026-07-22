"""Command-line interface for simulation asset preparation."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Sequence


def _add_surface_parameters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--resolution", type=float, default=50.0)
    parser.add_argument("--level-set", type=float, default=0.1)
    parser.add_argument("--vertices", type=int, default=1024)
    parser.add_argument("--gradation", type=float, default=1.5)
    parser.add_argument("--force-manifold", type=int, choices=(0, 1), default=1)


def _add_object_recipe(parser: argparse.ArgumentParser) -> None:
    _add_surface_parameters(parser)
    parser.add_argument("--no-normalize", action="store_true")
    parser.add_argument("--coacd-threshold", type=float, default=0.05)
    parser.add_argument("--coacd-max-convex-hull", type=int, default=-1)
    parser.add_argument("--coacd-preprocess-mode", default="auto")
    parser.add_argument("--coacd-preprocess-resolution", type=int, default=50)
    parser.add_argument("--coacd-real-metric", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--formats",
        default="mjcf,urdf",
        help="comma-separated model outputs: mjcf,urdf",
    )


def _object_recipe(args: argparse.Namespace):
    from .workflows import ObjectRecipe

    return ObjectRecipe(
        normalize=not args.no_normalize,
        resolution=args.resolution,
        level_set=args.level_set,
        target_vertices=args.vertices,
        gradation=args.gradation,
        force_manifold=args.force_manifold,
        coacd_threshold=args.coacd_threshold,
        coacd_max_convex_hull=args.coacd_max_convex_hull,
        coacd_preprocess_mode=args.coacd_preprocess_mode,
        coacd_preprocess_resolution=args.coacd_preprocess_resolution,
        coacd_real_metric=args.coacd_real_metric,
        seed=args.seed,
    )


def _output_formats(value: str) -> tuple[str, ...]:
    formats = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not formats:
        raise ValueError("At least one object output format is required")
    return formats


def _body_surface_recipe(args: argparse.Namespace):
    from .workflows import BodySurfaceRecipe

    return BodySurfaceRecipe(
        resolution=args.resolution,
        level_set=args.level_set,
        target_vertices=args.vertices,
        gradation=args.gradation,
        force_manifold=args.force_manifold,
    )


def _mesh_normalize(args: argparse.Namespace) -> int:
    from .mesh.io import load_mesh
    from .mesh.normalize import normalize_mesh

    mesh, _, _ = normalize_mesh(load_mesh(args.input))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(output)
    print(output)
    return 0


def _mesh_openvdb(args: argparse.Namespace) -> int:
    from .mesh.openvdb import openvdb_sdf

    output = openvdb_sdf(
        args.input,
        args.output,
        resolution=args.resolution,
        level_set=args.level_set,
        normalize=not args.no_normalize,
    )
    print(output)
    return 0


def _mesh_acvd(args: argparse.Namespace) -> int:
    from .mesh.acvd import acvd_remesh

    output = acvd_remesh(
        args.input,
        args.output,
        method=args.method,
        vertices=args.vertices,
        gradation=args.gradation,
        force_manifold=args.force_manifold,
        threads=args.threads,
        quadric_level=args.quadric_level,
        boundary_fixing=args.boundary_fixing,
        subsample=args.subsample,
        split_long_edges=args.split_long_edges,
        display=args.display,
    )
    print(output)
    return 0


def _mesh_coacd(args: argparse.Namespace) -> int:
    from .mesh.coacd import decompose_mesh
    from .mesh.io import load_mesh

    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        if not args.overwrite:
            raise FileExistsError(f"Output directory is not empty: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    parts = decompose_mesh(
        load_mesh(args.input),
        threshold=args.threshold,
        max_convex_hull=args.max_convex_hull,
        preprocess_mode=args.preprocess_mode,
        preprocess_resolution=args.preprocess_resolution,
        real_metric=args.real_metric,
        seed=args.seed,
    )
    for index, part in enumerate(parts):
        part.export(output / f"part_{index:03d}.obj")
    print(f"wrote {len(parts)} parts to {output}")
    return 0


def _prepare_object(args: argparse.Namespace) -> int:
    from .workflows import prepare_object

    result = prepare_object(
        args.input,
        args.output,
        recipe=_object_recipe(args),
        formats=_output_formats(args.formats),
        overwrite=args.overwrite,
    )
    print(result.manifest_path)
    return 0


def _prepare_objects(args: argparse.Namespace) -> int:
    from .workflows import prepare_objects

    results = prepare_objects(
        args.input,
        args.output,
        recipe=_object_recipe(args),
        formats=_output_formats(args.formats),
        jobs=args.jobs,
        overwrite=args.overwrite,
    )
    for result in results:
        print(result.manifest_path)
    return 0


def _prepare_body_surfaces(args: argparse.Namespace) -> int:
    from .workflows import prepare_body_surfaces

    path = prepare_body_surfaces(
        args.model,
        args.output,
        recipe=_body_surface_recipe(args),
        bodies=args.body,
        overwrite=args.overwrite,
        keep_work=args.keep_work,
    )
    print(path)
    return 0


def _check_object(args: argparse.Namespace) -> int:
    from .workflows import check_object

    errors = check_object(args.asset)
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    print(f"ok: {args.asset}")
    return 0


def _check_body_surfaces(args: argparse.Namespace) -> int:
    from .workflows import check_body_surfaces

    errors = check_body_surfaces(args.model, args.assets, bodies=args.body)
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    print(f"ok: {args.assets}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sim-assets", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    mesh = commands.add_parser("mesh", help="independent raw-mesh operations")
    mesh_commands = mesh.add_subparsers(dest="mesh_command", required=True)

    normalize = mesh_commands.add_parser("normalize", help="center and scale a mesh")
    normalize.add_argument("input")
    normalize.add_argument("output")
    normalize.set_defaults(func=_mesh_normalize)

    openvdb = mesh_commands.add_parser("openvdb", help="apply OpenVDB SDF processing")
    openvdb.add_argument("input")
    openvdb.add_argument("output")
    openvdb.add_argument("--resolution", type=float, default=50.0)
    openvdb.add_argument("--level-set", type=float, default=0.1)
    openvdb.add_argument("--no-normalize", action="store_true")
    openvdb.set_defaults(func=_mesh_openvdb)

    from .mesh.acvd import available_methods

    acvd = mesh_commands.add_parser("acvd", help="apply ACVD remeshing")
    acvd.add_argument("input")
    acvd.add_argument("output")
    acvd.add_argument("--method", choices=available_methods(), default="acvd")
    acvd.add_argument("--vertices", type=int, required=True)
    acvd.add_argument("--gradation", type=float, default=0.0)
    acvd.add_argument("--force-manifold", type=int, choices=(0, 1), default=1)
    acvd.add_argument("--threads", type=int)
    acvd.add_argument("--quadric-level", type=int, choices=(1, 2, 3))
    acvd.add_argument("--boundary-fixing", type=int, choices=(0, 1))
    acvd.add_argument("--subsample", type=int)
    acvd.add_argument("--split-long-edges", type=float)
    acvd.add_argument("--display", type=int, choices=(0, 1, 2))
    acvd.set_defaults(func=_mesh_acvd)

    coacd = mesh_commands.add_parser("coacd", help="apply convex decomposition")
    coacd.add_argument("input")
    coacd.add_argument("output")
    coacd.add_argument("--threshold", type=float, default=0.05)
    coacd.add_argument("--max-convex-hull", type=int, default=-1)
    coacd.add_argument("--preprocess-mode", default="auto")
    coacd.add_argument("--preprocess-resolution", type=int, default=50)
    coacd.add_argument("--real-metric", action="store_true")
    coacd.add_argument("--seed", type=int, default=0)
    coacd.add_argument("--overwrite", action="store_true")
    coacd.set_defaults(func=_mesh_coacd)

    prepare = commands.add_parser("prepare", help="prepare complete asset workflows")
    prepare_commands = prepare.add_subparsers(dest="prepare_command", required=True)

    object_parser = prepare_commands.add_parser("object", help="prepare one object")
    object_parser.add_argument("input")
    object_parser.add_argument("--output", required=True)
    _add_object_recipe(object_parser)
    object_parser.add_argument("--overwrite", action="store_true")
    object_parser.set_defaults(func=_prepare_object)

    objects_parser = prepare_commands.add_parser(
        "objects", help="prepare a folder of objects"
    )
    objects_parser.add_argument("input")
    objects_parser.add_argument("--output", required=True)
    objects_parser.add_argument("--jobs", type=int, default=1)
    _add_object_recipe(objects_parser)
    objects_parser.add_argument("--overwrite", action="store_true")
    objects_parser.set_defaults(func=_prepare_objects)

    body_surfaces = prepare_commands.add_parser(
        "body-surfaces", help="prepare body-local collision surfaces"
    )
    body_surfaces.add_argument("model")
    body_surfaces.add_argument("--output", required=True)
    body_surfaces.add_argument("--body", action="append")
    _add_surface_parameters(body_surfaces)
    body_surfaces.add_argument("--overwrite", action="store_true")
    body_surfaces.add_argument("--keep-work", action="store_true")
    body_surfaces.set_defaults(func=_prepare_body_surfaces)

    check = commands.add_parser("check", help="validate prepared assets")
    check_commands = check.add_subparsers(dest="check_command", required=True)

    check_object = check_commands.add_parser("object", help="check an object asset")
    check_object.add_argument("asset")
    check_object.set_defaults(func=_check_object)

    check_surfaces = check_commands.add_parser(
        "body-surfaces", help="check body-surface assets"
    )
    check_surfaces.add_argument("model")
    check_surfaces.add_argument("--assets", required=True)
    check_surfaces.add_argument("--body", action="append")
    check_surfaces.set_defaults(func=_check_body_surfaces)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileExistsError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"sim-assets: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
