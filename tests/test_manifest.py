from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sim_asset_tools.manifest import (
    SCHEMA_VERSION,
    load_manifest,
    resolve_artifact,
    sha256_file,
    verify_file_records,
    write_manifest,
)


class ManifestTest(unittest.TestCase):
    def test_round_trip_and_file_verification(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            artifact = root / "meshes" / "part.obj"
            artifact.parent.mkdir()
            artifact.write_text("mesh\n", encoding="utf-8")
            manifest_path = root / "asset.json"
            manifest = {
                "schema": SCHEMA_VERSION,
                "kind": "object",
                "source": {"path": "meshes/part.obj", "sha256": sha256_file(artifact)},
            }

            write_manifest(manifest_path, manifest)

            self.assertEqual(load_manifest(root), manifest)
            self.assertEqual(verify_file_records(root, [manifest["source"]]), [])
            self.assertFalse(any(root.glob(".asset.json.*.tmp")))

    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "relative and contained"):
                resolve_artifact(Path(value), "../outside.obj")

    def test_rejects_unknown_schema(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "asset.json"
            path.write_text(json.dumps({"schema": "other/v1", "kind": "object"}))

            with self.assertRaisesRegex(
                ValueError, "Unsupported asset manifest schema"
            ):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
