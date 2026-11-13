"""The Contents card's snapshot and rows, against stand-in sketches.

Also times a large sketch, so a change that makes reading or laying out
slow shows here first.

Run with: python3 tests/test_sketch_contents.py
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
from sketch_fakes import Constraint, LineSegment, Sketch  # noqa: E402

App, Gui = fakes.install()

from freecad.nxt.tools import sketch_contents as contents  # noqa: E402

#: Sizes and budget for the large sketch: well past a typical part.
LARGE_ELEMENTS = 5000
LARGE_CONSTRAINTS = 12000
#: Seconds for one read and one layout of the large sketch.
LARGE_BUDGET = 1.0


def keys(rows: list[dict]) -> list[str]:
    return [row["key"] for row in rows]


def laid_out(sketch: Sketch, **view: object) -> list[dict]:
    return contents.rows(contents.read(sketch), contents.View(**view))


class ElementTests(unittest.TestCase):
    def test_every_element_then_the_external_ones(self) -> None:
        rows = laid_out(Sketch())
        self.assertEqual(keys(rows), ["e0", "e1", "e2", "e3", "x1"])
        self.assertEqual(rows[4]["title"], "External 1")
        self.assertEqual(rows[4]["name"], "ExternalEdge1")

    def test_only_what_can_move_is_marked(self) -> None:
        marks = [row["mark"] for row in laid_out(Sketch())]
        self.assertEqual(marks, [0, 0, contents.MARK_FREE,
                                 contents.MARK_FREE, 0])

    def test_free_filter_names_the_parts_that_move(self) -> None:
        rows = laid_out(Sketch(), filters=frozenset({contents.FREE}))
        self.assertEqual([(r["key"], r["detail"]) for r in rows],
                         [("e2", "end"), ("e3", "edge")])

    def test_construction_reads_dashed(self) -> None:
        row = laid_out(Sketch())[3]
        self.assertTrue(row["dashed"])
        self.assertEqual(row["detail"], "construction")

    def test_one_element_selected_opens_its_strip(self) -> None:
        rows = laid_out(Sketch(), selected=("Edge1",))
        self.assertEqual(keys(rows)[:2], ["e0", "s0"])
        self.assertTrue(rows[0]["selected"])
        self.assertEqual([chip["name"] for chip in rows[1]["chips"]],
                         ["Constraint1", "Constraint3"])

    def test_a_point_selects_its_element(self) -> None:
        rows = laid_out(Sketch(), selected=("Vertex3",),
                        vertex_geo={"Vertex3": 1})
        self.assertIn("s1", keys(rows))

    def test_several_selected_show_a_summary_instead(self) -> None:
        rows = laid_out(Sketch(), selected=("Edge1", "Edge2"))
        self.assertEqual(rows[0]["kind"], "summary")
        self.assertEqual(rows[0]["count"], 2)
        self.assertNotIn("s0", keys(rows))

    def test_chips_are_capped_dimensions_first(self) -> None:
        sketch = Sketch()
        sketch.Constraints = [Constraint("Coincident", 0, 1)
                              for _ in range(8)]
        sketch.Constraints.append(Constraint("Distance", 0, value=5.0))
        strip = laid_out(sketch, selected=("Edge1",))[1]
        self.assertEqual(strip["chips"][0]["name"], "Constraint9")
        self.assertEqual(len(strip["chips"]), contents.CHIP_CAP)
        self.assertEqual(strip["more"], 9 - contents.CHIP_CAP)

    def test_search_matches_title_and_number(self) -> None:
        self.assertEqual(keys(laid_out(Sketch(), query="circle")), ["e3"])
        self.assertEqual(keys(laid_out(Sketch(), query="#2")), ["e1"])


class ConstraintTests(unittest.TestCase):
    def test_dimensions_lead_then_each_type(self) -> None:
        rows = laid_out(Sketch(), tab=contents.CONSTRAINTS)
        self.assertEqual(keys(rows), [
            "g:dimensions", "c1", "g:Coincident", "c2", "g:Horizontal",
            "c0", "g:PointOnObject", "c3"])
        self.assertEqual(rows[1]["title"], "Width")
        self.assertTrue(rows[1]["editable"])

    def test_long_groups_start_folded(self) -> None:
        sketch = Sketch()
        sketch.Constraints += [Constraint("Coincident", 0, 1)
                               for _ in range(contents.FOLD_ABOVE)]
        rows = laid_out(sketch, tab=contents.CONSTRAINTS)
        group = next(r for r in rows if r["key"] == "g:Coincident")
        self.assertTrue(group["folded"])
        self.assertEqual(group["count"], contents.FOLD_ABOVE + 1)
        self.assertNotIn("c2", keys(rows))

    def test_a_problem_opens_its_group_and_rises(self) -> None:
        sketch = Sketch()
        sketch.Constraints += [Constraint("Coincident", 0, 1)
                               for _ in range(contents.FOLD_ABOVE)]
        sketch.ConflictingConstraints = [14]
        rows = laid_out(sketch, tab=contents.CONSTRAINTS)
        at = keys(rows).index("g:Coincident")
        self.assertEqual(rows[at + 1]["key"], "c13")
        self.assertTrue(rows[at + 1]["fixes"])
        self.assertGreater(rows[at]["mark"], contents.MARK_FREE)

    def test_a_selected_constraint_shows_its_geometry(self) -> None:
        sketch = Sketch()
        sketch.Constraints[0].Second = -1
        rows = laid_out(sketch, tab=contents.CONSTRAINTS,
                        selected=("Constraint1",))
        strip = rows[keys(rows).index("c0") + 1]
        self.assertEqual([c["name"] for c in strip["chips"]],
                         ["Edge1", "H_Axis"])

    def test_values_are_searched_when_given(self) -> None:
        snap = contents.read(Sketch())
        rows = contents.rows(snap, contents.View(
            tab=contents.CONSTRAINTS, query="32"), {1: "32.00 mm"})
        self.assertEqual(keys(rows), ["g:dimensions", "c1"])

    def test_filters_keep_reference_and_inactive(self) -> None:
        sketch = Sketch()
        sketch.Constraints[1].Driving = False
        sketch.Constraints[2].IsActive = False
        rows = laid_out(sketch, tab=contents.CONSTRAINTS,
                        filters=frozenset({contents.REFERENCE,
                                           contents.INACTIVE}))
        self.assertEqual([r["key"] for r in rows if r["kind"] ==
                          "constraint"], ["c1", "c2"])


class LargeSketchTests(unittest.TestCase):
    def test_reads_and_lays_out_within_budget(self) -> None:
        sketch = Sketch()
        sketch.Geometry = [LineSegment() for _ in range(LARGE_ELEMENTS)]
        sketch.construction = set()
        sketch.Constraints = [
            Constraint("Coincident" if i % 3 else "Distance",
                       i % LARGE_ELEMENTS, (i + 1) % LARGE_ELEMENTS,
                       value=float(i))
            for i in range(LARGE_CONSTRAINTS)]
        started = time.perf_counter()
        snap = contents.read(sketch)
        for tab in (contents.ELEMENTS, contents.CONSTRAINTS):
            contents.rows(snap, contents.View(tab=tab,
                                              selected=("Edge7",)))
        took = time.perf_counter() - started
        print("\n  large sketch: %.3f s" % took, end=" ")
        self.assertLess(took, LARGE_BUDGET)


if __name__ == "__main__":
    unittest.main()
