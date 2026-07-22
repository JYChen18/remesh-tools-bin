from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
