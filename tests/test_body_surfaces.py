from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HAS_MODEL_DEPS = all(
    importlib.util.find_spec(name) is not None for name in ("mujoco", "trimesh")
)


@unittest.skipUnless(_HAS_MODEL_DEPS, "requires sim-asset-tools[mujoco]")
class BodySurfacesTest(unittest.TestCase):
    def test_prepare_uses_manifest_mapping_for_body_names_with_slashes(self) -> None:
        from sim_asset_tools.mesh.io import load_mesh
        from sim_asset_tools.workflows import body_surfaces

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            model_path = root / "scene.xml"
            model_path.write_text(
                """
                <mujoco>
                  <worldbody>
                    <body name="hand/forearm">
                      <freejoint/>
                      <geom type="box" size="0.1 0.1 0.1"/>
                      <geom type="box" size="0.1 0.1 0.1" pos="0.1 0 0"/>
                    </body>
                  </worldbody>
                </mujoco>
                """,
                encoding="utf-8",
            )

            def copy_source(source, output, *_args):
                load_mesh(source).export(output)
                return output

            with mock.patch.object(
                body_surfaces, "prepare_surface", side_effect=copy_source
            ):
                manifest_path = body_surfaces.prepare_body_surfaces(
                    model_path, root / "derived"
                )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["kind"], "body-surfaces")
            self.assertEqual(manifest["contract"], "body-surfaces/v1")
            record = manifest["bodies"]["hand/forearm"]
            self.assertNotIn("hand/forearm", record["mesh"]["path"])
            self.assertTrue((manifest_path.parent / record["mesh"]["path"]).is_file())
            self.assertEqual(
                body_surfaces.check_body_surfaces(model_path, manifest_path), []
            )


if __name__ == "__main__":
    unittest.main()
