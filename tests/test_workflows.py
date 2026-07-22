from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HAS_MESH_DEPS = all(
    importlib.util.find_spec(name) is not None for name in ("numpy", "trimesh")
)
_HAS_MODEL_DEPS = _HAS_MESH_DEPS and importlib.util.find_spec("mujoco") is not None


@unittest.skipUnless(_HAS_MESH_DEPS, "requires mesh dependencies")
class ObjectWorkflowTests(unittest.TestCase):
    def test_batch_rejects_inputs_that_share_an_output_directory(self) -> None:
        from sim_asset_tools.workflows import prepare_objects

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "cup.obj").touch()
            (root / "cup.stl").touch()

            with self.assertRaisesRegex(ValueError, "share output directories"):
                prepare_objects(root, root / "output")

    def test_prepare_object_writes_a_valid_versioned_bundle(self) -> None:
        import trimesh

        from sim_asset_tools.mesh import load_mesh
        from sim_asset_tools.workflows import check_object, prepare_object
        from sim_asset_tools.workflows import object as object_workflow

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            source = root / "box.obj"
            trimesh.creation.box().export(source)

            def copy_source(input_path, output_path, *_args):
                load_mesh(input_path).export(output_path)
                return output_path

            with (
                mock.patch.object(
                    object_workflow, "prepare_surface", side_effect=copy_source
                ),
                mock.patch.object(
                    object_workflow,
                    "decompose_mesh",
                    side_effect=lambda mesh, **_kwargs: [mesh.copy()],
                ),
            ):
                result = prepare_object(source, root / "asset")

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "sim-asset/v1")
            self.assertEqual(manifest["kind"], "object")
            self.assertGreater(manifest["mass_properties"]["volume"], 0)
            self.assertTrue(result.mjcf_path.is_file())
            self.assertTrue(result.urdf_path.is_file())
            self.assertEqual(check_object(result.output_directory), [])


@unittest.skipUnless(_HAS_MODEL_DEPS, "requires sim-asset-tools[mujoco]")
class BodySurfaceWorkflowTests(unittest.TestCase):
    def test_manifest_maps_model_body_names_to_portable_paths(self) -> None:
        from sim_asset_tools.mesh import load_mesh
        from sim_asset_tools.workflows import check_body_surfaces, prepare_body_surfaces
        from sim_asset_tools.workflows import body_surfaces as body_surface_workflow

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
                body_surface_workflow, "prepare_surface", side_effect=copy_source
            ):
                manifest_path = prepare_body_surfaces(model_path, root / "derived")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["contract"], "body-surfaces/v1")
            self.assertEqual(set(manifest["bodies"]), {"hand/forearm"})
            mesh_path = manifest["bodies"]["hand/forearm"]["mesh"]["path"]
            self.assertNotIn("hand/forearm", mesh_path)
            self.assertTrue((manifest_path.parent / mesh_path).is_file())
            self.assertEqual(check_body_surfaces(model_path, manifest_path), [])


if __name__ == "__main__":
    unittest.main()
