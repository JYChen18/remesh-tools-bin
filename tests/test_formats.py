from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sim_asset_tools.formats.manifest import (
    OBJECT_SCHEMA_VERSION,
    load_manifest,
    resolve_artifact,
    sha256_directory,
    sha256_file,
    sha256_json,
    verify_sha256_map,
    write_manifest,
)


class ManifestFormatTests(unittest.TestCase):
    def test_json_fingerprint_is_independent_of_object_key_order(self) -> None:
        first = {"geometry": {"volume": 1.0, "center": [0, 0, 0]}, "schema": 1}
        second = {"schema": 1, "geometry": {"center": [0, 0, 0], "volume": 1.0}}

        self.assertEqual(sha256_json(first), sha256_json(second))
        self.assertNotEqual(sha256_json(first), sha256_json({"schema": 1}))

    def test_directory_fingerprint_covers_names_and_contents(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            first = root / "part_000.obj"
            second = root / "part_001.obj"
            first.write_text("first\n", encoding="utf-8")
            second.write_text("second\n", encoding="utf-8")
            original = sha256_directory(root)

            first.write_text("changed\n", encoding="utf-8")
            self.assertNotEqual(sha256_directory(root), original)
            first.write_text("first\n", encoding="utf-8")
            second.rename(root / "renamed.obj")
            self.assertNotEqual(sha256_directory(root), original)
            (root / "renamed.obj").rename(second)
            (root / "part_002.obj").write_text("third\n", encoding="utf-8")
            self.assertNotEqual(sha256_directory(root), original)

    def test_round_trip_verifies_artifacts_and_detects_changes(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            artifact = root / "meshes" / "part.obj"
            artifact.parent.mkdir()
            artifact.write_text("mesh\n", encoding="utf-8")
            manifest_path = root / "asset.json"
            manifest = {
                "schema": OBJECT_SCHEMA_VERSION,
                "sha256": {"meshes/part.obj": sha256_file(artifact)},
            }

            write_manifest(manifest_path, manifest)

            self.assertEqual(load_manifest(root), manifest)
            self.assertEqual(verify_sha256_map(root, manifest["sha256"]), [])

            artifact.write_text("changed\n", encoding="utf-8")
            self.assertEqual(
                verify_sha256_map(root, manifest["sha256"]),
                ["artifact hash does not match: meshes/part.obj"],
            )

    def test_rejects_artifact_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "relative and contained"):
                resolve_artifact(Path(value), "../outside.obj")

    def test_rejects_unknown_schema(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "asset.json"
            path.write_text(json.dumps({"schema": "other/v1"}))

            with self.assertRaisesRegex(
                ValueError, "Unsupported asset manifest schema"
            ):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
