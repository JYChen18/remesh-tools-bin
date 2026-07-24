from __future__ import annotations

import copy
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

        from sim_asset_tools.formats.manifest import (
            sha256_directory,
            sha256_file,
            sha256_json,
        )
        from sim_asset_tools.formats.object_manifest import OBJECT_MANIFEST_SCHEMA
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
            pristine_manifest = copy.deepcopy(manifest)
            collision_contents = {
                path.name: path.read_bytes()
                for path in (result.output_directory / "collision").glob("*.obj")
            }
            self.assertEqual(manifest["schema"], OBJECT_MANIFEST_SCHEMA)
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

            def publish_rehashed(value: dict[str, object]) -> None:
                hashes = value["sha256"]
                assert isinstance(hashes, dict)
                hashes["collision"] = sha256_directory(
                    result.output_directory / "collision"
                )
                for name in ("schema", "geometry", "surfaces", "recipe"):
                    hashes[name] = sha256_json(value[name])
                for relative in tuple(hashes):
                    if relative in {
                        "schema",
                        "geometry",
                        "surfaces",
                        "recipe",
                        "collision",
                        "sha256",
                    }:
                        continue
                    hashes[relative] = sha256_file(result.output_directory / relative)
                hashes["sha256"] = sha256_json(
                    {
                        name: digest
                        for name, digest in hashes.items()
                        if name != "sha256"
                    }
                )
                result.manifest_path.write_text(
                    json.dumps(value),
                    encoding="utf-8",
                )

            manifest = copy.deepcopy(pristine_manifest)
            manifest["geometry"] = []
            publish_rehashed(manifest)
            self.assertIn(
                "manifest geometry must be an object",
                check_object(result.output_directory),
            )

            manifest = copy.deepcopy(pristine_manifest)
            visual_path = result.output_directory / "visual.obj"
            visual_bytes = visual_path.read_bytes()
            visual_path.write_text("not an OBJ mesh\n", encoding="utf-8")
            publish_rehashed(manifest)
            self.assertTrue(
                any(
                    error.startswith("visual could not be loaded:")
                    for error in check_object(result.output_directory)
                )
            )

            visual_path.write_bytes(visual_bytes)
            manifest = copy.deepcopy(pristine_manifest)
            for collision_path in (result.output_directory / "collision").glob("*.obj"):
                collision_path.unlink()
            publish_rehashed(manifest)
            self.assertIn(
                "collision directory must contain at least one OBJ mesh",
                check_object(result.output_directory),
            )

            for name, content in collision_contents.items():
                (result.output_directory / "collision" / name).write_bytes(content)
            (result.output_directory / "collision" / "notes.txt").write_text(
                "unexpected\n",
                encoding="utf-8",
            )
            manifest = copy.deepcopy(pristine_manifest)
            publish_rehashed(manifest)
            self.assertIn(
                "unexpected collision artifact: collision/notes.txt",
                check_object(result.output_directory),
            )

            (result.output_directory / "collision" / "notes.txt").unlink()
            result.manifest_path.write_text(
                json.dumps(pristine_manifest),
                encoding="utf-8",
            )
            collision_link = result.output_directory / "collision" / "outside.obj"
            try:
                collision_link.symlink_to(source)
            except (NotImplementedError, OSError):
                pass
            else:
                errors = check_object(result.output_directory)
                self.assertTrue(
                    any("symbolic link" in error for error in errors),
                    errors,
                )
                collision_link.unlink()

    def test_check_object_reports_malformed_records(self) -> None:
        from sim_asset_tools import cli
        from sim_asset_tools.workflows import check_object

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "asset.json").write_text(
                json.dumps(
                    {
                        "schema": "sim-asset/object/v1",
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
            self.assertIn("manifest geometry must be an object", errors)
            self.assertEqual(cli.main(["check", "object", str(root)]), 1)

    def test_check_object_rejects_unknown_schema(self) -> None:
        from sim_asset_tools.workflows import check_object

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "asset.json").write_text(
                json.dumps({"schema": "sim-asset/object/v2"}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Regenerate the object bundle"):
                check_object(root)


if __name__ == "__main__":
    unittest.main()
