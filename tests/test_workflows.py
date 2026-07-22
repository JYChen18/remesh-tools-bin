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
_HAS_COACD = importlib.util.find_spec("coacd") is not None
_HAS_MODEL_DEPS = _HAS_MESH_DEPS and importlib.util.find_spec("mujoco") is not None


@unittest.skipUnless(_HAS_MESH_DEPS, "requires mesh dependencies")
class ObjectWorkflowTests(unittest.TestCase):
    def test_overwrite_rejects_an_output_that_contains_the_input(self) -> None:
        from sim_asset_tools.workflows import prepare_object

        with tempfile.TemporaryDirectory() as value:
            output = Path(value)
            source = output / "mesh.obj"
            source.write_text(
                "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "must not contain"):
                prepare_object(source, output, overwrite=True)

            self.assertTrue(source.is_file())

    def test_batch_rejects_inputs_that_share_an_output_directory(self) -> None:
        from sim_asset_tools.workflows import prepare_objects

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "cup.obj").touch()
            (root / "cup.stl").touch()

            with self.assertRaisesRegex(ValueError, "share output directories"):
                prepare_objects(root, root / "output")

    @unittest.skipUnless(_HAS_COACD, "requires sim-asset-tools[coacd]")
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

            with mock.patch.object(
                object_workflow, "prepare_surface", side_effect=copy_source
            ):
                result = prepare_object(source, root / "asset")

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "sim-asset/v1")
            self.assertEqual(manifest["kind"], "object")
            self.assertGreater(manifest["mass_properties"]["volume"], 0)
            self.assertTrue(result.mjcf_path.is_file())
            self.assertTrue(result.urdf_path.is_file())
            self.assertEqual(check_object(result.output_directory), [])

    def test_check_object_reports_malformed_records(self) -> None:
        from sim_asset_tools import cli
        from sim_asset_tools.workflows import check_object

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "asset.json").write_text(
                json.dumps(
                    {
                        "schema": "sim-asset/v1",
                        "kind": "object",
                        "source": "invalid",
                        "visual": {"mesh": {}},
                        "collision": {"parts": []},
                        "models": {},
                    }
                ),
                encoding="utf-8",
            )

            errors = check_object(root)

            self.assertIn("manifest source must be an object", errors)
            self.assertIn("artifact record is missing a string path", errors)
            self.assertEqual(cli.main(["check", "object", str(root)]), 1)


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

    def test_overwrite_is_atomic_and_removes_stale_body_meshes(self) -> None:
        import trimesh

        from sim_asset_tools.mesh import load_mesh
        from sim_asset_tools.workflows import (
            BodySurfaceRecipe,
            check_body_surfaces,
            prepare_body_surfaces,
        )
        from sim_asset_tools.workflows import body_surfaces as body_surface_workflow

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            model_path = root / "scene.xml"
            model_path.write_text(
                """
                <mujoco>
                  <worldbody>
                    <body name="one"><freejoint/><geom type="box" size=".1 .1 .1"/></body>
                    <body name="two"><freejoint/><geom type="box" size=".1 .1 .1"/></body>
                  </worldbody>
                </mujoco>
                """,
                encoding="utf-8",
            )

            def copy_source(source, output, *_args):
                load_mesh(source).export(output)
                return output

            output_directory = root / "assets"
            with mock.patch.object(
                body_surface_workflow, "prepare_surface", side_effect=copy_source
            ):
                manifest_path = prepare_body_surfaces(model_path, output_directory)

            calls = 0

            def fail_second(_source, output, *_args):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("injected failure")
                trimesh.creation.icosphere().export(output)
                return output

            with (
                mock.patch.object(
                    body_surface_workflow, "prepare_surface", side_effect=fail_second
                ),
                self.assertRaisesRegex(RuntimeError, "injected failure"),
            ):
                prepare_body_surfaces(
                    model_path,
                    output_directory,
                    recipe=BodySurfaceRecipe(target_vertices=64),
                    overwrite=True,
                )

            self.assertEqual(check_body_surfaces(model_path, manifest_path), [])
            self.assertEqual(list(root.glob(".assets.staging-*")), [])

            with mock.patch.object(
                body_surface_workflow, "prepare_surface", side_effect=copy_source
            ):
                prepare_body_surfaces(
                    model_path,
                    output_directory,
                    bodies=["one"],
                    overwrite=True,
                )

            self.assertEqual(
                len(list((output_directory / "meshes").glob("*.obj"))), 1
            )


if __name__ == "__main__":
    unittest.main()
