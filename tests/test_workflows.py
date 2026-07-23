from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HAS_MESH_DEPS = all(
    importlib.util.find_spec(name) is not None
    for name in ("coacd", "numpy", "trimesh", "vtkmodules")
)
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

    def test_prepare_object_writes_a_valid_versioned_bundle(self) -> None:
        import trimesh

        from sim_asset_tools.formats.manifest import sha256_json
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
            self.assertEqual(manifest["schema"], "sim-asset/v2")
            self.assertNotIn("kind", manifest)
            self.assertEqual(manifest["surfaces"], {"object": "visual.obj"})
            geometry = manifest["geometry"]
            self.assertGreater(geometry["volume"], 0)
            self.assertEqual(len(geometry["center_of_mass"]), 3)
            self.assertEqual(len(geometry["inertia_per_unit_mass"]), 3)
            self.assertEqual(geometry["source_aabb_extents"], [1.0, 1.0, 1.0])
            self.assertEqual(len(geometry["obb_center"]), 3)
            self.assertEqual(len(geometry["obb_axes"]), 3)
            self.assertEqual(len(geometry["obb_extents"]), 3)
            self.assertNotIn("source_aabb_half_diagonal", geometry)
            self.assertFalse(
                any(name.startswith(("visual_", "collision_")) for name in geometry)
            )
            self.assertEqual(
                set(manifest["sha256"]) & {"source.obj", "visual.obj"},
                {"source.obj", "visual.obj"},
            )
            self.assertTrue(
                {"schema", "geometry", "surfaces", "recipe", "sha256"}
                <= manifest["sha256"].keys()
            )
            other_hashes = {
                name: digest
                for name, digest in manifest["sha256"].items()
                if name != "sha256"
            }
            self.assertEqual(manifest["sha256"]["sha256"], sha256_json(other_hashes))
            self.assertIn("model.xml", manifest["sha256"])
            self.assertIn("model.urdf", manifest["sha256"])
            self.assertIn("collision", manifest["sha256"])
            self.assertFalse(
                any(path.startswith("collision/") for path in manifest["sha256"])
            )
            self.assertTrue(result.mjcf_path.is_file())
            self.assertTrue(result.urdf_path.is_file())
            self.assertEqual(result.mjcf_path.parent, result.output_directory)
            self.assertEqual(result.urdf_path.parent, result.output_directory)
            self.assertEqual(check_object(result.output_directory), [])

            collision_path = next((result.output_directory / "collision").glob("*.obj"))
            original_collision = collision_path.read_bytes()
            collision_path.write_bytes(original_collision + b"\n")
            self.assertIn(
                "manifest collision fingerprint does not match",
                check_object(result.output_directory),
            )
            collision_path.write_bytes(original_collision)
            self.assertEqual(check_object(result.output_directory), [])

            manifest["surfaces"]["object"] = "source.obj"
            result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertIn(
                "manifest surfaces fingerprint does not match",
                check_object(result.output_directory),
            )

            manifest["surfaces"]["object"] = "visual.obj"
            manifest["geometry"]["volume"] *= 2.0
            result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertIn(
                "manifest geometry fingerprint does not match",
                check_object(result.output_directory),
            )

            manifest["sha256"]["geometry"] = sha256_json(manifest["geometry"])
            result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertIn(
                "manifest sha256 fingerprint does not match",
                check_object(result.output_directory),
            )

    def test_check_object_reports_malformed_records(self) -> None:
        from sim_asset_tools import cli
        from sim_asset_tools.workflows import check_object

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "asset.json").write_text(
                json.dumps(
                    {
                        "schema": "sim-asset/v2",
                        "geometry": "invalid",
                        "sha256": {},
                        "recipe": {},
                        "surfaces": "invalid",
                    }
                ),
                encoding="utf-8",
            )

            errors = check_object(root)

            self.assertIn("manifest sha256 is missing the geometry fingerprint", errors)
            self.assertIn("manifest sha256 is missing the sha256 fingerprint", errors)
            self.assertEqual(cli.main(["check", "object", str(root)]), 1)


@unittest.skipUnless(_HAS_MODEL_DEPS, "requires MuJoCo and mesh dependencies")
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
                  <compiler meshdir="mesh-assets"/>
                  <worldbody>
                    <body name="hand/forearm">
                      <freejoint/>
                      <geom type="box" size="0.1 0.1 0.1"/>
                      <geom type="box" size="0.1 0.1 0.1" pos="0.1 0 0"/>
                    </body>
                    <body name="object">
                      <freejoint/>
                      <geom type="ellipsoid" size="0.1 0.2 0.3"/>
                    </body>
                    <geom name="floor" type="plane" size="1 1 0.1"/>
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
                manifest_path = prepare_body_surfaces(model_path)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest_path,
                root / "mesh-assets" / "surfaces" / "asset.json",
            )
            self.assertEqual(
                set(manifest),
                {"schema", "surfaces", "surface_sets", "recipe", "sha256"},
            )
            self.assertEqual(manifest["schema"], "sim-asset/v2")
            self.assertEqual(
                manifest["surfaces"],
                {"hand/forearm": "hand%2Fforearm.obj"},
            )
            self.assertEqual(
                manifest["surface_sets"]["scene.xml"]["bodies"],
                ["hand/forearm"],
            )
            self.assertRegex(
                manifest["surface_sets"]["scene.xml"]["source_geometry_sha256"],
                r"^[0-9a-f]{64}$",
            )
            self.assertNotIn("object", manifest["surfaces"])
            mesh_path = manifest["surfaces"]["hand/forearm"]
            self.assertNotIn("/", mesh_path)
            self.assertTrue((manifest_path.parent / mesh_path).is_file())
            self.assertIn(mesh_path, manifest["sha256"])
            self.assertTrue(
                {"schema", "surfaces", "recipe", "sha256"} <= manifest["sha256"].keys()
            )
            self.assertNotIn("surface_sets", manifest["sha256"])
            self.assertEqual(check_body_surfaces(model_path), [])

            legacy_manifest = dict(manifest)
            legacy_manifest.pop("surface_sets")
            manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
            with mock.patch.object(
                body_surface_workflow,
                "prepare_surface",
                side_effect=AssertionError("legacy surface was regenerated"),
            ):
                self.assertEqual(prepare_body_surfaces(model_path), manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("scene.xml", manifest["surface_sets"])

            surface_path = manifest_path.parent / mesh_path
            original_surface = surface_path.read_bytes()
            surface_path.write_bytes(original_surface + b"\n")
            self.assertIn(
                f"artifact hash does not match: {mesh_path}",
                check_body_surfaces(model_path),
            )
            surface_path.write_bytes(original_surface)

            physics_xml = model_path.read_text(encoding="utf-8").replace(
                '<geom type="box" size="0.1 0.1 0.1"/>',
                '<geom type="box" size="0.1 0.1 0.1" solref="0.01 1"/>',
                1,
            )
            model_path.write_text(physics_xml, encoding="utf-8")
            self.assertEqual(check_body_surfaces(model_path), [])
            with mock.patch.object(
                body_surface_workflow,
                "prepare_surface",
                side_effect=AssertionError("physics-only change regenerated surfaces"),
            ):
                self.assertEqual(prepare_body_surfaces(model_path), manifest_path)

            model_path.write_text(
                physics_xml.replace(
                    'size="0.1 0.1 0.1"',
                    'size="0.2 0.2 0.2"',
                ),
                encoding="utf-8",
            )
            self.assertIn(
                "surface set source geometry fingerprint does not match: 'scene.xml'",
                check_body_surfaces(model_path),
            )
            with self.assertRaisesRegex(
                FileExistsError,
                "pass overwrite=True to update it",
            ):
                prepare_body_surfaces(model_path)

            with self.assertRaisesRegex(
                ValueError,
                "not named multi-geom collision bodies: object",
            ):
                prepare_body_surfaces(
                    model_path,
                    root / "selected",
                    bodies=["object"],
                )

    def test_models_merge_into_one_provider_and_overwrite_only_their_set(self) -> None:
        from sim_asset_tools.mesh import load_mesh
        from sim_asset_tools.workflows import (
            BodySurfaceRecipe,
            check_body_surfaces,
            prepare_body_surfaces,
        )
        from sim_asset_tools.workflows import body_surfaces as body_surface_workflow

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            output_directory = root / "mesh-assets" / "surfaces"
            right_path = root / "scene_right.xml"
            left_path = root / "scene_left.xml"

            def write_model(path: Path, body_name: str, size: str = ".1") -> None:
                path.write_text(
                    f"""
                    <mujoco>
                      <compiler meshdir="mesh-assets"/>
                      <worldbody>
                        <body name="{body_name}">
                          <geom type="box" size="{size} {size} {size}"/>
                          <geom type="box" size="{size} {size} {size}"
                            pos="{size} 0 0"/>
                        </body>
                      </worldbody>
                    </mujoco>
                    """,
                    encoding="utf-8",
                )

            write_model(right_path, "rh_hand")
            write_model(left_path, "lh_hand")

            def copy_source(source, output, *_args):
                load_mesh(source).export(output)
                return output

            with mock.patch.object(
                body_surface_workflow,
                "prepare_surface",
                side_effect=copy_source,
            ):
                manifest_path = prepare_body_surfaces(right_path)
                self.assertEqual(prepare_body_surfaces(left_path), manifest_path)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["surfaces"],
                {
                    "lh_hand": "lh_hand.obj",
                    "rh_hand": "rh_hand.obj",
                },
            )
            self.assertEqual(
                set(manifest["surface_sets"]),
                {"scene_left.xml", "scene_right.xml"},
            )
            self.assertEqual(check_body_surfaces(right_path), [])
            self.assertEqual(check_body_surfaces(left_path), [])

            with mock.patch.object(
                body_surface_workflow,
                "prepare_surface",
                side_effect=AssertionError("unchanged set was regenerated"),
            ):
                self.assertEqual(prepare_body_surfaces(right_path), manifest_path)

            left_bytes = (output_directory / "lh_hand.obj").read_bytes()
            write_model(right_path, "rh_hand", ".2")
            self.assertTrue(
                any(
                    "surface set source geometry fingerprint does not match" in error
                    for error in check_body_surfaces(right_path)
                )
            )
            self.assertEqual(check_body_surfaces(left_path), [])

            with self.assertRaisesRegex(
                FileExistsError,
                "pass overwrite=True to update it",
            ):
                prepare_body_surfaces(right_path)

            with mock.patch.object(
                body_surface_workflow,
                "prepare_surface",
                side_effect=copy_source,
            ):
                prepare_body_surfaces(right_path, overwrite=True)

            self.assertEqual(
                (output_directory / "lh_hand.obj").read_bytes(),
                left_bytes,
            )
            self.assertEqual(check_body_surfaces(right_path), [])
            self.assertEqual(check_body_surfaces(left_path), [])

            with self.assertRaisesRegex(
                ValueError,
                "cannot mix preparation recipes",
            ):
                prepare_body_surfaces(
                    right_path,
                    recipe=BodySurfaceRecipe(target_vertices=64),
                    overwrite=True,
                )

    def test_shared_provider_rejects_different_geometry_for_the_same_body(self) -> None:
        from sim_asset_tools.mesh import load_mesh
        from sim_asset_tools.workflows import check_body_surfaces, prepare_body_surfaces
        from sim_asset_tools.workflows import body_surfaces as body_surface_workflow

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            output_directory = root / "surfaces"
            first_path = root / "first.xml"
            second_path = root / "second.xml"
            first_path.write_text(
                """
                <mujoco>
                  <worldbody>
                    <body name="hand">
                      <geom type="box" size=".1 .1 .1"/>
                      <geom type="box" size=".1 .1 .1"/>
                    </body>
                  </worldbody>
                </mujoco>
                """,
                encoding="utf-8",
            )
            second_path.write_text(
                first_path.read_text(encoding="utf-8").replace(
                    'size=".1 .1 .1"',
                    'size=".2 .2 .2"',
                ),
                encoding="utf-8",
            )

            def copy_source(source, output, *_args):
                load_mesh(source).export(output)
                return output

            with mock.patch.object(
                body_surface_workflow,
                "prepare_surface",
                side_effect=copy_source,
            ):
                manifest_path = prepare_body_surfaces(first_path, output_directory)
                with self.assertRaisesRegex(
                    ValueError,
                    "Body-surface conflict for 'hand'",
                ):
                    prepare_body_surfaces(second_path, output_directory)

            self.assertEqual(check_body_surfaces(first_path, manifest_path), [])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["surface_sets"]), {"first.xml"})

    def test_body_surface_filenames_report_portability_conflicts(self) -> None:
        from sim_asset_tools.workflows import prepare_body_surfaces

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            model_path = root / "scene.xml"
            model_path.write_text(
                """
                <mujoco>
                  <worldbody>
                    <body name="Body">
                      <geom type="box" size=".1 .1 .1"/>
                      <geom type="box" size=".1 .1 .1"/>
                    </body>
                    <body name="body">
                      <geom type="box" size=".1 .1 .1"/>
                      <geom type="box" size=".1 .1 .1"/>
                    </body>
                  </worldbody>
                </mujoco>
                """,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "conflicting surface filenames",
            ):
                prepare_body_surfaces(model_path, root / "surfaces")

    def test_mixed_plane_or_heightfield_body_is_rejected(self) -> None:
        from sim_asset_tools.workflows import prepare_body_surfaces

        cases = {
            "plane": (
                "",
                '<geom name="terrain" type="plane" size="1 1 .1"/>',
            ),
            "heightfield": (
                """
                <asset>
                  <hfield name="terrain_data" nrow="2" ncol="2"
                    size="1 1 1 .1" elevation="0 0 0 0"/>
                </asset>
                """,
                '<geom name="terrain" type="hfield" hfield="terrain_data"/>',
            ),
        }
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            for name, (asset, procedural_geom) in cases.items():
                with self.subTest(name=name):
                    model_path = root / f"{name}.xml"
                    model_path.write_text(
                        f"""
                        <mujoco>
                          {asset}
                          <worldbody>
                            {procedural_geom}
                            <geom name="obstacle" type="box" size=".1 .2 .3"/>
                          </worldbody>
                        </mujoco>
                        """,
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        ValueError,
                        "plane or heightfield must be the only collidable geom",
                    ):
                        prepare_body_surfaces(model_path, root / f"{name}-surfaces")

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
                    <body name="one">
                      <freejoint/>
                      <geom type="box" size=".1 .1 .1"/>
                      <geom type="box" size=".1 .1 .1"/>
                    </body>
                    <body name="two">
                      <freejoint/>
                      <geom type="box" size=".1 .1 .1"/>
                      <geom type="box" size=".1 .1 .1"/>
                    </body>
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

            self.assertEqual(len(list(output_directory.glob("*.obj"))), 1)


if __name__ == "__main__":
    unittest.main()
