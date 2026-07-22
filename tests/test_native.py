from __future__ import annotations

import os
import platform
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from native.tools import fetch_vtk_sdk, patch_openvdb
from sim_asset_tools import native


class NativeEnvironmentTests(unittest.TestCase):
    def test_includes_windows_vtk_library_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            site_packages = Path(temporary_directory)
            vtkmodules_dir = site_packages / "vtkmodules"
            vtk_libs_dir = site_packages / "vtk.libs"
            vtkmodules_dir.mkdir()
            vtk_libs_dir.mkdir()

            with mock.patch.object(
                native, "_vtkmodules_dir", return_value=vtkmodules_dir
            ):
                library_dirs = native._vtk_library_dirs()

            self.assertEqual(library_dirs, (vtk_libs_dir, vtkmodules_dir))

    def test_includes_delvewheel_library_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            site_packages = Path(temporary_directory)
            package_dir = site_packages / "sim_asset_tools"
            vendored_dir = site_packages / "sim_asset_tools.libs"
            package_dir.mkdir()
            (package_dir / "_native" / "bin").mkdir(parents=True)
            (package_dir / "_native" / "lib").mkdir()
            vendored_dir.mkdir()

            fake_native = package_dir / "native.py"
            with (
                mock.patch.object(native, "__file__", str(fake_native)),
                mock.patch.object(native, "_vtk_library_dirs", return_value=()),
            ):
                env = native._native_env()

            if os.name == "nt":
                path_key = "PATH"
            elif native.sys.platform == "darwin":
                path_key = "DYLD_LIBRARY_PATH"
            else:
                path_key = "LD_LIBRARY_PATH"
            paths = env[path_key].split(os.pathsep)
            self.assertEqual(
                paths[:3],
                [
                    str(package_dir / "_native" / "bin"),
                    str(package_dir / "_native" / "lib"),
                    str(vendored_dir),
                ],
            )


class NativeBuildSupportTests(unittest.TestCase):
    def sdk_archive_name(self, sys_platform: str, machine: str) -> str:
        with (
            mock.patch.object(fetch_vtk_sdk.sys, "platform", sys_platform),
            mock.patch.object(fetch_vtk_sdk.sys, "version_info", (3, 13)),
            mock.patch.object(platform, "machine", return_value=machine),
        ):
            return fetch_vtk_sdk._sdk_archive_name(fetch_vtk_sdk.SUPPORTED_VERSION)

    def test_selects_the_platform_specific_vtk_sdk(self) -> None:
        cases = (
            ("linux", "x86_64", "vtk_sdk-9.6.2-cp313-cp313-linux_x86_64.whl"),
            ("linux", "aarch64", "vtk_sdk-9.6.2-cp313-cp313-linux_aarch64.whl"),
            ("darwin", "arm64", "vtk_sdk-9.6.2-cp313-cp313-macosx_11_0_arm64.whl"),
            ("win32", "AMD64", "vtk_sdk-9.6.2-cp313-cp313-win_amd64.whl"),
        )

        for sys_platform, machine, expected in cases:
            with self.subTest(platform=sys_platform, machine=machine):
                self.assertEqual(
                    self.sdk_archive_name(sys_platform, machine), expected
                )

    def test_rejects_unsupported_vtk_sdk_targets(self) -> None:
        with (
            mock.patch.object(fetch_vtk_sdk.sys, "platform", "linux"),
            mock.patch.object(platform, "machine", return_value="riscv64"),
            self.assertRaisesRegex(RuntimeError, "not known for platform"),
        ):
            fetch_vtk_sdk._platform_tag()

        with (
            mock.patch.object(fetch_vtk_sdk.sys, "version_info", (3, 9)),
            self.assertRaisesRegex(RuntimeError, "3.10 through 3.13"),
        ):
            fetch_vtk_sdk._cpython_tag()

    def test_vtk_sdk_extraction_rejects_parent_paths(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            wheel = root / "sdk.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("../outside", "bad")

            with self.assertRaisesRegex(RuntimeError, "outside destination"):
                fetch_vtk_sdk._safe_extract(wheel, root / "sdk")

            self.assertFalse((root / "outside").exists())


class OpenVdbPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.openvdb_dir = Path(self.temporary_directory.name) / "openvdb"
        (self.openvdb_dir / "tree").mkdir(parents=True)
        (self.openvdb_dir / "tools").mkdir()

    def write_legacy_headers(self) -> None:
        (self.openvdb_dir / "tree" / "NodeManager.h").write_text(
            "\n".join(["OpT::template eval(mNodeOp, it);"] * 3),
            encoding="utf-8",
        )
        (self.openvdb_dir / "tools" / "PointIndexGrid.h").write_text(
            "BaseLeaf::merge<Policy>(rhs);",
            encoding="utf-8",
        )

    def test_patches_legacy_headers_idempotently(self) -> None:
        self.write_legacy_headers()

        patch_openvdb.patch_legacy_headers(self.openvdb_dir)
        patch_openvdb.patch_legacy_headers(self.openvdb_dir)

        node_manager = (self.openvdb_dir / "tree" / "NodeManager.h").read_text(
            encoding="utf-8"
        )
        point_index_grid = (
            self.openvdb_dir / "tools" / "PointIndexGrid.h"
        ).read_text(encoding="utf-8")
        self.assertEqual(node_manager.count("OpT::eval"), 3)
        self.assertNotIn("OpT::template eval", node_manager)
        self.assertIn("BaseLeaf::template merge<Policy>(rhs);", point_index_grid)

    def test_rejects_unexpected_legacy_header_shape(self) -> None:
        self.write_legacy_headers()
        (self.openvdb_dir / "tree" / "NodeManager.h").write_text(
            "OpT::template eval(mNodeOp, it);",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RuntimeError, "Expected 3 occurrence"):
            patch_openvdb.patch_legacy_headers(self.openvdb_dir)


if __name__ == "__main__":
    unittest.main()
