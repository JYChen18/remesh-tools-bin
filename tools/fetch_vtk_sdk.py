#!/usr/bin/env python3
"""Fetch and expose the official VTK wheel SDK archive for ACVD builds."""

from __future__ import annotations

import argparse
import os
import platform
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = "https://vtk.org/files/wheel-sdks"
SUPPORTED_VERSION = "9.4.0"


def _cpython_tag() -> str:
    if platform.python_implementation() != "CPython":
        raise RuntimeError("VTK 9.4.0 wheels are only available for CPython")

    major, minor = sys.version_info[:2]
    if major != 3 or minor < 8 or minor > 13:
        raise RuntimeError("VTK 9.4.0 SDK archives are available for CPython 3.8 through 3.13")

    return f"cp{major}{minor}"


def _platform_tag() -> str:
    machine = platform.machine().lower()

    if sys.platform.startswith("linux"):
        if machine in {"x86_64", "amd64"}:
            return "manylinux_2_17_x86_64.manylinux2014_x86_64"
    elif sys.platform == "darwin":
        if machine == "arm64":
            return "macosx_11_0_arm64"
        if machine in {"x86_64", "amd64"}:
            return "macosx_10_10_x86_64"
    elif sys.platform == "win32":
        if machine in {"amd64", "x86_64"}:
            return "win_amd64"

    raise RuntimeError(f"VTK 9.4.0 SDK archive is not known for platform {sys.platform!r}/{machine!r}")


def _sdk_archive_name(version: str) -> str:
    py_tag = _cpython_tag()
    return f"vtk-wheel-sdk-{version}-{py_tag}-{py_tag}-{_platform_tag()}.tar.xz"


def _download(url: str, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        return

    tmp = archive.with_name(f"{archive.name}.{os.getpid()}.part")
    print(f"Downloading {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "acvd-bin-build"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, tmp.open("xb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"VTK SDK archive does not exist at {url}") from exc

    tmp.replace(archive)


def _safe_extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest.resolve()

    with tarfile.open(archive, "r:xz") as tar:
        members = tar.getmembers()
        for member in members:
            target = (dest / member.name).resolve()
            if target != resolved_dest and resolved_dest not in target.parents:
                raise RuntimeError(f"Refusing to extract path outside destination: {member.name}")
        tar.extractall(dest, members=members)


def _find_vtk_dir(root: Path) -> Path:
    candidates = sorted(root.rglob("VTKConfig.cmake")) + sorted(root.rglob("vtk-config.cmake"))
    if not candidates:
        raise RuntimeError(f"Could not find VTKConfig.cmake or vtk-config.cmake under {root}")

    preferred = [
        path
        for path in candidates
        if "cmake" in path.parts and any(part.startswith("vtk-") for part in path.parts)
    ]
    return (preferred or candidates)[0].parent


def _write_cmake_output(path: Path, vtk_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(vtk_dir).replace("\\", "/")
    path.write_text(f'set(ACVD_BIN_VTK_DIR "{escaped}")\n', encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--dest", required=True, type=Path)
    parser.add_argument("--cmake-output", required=True, type=Path)
    args = parser.parse_args()

    if args.version != SUPPORTED_VERSION:
        raise RuntimeError(f"acvd-bin is pinned to VTK {SUPPORTED_VERSION}, got {args.version}")

    override = os.environ.get("ACVD_BIN_VTK_SDK_DIR")
    if override:
        vtk_dir = _find_vtk_dir(Path(override))
        _write_cmake_output(args.cmake_output, vtk_dir)
        print(f"Using VTK SDK override: {vtk_dir}", flush=True)
        return 0

    archive_name = _sdk_archive_name(args.version)
    archive = args.dest / "downloads" / archive_name
    extract_root = args.dest / "extracted" / archive_name.removesuffix(".tar.xz")
    stamp = extract_root / ".acvd-bin-extracted"

    _download(f"{BASE_URL}/{archive_name}", archive)
    if not stamp.exists():
        _safe_extract(archive, extract_root)
        stamp.write_text("ok\n", encoding="utf-8")

    vtk_dir = _find_vtk_dir(extract_root)
    _write_cmake_output(args.cmake_output, vtk_dir)
    print(f"Using VTK SDK: {vtk_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
