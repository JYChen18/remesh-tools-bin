#!/usr/bin/env python3
"""Fetch and expose the official VTK wheel SDK for sim-asset-tools builds."""

from __future__ import annotations

import argparse
import os
import platform
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


BASE_URL = "https://vtk.org/files/wheel-sdks/vtk-sdk"
SUPPORTED_VERSION = "9.6.2"
MINIMUM_PYTHON = (3, 10)
MAXIMUM_PYTHON = (3, 13)
CHARCONV_COMPATIBILITY_MARKER = (
    "sim-asset-tools: evaluate charconv support in the consumer toolchain"
)
CHARCONV_COMPATIBILITY_PATCH = f"""

// {CHARCONV_COMPATIBILITY_MARKER}
// The wheel SDK records the feature checks from the toolchain that built VTK.
// Re-enable VTK's compatibility definitions when this SDK is consumed with an
// older standard library or compiler.
#include <version>
#if (defined(_GLIBCXX_RELEASE) && _GLIBCXX_RELEASE <= 9) || \\
  (defined(_LIBCPP_VERSION) && defined(__clang__) && __clang_major__ <= 10)
#undef VTK_HAS_STD_CHARS_FORMAT
#undef VTK_HAS_STD_FROM_CHARS_RESULT
#undef VTK_HAS_STD_TO_CHARS_RESULT
#endif
"""


def _cpython_tag() -> str:
    if platform.python_implementation() != "CPython":
        raise RuntimeError(
            f"VTK {SUPPORTED_VERSION} wheels are only available for CPython"
        )

    major, minor = sys.version_info[:2]
    if (major, minor) < MINIMUM_PYTHON or (major, minor) > MAXIMUM_PYTHON:
        raise RuntimeError(
            f"VTK {SUPPORTED_VERSION} SDK archives are available for "
            f"CPython {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} through "
            f"{MAXIMUM_PYTHON[0]}.{MAXIMUM_PYTHON[1]}"
        )

    return f"cp{major}{minor}"


def _platform_tag() -> str:
    machine = platform.machine().lower()

    if sys.platform.startswith("linux"):
        if machine in {"x86_64", "amd64"}:
            return "linux_x86_64"
        if machine in {"aarch64", "arm64"}:
            return "linux_aarch64"
    elif sys.platform == "darwin":
        if machine == "arm64":
            return "macosx_11_0_arm64"
        if machine in {"x86_64", "amd64"}:
            return "macosx_10_10_x86_64"
    elif sys.platform == "win32":
        if machine in {"amd64", "x86_64"}:
            return "win_amd64"

    raise RuntimeError(
        f"VTK {SUPPORTED_VERSION} SDK archive is not known for "
        f"platform {sys.platform!r}/{machine!r}"
    )


def _sdk_archive_name(version: str) -> str:
    py_tag = _cpython_tag()
    return f"vtk_sdk-{version}-{py_tag}-{py_tag}-{_platform_tag()}.whl"


def _download(url: str, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        if zipfile.is_zipfile(archive):
            return
        archive.unlink()

    tmp = archive.with_name(f"{archive.name}.{os.getpid()}.part")
    tmp.unlink(missing_ok=True)
    print(f"Downloading {url}", flush=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "sim-asset-tools-build"}
    )
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            tmp.open("xb") as handle,
        ):
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"VTK SDK archive does not exist at {url}") from exc

    if not zipfile.is_zipfile(tmp):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded VTK SDK is not a valid wheel: {url}")
    tmp.replace(archive)


def _safe_extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest.resolve()

    with zipfile.ZipFile(archive) as wheel:
        members = wheel.infolist()
        for member in members:
            target = (dest / member.filename).resolve()
            if target != resolved_dest and resolved_dest not in target.parents:
                raise RuntimeError(
                    f"Refusing to extract path outside destination: {member.filename}"
                )

        for member in members:
            target = Path(wheel.extract(member, dest))
            mode = (member.external_attr >> 16) & 0o777
            if mode and target.is_file():
                target.chmod(mode)


def _find_vtk_dir(root: Path) -> Path:
    candidates = sorted(root.rglob("VTKConfig.cmake")) + sorted(
        root.rglob("vtk-config.cmake")
    )
    if not candidates:
        raise RuntimeError(
            f"Could not find VTKConfig.cmake or vtk-config.cmake under {root}"
        )

    preferred = [
        path
        for path in candidates
        if "cmake" in path.parts and any(part.startswith("vtk-") for part in path.parts)
    ]
    return (preferred or candidates)[0].parent


def _patch_charconv_compatibility(root: Path) -> None:
    headers = sorted(root.rglob("vtkCharConvCompatibility.h"))
    if not headers:
        raise RuntimeError(
            f"Could not find vtkCharConvCompatibility.h under VTK SDK {root}"
        )

    needle = "#define VTK_HAS_STD_TO_CHARS_RESULT\n"
    for header in headers:
        content = header.read_text(encoding="utf-8")
        if CHARCONV_COMPATIBILITY_MARKER in content:
            continue
        if content.count(needle) != 1:
            raise RuntimeError(
                f"Could not patch unexpected VTK charconv compatibility header: {header}"
            )
        header.write_text(
            content.replace(needle, needle + CHARCONV_COMPATIBILITY_PATCH, 1),
            encoding="utf-8",
        )


def _write_cmake_output(path: Path, vtk_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(vtk_dir).replace("\\", "/")
    path.write_text(f'set(SIM_ASSET_TOOLS_VTK_DIR "{escaped}")\n', encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--dest", required=True, type=Path)
    parser.add_argument("--cmake-output", required=True, type=Path)
    args = parser.parse_args()

    if args.version != SUPPORTED_VERSION:
        raise RuntimeError(
            f"sim-asset-tools is pinned to VTK {SUPPORTED_VERSION}, got {args.version}"
        )

    override = os.environ.get("SIM_ASSET_TOOLS_VTK_SDK_DIR")
    if override:
        vtk_dir = _find_vtk_dir(Path(override))
        _write_cmake_output(args.cmake_output, vtk_dir)
        print(f"Using VTK SDK override: {vtk_dir}", flush=True)
        return 0

    archive_name = _sdk_archive_name(args.version)
    archive = args.dest / "downloads" / archive_name
    sdk_root = args.dest / "sdk" / archive_name.removesuffix(".whl")
    stamp = sdk_root / ".sim-asset-tools-extracted"

    _download(f"{BASE_URL}/{archive_name}", archive)
    if not stamp.exists():
        _safe_extract(archive, sdk_root)
        stamp.write_text(f"{archive_name}\n", encoding="utf-8")

    _patch_charconv_compatibility(sdk_root)
    vtk_dir = _find_vtk_dir(sdk_root)
    _write_cmake_output(args.cmake_output, vtk_dir)
    print(f"Using VTK SDK: {vtk_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
