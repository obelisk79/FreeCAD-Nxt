"""Section plane aiming: three points, and turning to face the camera.

Run with: python3 tests/test_section_aim.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fakes  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.tools import section_aim  # noqa: E402


class V:
    """Enough of App.Vector for plane maths."""

    def __init__(self, x: float = 0, y: float = 0, z: float = 0) -> None:
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __add__(self, o: "V") -> "V":
        return V(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o: "V") -> "V":
        return V(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, k: float) -> "V":
        return V(self.x * k, self.y * k, self.z * k)

    def dot(self, o: "V") -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o: "V") -> "V":
        return V(self.y * o.z - self.z * o.y, self.z * o.x - self.x * o.z,
                 self.x * o.y - self.y * o.x)

    @property
    def Length(self) -> float:  # noqa: N802 - App.Vector's name
        return float(self.dot(self) ** 0.5)

    def normalize(self) -> "V":
        n = self.Length
        self.x, self.y, self.z = self.x / n, self.y / n, self.z / n
        return self

    def tuple(self) -> tuple[float, float, float]:
        return (round(self.x, 9), round(self.y, 9), round(self.z, 9))


class AimTests(unittest.TestCase):

    def test_three_points_give_their_plane(self) -> None:
        plane = section_aim.plane_through([V(0, 0, 5), V(1, 0, 5),
                                           V(0, 1, 5)])
        assert plane is not None
        normal, point = plane
        self.assertEqual(abs(normal.z), 1.0)
        self.assertAlmostEqual(point.z, 5.0)

    def test_points_in_a_line_give_none(self) -> None:
        self.assertIsNone(section_aim.plane_through(
            [V(0, 0, 0), V(1, 1, 1), V(2, 2, 2)]))
        self.assertIsNone(section_aim.plane_through([V(), V(1, 0, 0)]))

    def test_the_normal_is_turned_away_from_the_camera(self) -> None:
        look = V(0, 0, -1)
        self.assertEqual(section_aim.facing(V(0, 0, 1), look).tuple(),
                         (0.0, 0.0, -1.0))
        self.assertEqual(section_aim.facing(V(0, 0, -1), look).tuple(),
                         (0.0, 0.0, -1.0))


class NullShape:
    """An empty sketch's shape: asking its type raises, as FreeCAD's."""

    def isNull(self) -> bool:  # noqa: N802 - Part's name
        return True

    @property
    def ShapeType(self) -> str:  # noqa: N802 - Part's name
        raise RuntimeError("cannot determine type of null shape")


class EmptySketch:
    TypeId = "Sketcher::SketchObject"

    def getSubObject(self, *_args: object, **_kw: object) -> object:  # noqa: N802
        return NullShape()


class SelectionTests(unittest.TestCase):

    def test_an_empty_sketch_selected_gives_no_plane(self) -> None:
        import types
        picked = types.SimpleNamespace(Object=EmptySketch(),
                                       SubElementNames=())
        saved = getattr(Gui, "Selection", None)
        Gui.Selection = types.SimpleNamespace(
            getSelectionEx=lambda *_args: [picked])
        try:
            self.assertIsNone(section_aim.from_selection())
        finally:
            Gui.Selection = saved


if __name__ == "__main__":
    unittest.main(verbosity=2)
