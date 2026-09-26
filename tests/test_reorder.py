"""Reordering a Body by drag and drop: the plan, before anything moves.

Run with: python3 tests/test_reorder.py
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("FreeCAD", types.ModuleType("FreeCAD"))

from freecad.nxt.tree.reorder import dependencies, plan  # noqa: E402

# Sketch -> Pad -> Sketch001 (on Pad's face) -> Pocket -> Fillet (Pocket's
# edges), and a free-standing Plane nothing reads.
MEMBERS = ["Sketch", "Pad", "Plane", "Sketch001", "Pocket", "Fillet"]
DEPENDS = {
    "Pad": {"Sketch"},
    "Sketch001": {"Pad", "Sketch"},
    "Pocket": {"Sketch001", "Pad", "Sketch"},
    "Fillet": {"Pocket", "Sketch001", "Pad", "Sketch"},
}


class PlanTests(unittest.TestCase):

    def test_a_drop_puts_it_just_after_the_target(self) -> None:
        result = plan(MEMBERS, ["Plane"], "Pocket", DEPENDS)
        self.assertTrue(result.ok, result.problem)
        self.assertEqual(result.order, ("Sketch", "Pad", "Sketch001",
                                        "Pocket", "Plane", "Fillet"))
        self.assertEqual(result.moving, ("Plane",))

    def test_onto_the_body_puts_it_first(self) -> None:
        result = plan(MEMBERS, ["Plane"], None, DEPENDS)
        self.assertEqual(result.order[0], "Plane")

    def test_nothing_may_come_before_what_it_reads(self) -> None:
        result = plan(MEMBERS, ["Pocket"], "Sketch", DEPENDS)
        self.assertFalse(result.ok)
        self.assertIn("Pocket would come before", result.problem)
        # ...nor what reads it end up before it.
        result = plan(MEMBERS, ["Sketch001"], "Fillet", DEPENDS)
        self.assertFalse(result.ok)
        self.assertIn("Pocket would come before Sketch001", result.problem)

    def test_several_move_together_in_body_order(self) -> None:
        result = plan(MEMBERS, ["Fillet", "Plane"], "Pad", DEPENDS)
        self.assertFalse(result.ok)         # Fillet before Pocket
        result = plan(MEMBERS, ["Fillet", "Plane"], "Pocket", DEPENDS)
        self.assertTrue(result.ok, result.problem)
        self.assertEqual(result.moving, ("Plane", "Fillet"))
        self.assertEqual(result.order[-2:], ("Plane", "Fillet"))

    def test_refusals(self) -> None:
        self.assertFalse(plan(MEMBERS, ["Pad"], "Pad", DEPENDS).ok)
        self.assertFalse(plan(MEMBERS, ["Pad"], "Sketch", DEPENDS).ok)
        self.assertIn("already there",
                      plan(MEMBERS, ["Pad"], "Sketch", DEPENDS).problem)
        self.assertIn("base feature",
                      plan(MEMBERS, ["Sketch"], "Pad", DEPENDS,
                           base="Sketch").problem)
        self.assertFalse(plan(MEMBERS, ["Plane"], "Elsewhere", DEPENDS).ok)


class Obj:
    """Enough of a document object for dependencies()."""

    def __init__(self, name: str, solid: bool, out: list[Obj]) -> None:
        self.Name, self._solid, self.OutList = name, solid, out

    def isDerivedFrom(self, type_name: str) -> bool:
        return self._solid and type_name == "PartDesign::Feature"

    @property
    def OutListRecursive(self) -> list[Obj]:
        seen: list[Obj] = []
        stack = list(self.OutList)
        while stack:
            obj = stack.pop()
            if obj not in seen:
                seen.append(obj)
                stack.extend(obj.OutList)
        return seen


class FreeCADRuleTests(unittest.TestCase):
    """The rule Part Design's Move Feature After command applies."""

    def setUp(self) -> None:
        sketch = Obj("Sketch", False, [])
        pad = Obj("Pad", True, [sketch])
        on_pad = Obj("Sketch001", False, [pad])         # attached to a face
        pocket = Obj("Pocket", True, [pad, on_pad])     # pad: BaseFeature
        loose = Obj("Sketch002", False, [])
        groove = Obj("Groove", True, [pocket, loose])
        self.body = types.SimpleNamespace(
            Group=[sketch, pad, on_pad, pocket, loose, groove])
        self.members = [m.Name for m in self.body.Group]
        self.rules = dependencies(self.body)

    def test_base_feature_links_do_not_count(self) -> None:
        # Groove's BaseFeature is Pocket; the Body rewires that on a move.
        self.assertEqual(self.rules["Groove"], set())
        result = plan(self.members, ["Groove"], "Pad", self.rules)
        self.assertTrue(result.ok, result.problem)

    def test_a_feature_stays_after_what_its_sketch_is_on(self) -> None:
        self.assertEqual(self.rules["Pocket"], {"Pad"})
        self.assertFalse(plan(self.members, ["Pocket"], "Sketch",
                              self.rules).ok)

    def test_sketches_are_free_to_move(self) -> None:
        self.assertNotIn("Sketch001", self.rules)
        result = plan(self.members, ["Sketch002"], "Sketch", self.rules)
        self.assertTrue(result.ok, result.problem)


if __name__ == "__main__":
    unittest.main(verbosity=2)
