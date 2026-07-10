from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from remesh_tools_bin._cli import _native_env, _tool_path, _vtk_library_dirs, main


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


def diagnose_windows_dlls() -> None:
    if os.name != "nt":
        return

    try:
        import pefile
    except ImportError:
        print("pefile is unavailable; cannot diagnose Windows DLL loading", file=sys.stderr)
        return

    env = _native_env()
    search_dirs = [Path(path) for path in env.get("PATH", "").split(os.pathsep) if path]
    package_dir = _tool_path("ACVD").parents[2]
    package_roots = [package_dir, package_dir.parent / "remesh_tools_bin.libs", *_vtk_library_dirs()]

    def is_packaged(path: Path) -> bool:
        resolved = path.resolve()
        return any(
            root.exists()
            and (resolved == root.resolve() or root.resolve() in resolved.parents)
            for root in package_roots
        )

    def find_dll(name: str) -> Path | None:
        for directory in search_dirs:
            candidate = directory / name
            if candidate.is_file():
                return candidate
        return None

    pending = [_tool_path("ACVD")]
    visited: set[Path] = set()
    while pending:
        binary = pending.pop()
        binary = binary.resolve()
        if binary in visited:
            continue
        visited.add(binary)

        pe = pefile.PE(str(binary), fast_load=True)
        pe.parse_data_directories(
            directories=[
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
            ]
        )
        imports = []
        for attribute in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            imports.extend(getattr(pe, attribute, ()))

        for entry in imports:
            name = entry.dll.decode(errors="replace")
            dependency = find_dll(name)
            if dependency is None:
                print(f"Unresolved DLL: {binary.name} -> {name}", file=sys.stderr)
            else:
                print(f"Resolved DLL: {binary.name} -> {dependency}", file=sys.stderr)
                if is_packaged(dependency):
                    pending.append(dependency)


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
        if acvd_result == 0xC0000135:
            diagnose_windows_dlls()
        if acvd_result != 0:
            raise RuntimeError(f"ACVD smoke test failed with exit code {acvd_result}")
        require_output(acvd_output)


if __name__ == "__main__":
    run()
