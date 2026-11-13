"""A sketch read for its task panel, against a stand-in sketch.

Run with: python3 tests/test_sketch_state.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
from sketch_fakes import Sketch  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.tools import sketch_state as state  # noqa: E402


class StatusTests(unittest.TestCase):
    def test_free_sketch_links_its_degrees_of_freedom(self) -> None:
        status = state.status(Sketch())
        self.assertEqual((status["mark"], status["link"], status["action"]),
                         (state.MARK_FREE, "3 DoF", state.FREE))

    def test_fully_constrained_has_no_mark(self) -> None:
        sketch = Sketch()
        sketch.DoF = 0
        status = state.status(sketch)
        self.assertEqual((status["mark"], status["text"], status["link"]),
                         (state.MARK_NONE, "Fully constrained", ""))

    def test_empty_sketch_says_so(self) -> None:
        sketch = Sketch()
        sketch.Geometry = []
        self.assertEqual(state.status(sketch)["text"], "Empty sketch")

    def test_the_worst_finding_leads(self) -> None:
        sketch = Sketch()
        sketch.RedundantConstraints = [4]
        sketch.ConflictingConstraints = [1, 3]
        status = state.status(sketch)
        self.assertEqual((status["text"], status["link"], status["action"]),
                         ("Over-constrained", "1, 3",
                          "ConflictingConstraints"))
        self.assertEqual(status["mark"], 3)

    def test_unknown_degrees_of_freedom_claim_nothing(self) -> None:
        sketch = Sketch()
        del sketch.DoF
        status = state.status(sketch)
        self.assertEqual((status["text"], status["link"]), ("", ""))


class IssueTests(unittest.TestCase):
    def test_healthy_sketch_has_none(self) -> None:
        self.assertEqual(state.issues(Sketch()), [])

    def test_every_finding_lists_its_constraints(self) -> None:
        sketch = Sketch()
        sketch.RedundantConstraints = [4]
        sketch.ConflictingConstraints = [1, 2]
        conflicting, redundant = state.issues(sketch)
        self.assertEqual([row["number"] for row in conflicting["rows"]],
                         [1, 2])
        self.assertEqual(conflicting["rows"][1]["value"], "32.00 mm")
        self.assertEqual(redundant["title"], "Redundant constraints")
        self.assertEqual(redundant["rows"][0]["label"], "Point on object")
        self.assertLess(redundant["mark"], conflicting["mark"])

    def test_a_number_past_the_list_is_left_out(self) -> None:
        sketch = Sketch()
        sketch.ConflictingConstraints = [2, 9]
        rows = state.issues(sketch)[0]["rows"]
        self.assertEqual([row["number"] for row in rows], [2])


class SelectionTests(unittest.TestCase):
    def test_an_edge_shows_its_element_and_constraints(self) -> None:
        picked = state.selection(Sketch(), ["Edge1"])
        self.assertEqual((picked["kind"], picked["title"]),
                         ("element", "Line 1"))
        self.assertEqual([row["number"] for row in picked["rows"]], [1, 3])
        self.assertFalse(picked["construction"])

    def test_a_point_shows_the_element_it_is_on(self) -> None:
        picked = state.selection(Sketch(), ["Vertex7"])
        self.assertEqual((picked["title"], picked["construction"]),
                         ("Circle 4", True))

    def test_a_constraint_shows_what_can_be_set(self) -> None:
        picked = state.selection(Sketch(), ["Body.Sketch.Constraint2"])
        self.assertEqual((picked["kind"], picked["index"], picked["name"]),
                         ("constraint", 1, "Width"))
        self.assertTrue(picked["dimensional"] and picked["driving"])
        self.assertFalse(
            state.selection(Sketch(), ["Constraint1"])["dimensional"])

    def test_a_constraint_names_its_geometry_once(self) -> None:
        sketch = Sketch()
        sketch.Constraints[0].Second = -1
        sketch.Constraints[2].Second = 0
        horizontal = state.selection(sketch, ["Constraint1"])["geometry"]
        self.assertEqual(horizontal, [
            {"title": "Line 1", "name": "Edge1"},
            {"title": "Horizontal axis", "name": "H_Axis"}])
        self.assertEqual(
            len(state.selection(sketch, ["Constraint3"])["geometry"]), 1)

    def test_external_geometry_counts_up_from_one(self) -> None:
        self.assertEqual(state.geometry_ref(Sketch(), -4),
                         {"title": "External 2", "name": "ExternalEdge2"})

    def test_nothing_else_has_a_card(self) -> None:
        sketch = Sketch()
        for names in ([], ["Edge1", "Edge2"], ["H_Axis"], ["RootPoint"],
                      ["ExternalEdge1"], ["Edge99"], ["Constraint99"]):
            self.assertEqual(state.selection(sketch, names), {"kind": ""},
                             names)


if __name__ == "__main__":
    unittest.main()
