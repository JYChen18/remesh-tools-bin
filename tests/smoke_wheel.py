from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from remesh_tools_bin._cli import _native_env, _tool_path, main


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tetrahedron.obj"


def require_output(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Expected non-empty output: {path}")


def diagnose_acvd_crash(native_args: list[str]) -> None:
    gdb = shutil.which("gdb")
    if not sys.platform.startswith("linux") or gdb is None:
        return

    print("ACVD terminated by a signal; rerunning under gdb", file=sys.stderr)
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
            str(_tool_path("ACVD")),
            *native_args,
        ],
        check=False,
        env=_native_env(),
        text=True,
    )


def run() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory)
        openvdb_output = temporary_path / "openvdb.obj"
        acvd_output = temporary_path / "acvd.ply"

        openvdb_result = main(
            [
                "openvdb-sdf",
                str(FIXTURE),
                str(openvdb_output),
                "--resolution",
                "10",
            ]
        )
        if openvdb_result != 0:
            raise RuntimeError(f"OpenVDB smoke test failed with exit code {openvdb_result}")
        require_output(openvdb_output)

        acvd_result = main(
            [
                "acvd",
                str(FIXTURE),
                str(acvd_output),
                "--vertices",
                "4",
                "--gradation",
                "0",
                "--subsample",
                "1",
            ]
        )
        if acvd_result < 0:
            diagnose_acvd_crash(
                [
                    str(FIXTURE),
                    "4",
                    "0",
                    "-o",
                    f"{temporary_path}{os.sep}",
                    "-of",
                    acvd_output.name,
                    "-s",
                    "1",
                ]
            )
        if acvd_result != 0:
            raise RuntimeError(f"ACVD smoke test failed with exit code {acvd_result}")
        require_output(acvd_output)


if __name__ == "__main__":
    run()
