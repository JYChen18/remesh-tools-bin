from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sim_asset_tools.cli import main as sim_assets_main
from sim_asset_tools.native import _native_env, _tool_path, run_native


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tetrahedron.obj"
EXPECTED_NATIVE_TOOLS = {
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
ACVD_CASES = (
    ("acvd", "ACVD", (), ()),
    ("acvd-parallel", "ACVDP", ("--threads", "1"), ("-np", "1")),
    ("acvd-quadric", "ACVDQ", ("--quadric-level", "1"), ("-q", "1")),
    (
        "acvd-quadric-parallel",
        "ACVDQP",
        ("--quadric-level", "1", "--threads", "1"),
        ("-q", "1", "-np", "1"),
    ),
    ("acvd-anisotropic", "AnisotropicRemeshing", (), ()),
    (
        "acvd-anisotropic-quadric",
        "AnisotropicRemeshingQ",
        ("--quadric-level", "1"),
        ("-q", "1"),
    ),
    (
        "acvd-anisotropic-quadric-parallel",
        "AnisotropicRemeshingQP",
        ("--quadric-level", "1", "--threads", "1"),
        ("-q", "1", "-np", "1"),
    ),
)


def require_output(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Expected non-empty output: {path}")


def diagnose_native_crash(tool: str, native_args: list[str]) -> None:
    gdb = shutil.which("gdb")
    if not sys.platform.startswith("linux") or gdb is None:
        return

    print(f"{tool} terminated by a signal; rerunning under gdb", file=sys.stderr)
    subprocess.run(
        [
            gdb,
            "--batch",
            "-ex",
            "set pagination off",
            "-ex",
            "run",
            "-ex",
            "thread apply all backtrace",
            "--args",
            str(_tool_path(tool)),
            *native_args,
        ],
        check=False,
        env=_native_env(),
        text=True,
    )


def verify_installed_tools() -> None:
    for tool in sorted(EXPECTED_NATIVE_TOOLS):
        path = _tool_path(tool)
        if not path.is_file():
            raise RuntimeError(f"Expected installed native executable: {path}")


def run_acvd_cases(temporary_path: Path) -> None:
    for method, tool, cli_extra, native_extra in ACVD_CASES:
        output = temporary_path / f"{method}.ply"
        argv = [
            "mesh",
            "acvd",
            str(FIXTURE),
            str(output),
            "--method",
            method,
            "--vertices",
            "4",
            "--gradation",
            "0",
            "--subsample",
            "1",
            *cli_extra,
        ]
        result = sim_assets_main(argv)
        if result != 0:
            if result < 0:
                native_args = [
                    str(FIXTURE),
                    "4",
                    "0",
                    "-o",
                    f"{temporary_path}{os.sep}",
                ]
                if not tool.startswith("AnisotropicRemeshing"):
                    native_args.extend(("-of", output.name))
                native_args.extend(("-s", "1", *native_extra))
                diagnose_native_crash(tool, native_args)
            raise RuntimeError(f"{method} smoke test failed with exit code {result}")
        require_output(output)


def write_volume_fixture(root: Path) -> Path:
    raw_path = root / "labels.raw"
    values = bytearray(5 * 5 * 5)
    for z in range(1, 4):
        for y in range(1, 4):
            for x in range(1, 4):
                values[x + 5 * (y + 5 * z)] = 1
    raw_path.write_bytes(values)

    header_path = root / "labels.mhd"
    header_path.write_text(
        "\n".join(
            (
                "ObjectType = Image",
                "NDims = 3",
                "BinaryData = True",
                "BinaryDataByteOrderMSB = False",
                "CompressedData = False",
                "TransformMatrix = 1 0 0 0 1 0 0 0 1",
                "Offset = 0 0 0",
                "CenterOfRotation = 0 0 0",
                "ElementSpacing = 1 1 1",
                "DimSize = 5 5 5",
                "ElementType = MET_UCHAR",
                f"ElementDataFile = {raw_path.name}",
                "",
            )
        ),
        encoding="ascii",
    )
    return header_path


def run_volume_analysis(temporary_path: Path) -> None:
    fixture = write_volume_fixture(temporary_path)
    output_directory = temporary_path / "volume-output"
    output_directory.mkdir()
    native_args = [
        str(fixture),
        "-n",
        "0",
        "-j",
        "1",
        "-f",
        "ply",
        "-o",
        str(output_directory),
    ]
    result = run_native(
        "VolumeAnalysis",
        native_args,
        cwd=temporary_path,
    )
    if result.returncode < 0:
        diagnose_native_crash("VolumeAnalysis", native_args)
    if result.returncode != 0:
        raise RuntimeError(
            f"VolumeAnalysis smoke test failed with exit code {result.returncode}"
        )
    require_output(output_directory / "1.ply")
    require_output(temporary_path / "meshes.xml")


def run() -> None:
    verify_installed_tools()
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory)
        openvdb_output = temporary_path / "openvdb.obj"

        openvdb_result = sim_assets_main(
            [
                "mesh",
                "openvdb",
                str(FIXTURE),
                str(openvdb_output),
                "--resolution",
                "10",
            ]
        )
        if openvdb_result != 0:
            raise RuntimeError(
                f"OpenVDB smoke test failed with exit code {openvdb_result}"
            )
        require_output(openvdb_output)
        run_acvd_cases(temporary_path)
        run_volume_analysis(temporary_path)


if __name__ == "__main__":
    run()
