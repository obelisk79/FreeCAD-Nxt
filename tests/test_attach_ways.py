"""The attachment panel's ways: FreeCAD's modes grouped and ordered.

Run with: python3 tests/test_attach_ways.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402

fakes.install(ParamGet=fakes.params({}))

from freecad.nxt.tools import attach_ways  # noqa: E402
from freecad.nxt.tools.attach_ways import DETACHED  # noqa: E402

ENGINE_3D = [DETACHED, "Translate", "ObjectXY", "ObjectXZ", "ObjectYZ",
             "FlatFace", "TangentPlane", "NormalToEdge", "FrenetNB",
             "FrenetTN", "FrenetTB", "Concentric", "SectionOfRevolution",
             "ThreePointsPlane", "ThreePointsNormal", "Folding",
             "InertialCS", "OZX", "OZY", "OXY", "OXZ", "OYZ", "OYX",
             "ParallelPlane", "MidPlane"]
ENGINE_LINE = [DETACHED, "ObjectX", "ObjectY", "ObjectZ", "TwoPointLine"]
ONE_FACE = {"allApplicableModes": ["FlatFace", "ObjectXY", "InertialCS"],
            "bestFitMode": "FlatFace", "message": "OK",
            "reachableModes": {"TangentPlane": [["Vertex"]],
                               "MidPlane": [["Plane"]]},
            "references_Types": ["Plane"], "nextRefTypeHint": ["Vertex"]}


def keys(rows: list[dict[str, object]]) -> list[object]:
    return [row["key"] for row in rows]


class WayTests(unittest.TestCase):
    def test_every_3d_mode_has_a_way(self) -> None:
        for mode in ENGINE_3D[1:]:
            self.assertIn(mode, attach_ways.way_of(mode).modes)
        ways = attach_ways.ways(ENGINE_3D, {}, DETACHED)
        self.assertEqual(len(ways), len(attach_ways.WAYS))

    def test_permutations_are_one_way(self) -> None:
        self.assertEqual(attach_ways.way_of("OXY").key, "align")
        self.assertEqual(attach_ways.way_of("FrenetTB").key, "path")
        self.assertEqual(len(attach_ways.variants(
            attach_ways.way_of("ObjectXZ"), ENGINE_3D)), 3)

    def test_fitting_ways_come_first(self) -> None:
        rows = attach_ways.ways(ENGINE_3D, ONE_FACE, "FlatFace")
        self.assertEqual(keys(rows)[:3], ["face", "object", "inertia"])
        self.assertTrue(rows[0]["current"])
        tangent = rows[keys(rows).index("tangent")]
        self.assertFalse(tangent["fits"])
        self.assertEqual(tangent["needs"], ["Vertex"])

    def test_with_picks_unreachable_ways_are_left_out(self) -> None:
        self.assertNotIn("folding", keys(
            attach_ways.ways(ENGINE_3D, ONE_FACE, "FlatFace")))

    def test_other_engines_keep_freecads_modes(self) -> None:
        rows = attach_ways.ways(ENGINE_LINE, {}, DETACHED)
        self.assertEqual(keys(rows), ENGINE_LINE[1:])
        self.assertEqual(attach_ways.way_of("TwoPointLine").label,
                         "TwoPointLine")


class ModeTests(unittest.TestCase):
    def test_current_kept_while_it_fits(self) -> None:
        self.assertEqual(attach_ways.mode_after_picks(
            "ObjectXY", "", ONE_FACE), "ObjectXY")

    def test_way_asked_for_wins_once_it_fits(self) -> None:
        both = dict(ONE_FACE, allApplicableModes=["FlatFace",
                                                  "TangentPlane"])
        self.assertEqual(attach_ways.mode_after_picks(
            "FlatFace", "TangentPlane", both), "TangentPlane")

    def test_best_fit_else_detached(self) -> None:
        self.assertEqual(attach_ways.mode_after_picks(
            DETACHED, "", ONE_FACE), "FlatFace")
        self.assertEqual(attach_ways.mode_after_picks(
            "FlatFace", "", {"message": "NoModesFit"}), DETACHED)

    def test_choosing_a_way_picks_a_fitting_variant(self) -> None:
        path = attach_ways.way_of("FrenetNB")
        self.assertEqual(attach_ways.mode_for_way(
            path, "FlatFace", ["FrenetTN"]), "FrenetTN")
        self.assertEqual(attach_ways.mode_for_way(
            path, "FrenetTB", ["FrenetTN"]), "FrenetTB")
        self.assertEqual(attach_ways.mode_for_way(
            path, "FlatFace", []), "FrenetNB")


class WordTests(unittest.TestCase):
    def test_picks_are_named_for_what_they_are(self) -> None:
        self.assertEqual(attach_ways.pick_word("Vertex"), "Point")
        self.assertEqual(attach_ways.pick_word("Solid"), "Object")
        self.assertEqual(attach_ways.pick_shape("Circle"), "curve")
        self.assertEqual(attach_ways.pick_shape("Cylinder"), "face")

    def test_known_errors_say_the_fix(self) -> None:
        what, fix = attach_ways.problem(
            "Points are collinear. Can't make a plane")
        self.assertIn("in a line", what)
        self.assertTrue(fix)
        self.assertEqual(attach_ways.problem("odd"), ("odd", ""))

    def test_needs_text(self) -> None:
        self.assertEqual(attach_ways.needs_text(
            ["Vertex", "Plane"], lambda text: text), "point + plane")


if __name__ == "__main__":
    unittest.main()
