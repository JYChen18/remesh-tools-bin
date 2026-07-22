from __future__ import annotations

import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec("numpy"), "requires numpy")
class MeshTests(unittest.TestCase):
    def test_validation_checks_orientation_of_every_component(self) -> None:
        import numpy as np

        from sim_asset_tools.mesh import validate_mesh

        class Mesh:
            is_watertight = True
            is_winding_consistent = True

            def __init__(self, *, reverse_second: bool) -> None:
                tetrahedron = np.array(
                    [
                        [0.0, 0.0, 0.0],
                        [1.0, 0.0, 0.0],
                        [0.0, 1.0, 0.0],
                        [0.0, 0.0, 1.0],
                    ]
                )
                faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
                second_faces = faces[:, ::-1] if reverse_second else faces
                self.vertices = np.vstack((tetrahedron, tetrahedron + [2.0, 0.0, 0.0]))
                self.faces = np.vstack((faces, second_faces + 4))
                self.area_faces = np.ones(len(self.faces))

        self.assertEqual(validate_mesh(Mesh(reverse_second=False), watertight=True), [])
        self.assertEqual(
            validate_mesh(Mesh(reverse_second=True), watertight=True),
            ["mesh normals must face outward"],
        )


if __name__ == "__main__":
    unittest.main()
