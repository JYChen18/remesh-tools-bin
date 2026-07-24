from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sim_asset_tools.formats.manifest import (
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

    def test_directory_fingerprint_rejects_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            directory = root / "artifacts"
            directory.mkdir()
            target = root / "outside.obj"
            target.write_text("outside\n", encoding="utf-8")
            link = directory / "part.obj"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symbolic links are unavailable: {exc}")

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                sha256_directory(directory)

    def test_round_trip_verifies_artifacts_and_detects_changes(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            artifact = root / "meshes" / "part.obj"
            artifact.parent.mkdir()
            artifact.write_text("mesh\n", encoding="utf-8")
            manifest_path = root / "asset.json"
            manifest = {
                "schema": "test-consumer/artifact/v7",
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

    def test_rejects_non_posix_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            with self.assertRaisesRegex(ValueError, "POSIX separators"):
                resolve_artifact(Path(value), r"..\outside.obj")

            for path in ("C:/outside.obj", "C:outside.obj"):
                with (
                    self.subTest(path=path),
                    self.assertRaisesRegex(ValueError, "relative and contained"),
                ):
                    resolve_artifact(Path(value), path)

    def test_manifest_io_is_schema_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "asset.json"
            manifest = {"consumer": "owns this format", "schema": "other/v99"}

            write_manifest(path, manifest)

            self.assertEqual(load_manifest(path), manifest)

    def test_write_rejects_non_object_json(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "asset.json"

            with self.assertRaisesRegex(TypeError, "must be a JSON object"):
                write_manifest(path, [])  # type: ignore[arg-type]

    def test_rejects_nonfinite_json_on_read_and_write(self) -> None:
        with tempfile.TemporaryDirectory() as value:
            path = Path(value) / "asset.json"

            for constant in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(read=constant):
                    path.write_text(f'{{"value": {constant}}}', encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "non-finite JSON number"):
                        load_manifest(path)

            path.unlink()
            with self.assertRaisesRegex(ValueError, "Out of range float values"):
                write_manifest(path, {"value": float("nan")})
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
