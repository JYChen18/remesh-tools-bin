from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HAS_INTEROP_DEPS = all(
    importlib.util.find_spec(name) is not None
    for name in ("cqdc_warp", "mujoco", "trimesh", "warp")
)


@unittest.skipUnless(
    _HAS_INTEROP_DEPS, "requires CQDC Warp and sim-asset-tools[mujoco]"
)
class CQDCInteropTest(unittest.TestCase):
    def test_cqdc_consumes_generated_versioned_manifest(self) -> None:
        import cqdc_warp as cqdc
        import mujoco

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
                      <geom type="box" size="0.1 0.1 0.1" pos="0.3 0 0"/>
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

            model = mujoco.MjModel.from_xml_path(model_path.as_posix())
            converted = cqdc.put_model(
                model,
                rs1dist_assets=cqdc.RS1DistAssetConfig(manifest=manifest_path),
            )

            self.assertEqual(converted.cqdc.rs1dist_samples.pos.shape[0], model.nbody)


if __name__ == "__main__":
    unittest.main()
