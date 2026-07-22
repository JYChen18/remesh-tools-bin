from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from native.tools import fetch_vtk_sdk


class VtkSdkWheelTests(unittest.TestCase):
    def archive_name(self, sys_platform: str, machine: str) -> str:
        with (
            mock.patch.object(fetch_vtk_sdk.sys, "platform", sys_platform),
            mock.patch.object(fetch_vtk_sdk.sys, "version_info", (3, 13)),
            mock.patch.object(fetch_vtk_sdk.platform, "machine", return_value=machine),
        ):
            return fetch_vtk_sdk._sdk_archive_name(fetch_vtk_sdk.SUPPORTED_VERSION)

    def test_linux_x86_64_wheel(self) -> None:
        self.assertEqual(
            self.archive_name("linux", "x86_64"),
            "vtk_sdk-9.6.2-cp313-cp313-linux_x86_64.whl",
        )

    def test_linux_arm64_wheel(self) -> None:
        self.assertEqual(
            self.archive_name("linux", "aarch64"),
            "vtk_sdk-9.6.2-cp313-cp313-linux_aarch64.whl",
        )

    def test_macos_arm64_wheel(self) -> None:
        self.assertEqual(
            self.archive_name("darwin", "arm64"),
            "vtk_sdk-9.6.2-cp313-cp313-macosx_11_0_arm64.whl",
        )

    def test_windows_x86_64_wheel(self) -> None:
        self.assertEqual(
            self.archive_name("win32", "AMD64"),
            "vtk_sdk-9.6.2-cp313-cp313-win_amd64.whl",
        )

    def test_unknown_platform_is_rejected(self) -> None:
        with (
            mock.patch.object(fetch_vtk_sdk.sys, "platform", "linux"),
            mock.patch.object(
                fetch_vtk_sdk.platform, "machine", return_value="riscv64"
            ),
            self.assertRaisesRegex(RuntimeError, "not known for platform"),
        ):
            fetch_vtk_sdk._platform_tag()

    def test_unsupported_python_is_rejected(self) -> None:
        with (
            mock.patch.object(fetch_vtk_sdk.sys, "version_info", (3, 9)),
            self.assertRaisesRegex(RuntimeError, "3.10 through 3.13"),
        ):
            fetch_vtk_sdk._cpython_tag()

    def test_wheel_extraction_rejects_parent_paths(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            wheel = root / "sdk.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("../outside", "bad")

            with self.assertRaisesRegex(RuntimeError, "outside destination"):
                fetch_vtk_sdk._safe_extract(wheel, root / "sdk")

            self.assertFalse((root / "outside").exists())


if __name__ == "__main__":
    unittest.main()
