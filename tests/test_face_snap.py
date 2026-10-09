"""Snapping a Pad or Pocket length to a parallel face: the arithmetic.

Run with: python3 tests/test_face_snap.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.modules.setdefault("FreeCAD", types.ModuleType("FreeCAD"))
sys.modules.setdefault("FreeCADGui", types.ModuleType("FreeCADGui"))

from freecad.nxt import face_snap  # noqa: E402
from freecad.nxt.face_snap import BACKWARD, FORWARD, Face  # noqa: E402


class V:
    """Just enough of App.Vector."""

    def __init__(self, x: float, y: float, z: float) -> None:
        self.v = (x, y, z)

    def dot(self, other: "V") -> float:
        return sum(a * b for a, b in zip(self.v, other.v))

    def __sub__(self, other: "V") -> "V":
        return V(*(a - b for a, b in zip(self.v, other.v)))


UP, SIDE = V(0, 0, 1), V(1, 0, 0)
ORIGIN = V(0, 0, 0)


def face(z: float, normal: V = UP, name: str = "F") -> tuple:
    return (normal, V(3, 4, z), "Base", name)


class FacingTests(unittest.TestCase):

    def test_only_faces_square_to_the_extrusion(self) -> None:
        found = face_snap.facing(
            [face(10, name="Top"), face(5, SIDE, "Wall")], ORIGIN, UP)
        self.assertEqual([f.element for f in found], ["Top"])

    def test_a_face_pointing_the_other_way_counts(self) -> None:
        found = face_snap.facing([face(4, V(0, 0, -1), "Under")],
                                 ORIGIN, UP)
        self.assertEqual([(f.distance, f.element) for f in found],
                         [(4, "Under")])

    def test_sorted_and_one_per_distance(self) -> None:
        found = face_snap.facing(
            [face(20, name="B"), face(-5, name="C"), face(10, name="A"),
             face(10, name="A2")], ORIGIN, UP)
        self.assertEqual([f.distance for f in found], [-5, 10, 20])


FACES = [Face(-5, "Base", "Face1"), Face(10, "Base", "Face2"),
         Face(20, "Base", "Face3")]


class CandidateTests(unittest.TestCase):

    def lengths(self, field: str, symmetric: bool = False) -> list:
        return [length for length, _f in
                face_snap.candidates(FACES, field, symmetric)]

    def test_the_first_length_reaches_forward(self) -> None:
        self.assertEqual(self.lengths(FORWARD), [10, 20])

    def test_the_second_backward(self) -> None:
        self.assertEqual(self.lengths(BACKWARD), [5])

    def test_a_symmetric_length_is_twice_either_side(self) -> None:
        self.assertEqual(self.lengths(FORWARD, True), [10, 20, 40])


class NearestTests(unittest.TestCase):

    LENGTHS = face_snap.candidates(FACES, FORWARD, False)

    def test_within_tolerance_it_snaps(self) -> None:
        hit = face_snap.nearest(10.4, self.LENGTHS, 0.5)
        self.assertEqual(hit[0], 10)

    def test_the_nearer_of_two(self) -> None:
        hit = face_snap.nearest(15.2, self.LENGTHS, 6)
        self.assertEqual(hit[0], 20)

    def test_outside_it_does_not(self) -> None:
        self.assertIsNone(face_snap.nearest(12, self.LENGTHS, 0.5))
        self.assertIsNone(face_snap.nearest(12, [], 0.5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
