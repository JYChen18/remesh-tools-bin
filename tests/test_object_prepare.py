from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HAS_OBJECT_DEPS = all(
    importlib.util.find_spec(name) is not None for name in ("numpy", "trimesh")
)


@unittest.skipUnless(_HAS_OBJECT_DEPS, "requires sim-asset-tools object dependencies")
class ObjectPrepareTest(unittest.TestCase):
    def test_rejects_empty_output_formats(self) -> None:
        from sim_asset_tools.workflows import prepare_object

        with self.assertRaisesRegex(ValueError, "At least one"):
            prepare_object("missing.obj", "unused", formats=())

    def test_batch_rejects_inputs_with_the_same_stem(self) -> None:
        from sim_asset_tools.workflows import prepare_objects

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            (root / "cup.obj").touch()
            (root / "cup.stl").touch()

            with self.assertRaisesRegex(ValueError, "share output directories"):
                prepare_objects(root, root / "output")

    def test_prepares_versioned_bundle_without_backend_specific_defaults(self) -> None:
        import trimesh

        from sim_asset_tools.mesh.io import load_mesh
        from sim_asset_tools.workflows import check_object, prepare_object
        from sim_asset_tools.workflows import object as object_prepare

        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            source = root / "box.obj"
            trimesh.creation.box().export(source)

            def copy_source(input_path, output_path, *_args):
                load_mesh(input_path).export(output_path)
                return output_path

            with (
                mock.patch.object(
                    object_prepare, "prepare_surface", side_effect=copy_source
                ),
                mock.patch.object(
                    object_prepare,
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


if __name__ == "__main__":
    unittest.main()
