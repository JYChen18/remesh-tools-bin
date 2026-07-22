from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from sim_asset_tools import cli, legacy


class SimAssetsCliTest(unittest.TestCase):
    def test_mesh_coacd_overwrite_removes_stale_parts(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            output = Path(value) / "parts"
            output.mkdir()
            stale = output / "part_999.obj"
            stale.touch()
            part = mock.Mock()
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
            part.export.assert_called_once_with(output / "part_000.obj")

    def test_mesh_acvd_maps_structured_arguments(self) -> None:
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

    def test_prepare_body_surfaces_has_no_backend_profile_argument(self) -> None:
        parser = cli._build_parser()
        args = parser.parse_args(
            ["prepare", "body-surfaces", "scene.xml", "--output", "derived"]
        )

        self.assertEqual(args.prepare_command, "body-surfaces")

    def test_legacy_command_warns_and_forwards(self) -> None:
        with mock.patch.object(legacy, "_legacy_main", return_value=0) as run:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = legacy.main(
                    ["acvd", "input.obj", "output.ply", "--vertices", "4"]
                )

        self.assertEqual(result, 0)
        run.assert_called_once()
        self.assertIn("deprecated", str(caught[0].message))


if __name__ == "__main__":
    unittest.main()
