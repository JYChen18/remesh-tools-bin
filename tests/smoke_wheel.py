from __future__ import annotations

import tempfile
from pathlib import Path

from remesh_tools_bin._cli import main


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tetrahedron.obj"


def require_output(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Expected non-empty output: {path}")


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
        if acvd_result != 0:
            raise RuntimeError(f"ACVD smoke test failed with exit code {acvd_result}")
        require_output(acvd_output)


if __name__ == "__main__":
    run()
