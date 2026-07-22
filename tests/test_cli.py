from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sim_asset_tools import cli


class CliTests(unittest.TestCase):
    def test_coacd_overwrite_removes_stale_parts(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            output = Path(value) / "parts"
            output.mkdir()
            stale = output / "part_999.obj"
            stale.touch()
            part = mock.Mock()
            part.export.side_effect = lambda path: Path(path).touch()

            with (
                mock.patch(
                    "sim_asset_tools.mesh.io.load_mesh", return_value=mock.Mock()
                ),
                mock.patch(
                    "sim_asset_tools.mesh.coacd.decompose_mesh", return_value=[part]
                ),
            ):
                result = cli.main(
                    ["mesh", "coacd", "in.obj", str(output), "--overwrite"]
                )

            self.assertEqual(result, 0)
            self.assertFalse(stale.exists())
            self.assertTrue((output / "part_000.obj").is_file())

    def test_acvd_forwards_structured_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            output = Path(value) / "out.ply"
            with mock.patch("sim_asset_tools.mesh.acvd.acvd_remesh") as remesh:
                result = cli.main(
                    [
                        "mesh",
                        "acvd",
                        "in.obj",
                        str(output),
                        "--vertices",
                        "42",
                    ]
                )

            self.assertEqual(result, 0)
            remesh.assert_called_once()
            self.assertEqual(remesh.call_args.kwargs["vertices"], 42)


if __name__ == "__main__":
    unittest.main()
