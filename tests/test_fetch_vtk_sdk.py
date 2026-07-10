from __future__ import annotations

import unittest
from unittest import mock

from tools import fetch_vtk_sdk


class VtkSdkArchiveTests(unittest.TestCase):
    def archive_name(self, sys_platform: str, machine: str) -> str:
        with (
            mock.patch.object(fetch_vtk_sdk.sys, "platform", sys_platform),
            mock.patch.object(fetch_vtk_sdk.sys, "version_info", (3, 13)),
            mock.patch.object(fetch_vtk_sdk.platform, "machine", return_value=machine),
        ):
            return fetch_vtk_sdk._sdk_archive_name(fetch_vtk_sdk.SUPPORTED_VERSION)

    def test_linux_x86_64_archive_uses_vtk_9_5_tag_order(self) -> None:
        self.assertEqual(
            self.archive_name("linux", "x86_64"),
            "vtk-wheel-sdk-9.5.2-cp313-cp313-"
            "manylinux2014_x86_64.manylinux_2_17_x86_64.tar.xz",
        )

    def test_macos_arm64_archive(self) -> None:
        self.assertEqual(
            self.archive_name("darwin", "arm64"),
            "vtk-wheel-sdk-9.5.2-cp313-cp313-macosx_11_0_arm64.tar.xz",
        )

    def test_windows_x86_64_archive(self) -> None:
        self.assertEqual(
            self.archive_name("win32", "AMD64"),
            "vtk-wheel-sdk-9.5.2-cp313-cp313-win_amd64.tar.xz",
        )

    def test_unknown_platform_is_rejected(self) -> None:
        with (
            mock.patch.object(fetch_vtk_sdk.sys, "platform", "linux"),
            mock.patch.object(fetch_vtk_sdk.platform, "machine", return_value="aarch64"),
            self.assertRaisesRegex(RuntimeError, "not known for platform"),
        ):
            fetch_vtk_sdk._platform_tag()

    def test_unsupported_python_is_rejected(self) -> None:
        with (
            mock.patch.object(fetch_vtk_sdk.sys, "version_info", (3, 9)),
            self.assertRaisesRegex(RuntimeError, "3.10 through 3.13"),
        ):
            fetch_vtk_sdk._cpython_tag()


if __name__ == "__main__":
    unittest.main()
