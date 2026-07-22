from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from native.tools import patch_openvdb


class OpenVdbPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.openvdb_dir = Path(self.temporary_directory.name) / "openvdb"
        (self.openvdb_dir / "tree").mkdir(parents=True)
        (self.openvdb_dir / "tools").mkdir()

    def write_legacy_headers(self) -> None:
        (self.openvdb_dir / "tree" / "NodeManager.h").write_text(
            "\n".join(["OpT::template eval(mNodeOp, it);"] * 3),
            encoding="utf-8",
        )
        (self.openvdb_dir / "tools" / "PointIndexGrid.h").write_text(
            "BaseLeaf::merge<Policy>(rhs);",
            encoding="utf-8",
        )

    def test_patches_legacy_clang_template_syntax(self) -> None:
        self.write_legacy_headers()

        patch_openvdb.patch_legacy_headers(self.openvdb_dir)

        node_manager = (self.openvdb_dir / "tree" / "NodeManager.h").read_text(
            encoding="utf-8"
        )
        point_index_grid = (self.openvdb_dir / "tools" / "PointIndexGrid.h").read_text(
            encoding="utf-8"
        )
        self.assertEqual(node_manager.count("OpT::eval"), 3)
        self.assertNotIn("OpT::template eval", node_manager)
        self.assertIn("BaseLeaf::template merge<Policy>(rhs);", point_index_grid)

    def test_header_patch_is_idempotent(self) -> None:
        self.write_legacy_headers()

        patch_openvdb.patch_legacy_headers(self.openvdb_dir)
        patch_openvdb.patch_legacy_headers(self.openvdb_dir)

    def test_rejects_unexpected_legacy_header_shape(self) -> None:
        self.write_legacy_headers()
        (self.openvdb_dir / "tree" / "NodeManager.h").write_text(
            "OpT::template eval(mNodeOp, it);",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RuntimeError, "Expected 3 occurrence"):
            patch_openvdb.patch_legacy_headers(self.openvdb_dir)


if __name__ == "__main__":
    unittest.main()
