"""Closing a profile that all but closes, against a stand-in sketch.

Run with: python3 tests/test_sketch_repair.py   (needs PySide6)
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from math import hypot
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6 import QtWidgets  # noqa: E402

Point = tuple[float, float]
SIDE = 100.0


class Vector:
    def __init__(self, point: Point) -> None:
        self.x, self.y = point


class Line:
    TypeId = "Part::GeomLineSegment"
    FirstParameter, LastParameter = 0.0, 1.0

    def __init__(self, start: Point, end: Point) -> None:
        self.StartPoint, self.EndPoint = start, end

    def value(self, at: float) -> Vector:
        (x1, y1), (x2, y2) = self.StartPoint, self.EndPoint
        return Vector((x1 + (x2 - x1) * at, y1 + (y2 - y1) * at))

    def length(self) -> float:
        (x1, y1), (x2, y2) = self.StartPoint, self.EndPoint
        return hypot(x2 - x1, y2 - y1)


class Circle:
    """A closed curve: no ends."""


class Doc:
    Name = "Doc"

    def __init__(self) -> None:
        self.objects: dict[str, Any] = {}
        self.log: list[str] = []
        self.UndoCount = 0

    @property
    def Objects(self) -> list[Any]:
        return list(self.objects.values())

    def getObject(self, name: str) -> Any:
        return self.objects.get(name)

    def openTransaction(self, _name: str) -> None:
        self.log.append("open")

    def commitTransaction(self) -> None:
        self.log.append("commit")

    def abortTransaction(self) -> None:
        self.log.append("abort")

    def recompute(self) -> None:
        self.log.append("recompute")


class Sketch:
    """A square whose last side stops `gap` short of where it began."""

    Name = Label = "Sketch"
    State: list[str] = []
    ConflictingConstraints: list[int] = []

    def __init__(self, doc: Doc, gap: float = 0.0) -> None:
        self.Document = doc
        self.Geometry: list[Any] = [
            Line((0, 0), (SIDE, 0)), Line((SIDE, 0), (SIDE, SIDE)),
            Line((SIDE, SIDE), (0, SIDE)), Line((0, SIDE), (0, gap))]
        self.construction: set[int] = set()
        self.constraints: list[tuple[Any, ...]] = []
        self.deleted: list[int] = []
        self.InList: list[Any] = []
        self.conflicts_when_solved = False
        doc.objects[self.Name] = self

    def isDerivedFrom(self, kind: str) -> bool:
        return kind == "Sketcher::SketchObject"

    def getConstruction(self, index: int) -> bool:
        return index in self.construction

    def getPoint(self, index: int, pos: int) -> Vector:
        line = self.Geometry[index]
        return Vector(line.StartPoint if pos == 1 else line.EndPoint)

    def addConstraint(self, constraint: tuple[Any, ...]) -> None:
        """Coincident: the second point is moved onto the first."""
        self.constraints.append(constraint)
        _kind, first, first_end, second, second_end = constraint
        target = self.getPoint(first, first_end)
        setattr(self.Geometry[second],
                "StartPoint" if second_end == 1 else "EndPoint",
                (target.x, target.y))

    def delGeometries(self, indices: list[int]) -> None:
        self.deleted += indices
        for index in indices:
            del self.Geometry[index]

    def solve(self) -> int:
        if self.conflicts_when_solved:
            self.ConflictingConstraints = [1]
        return 0


class Pad:
    Name = Label = "Pad"

    def __init__(self, sketch: Sketch, failed: bool = False) -> None:
        self.Profile = (sketch, [])
        self.State = ["Invalid"] if failed else []
        sketch.InList.append(self)
        sketch.Document.objects[self.Name] = self

    def isDerivedFrom(self, _kind: str) -> bool:
        return False


STORE: dict[str, Any] = {}
STATE = types.SimpleNamespace(transaction=None, in_edit=None)
DOC = Doc()
App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(  # type: ignore[attr-defined]
    PrintError=lambda _m: None, PrintMessage=lambda _m: None,
    PrintLog=lambda _m: None)
App.ParamGet = lambda _g: types.SimpleNamespace(  # type: ignore
    GetBool=lambda k, d: STORE.get(k, d), GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)
App.listDocuments = lambda: {DOC.Name: DOC}  # type: ignore[attr-defined]
App.getActiveTransaction = (  # type: ignore[attr-defined]
    lambda: STATE.transaction)
Gui = types.ModuleType("FreeCADGui")
Gui.getDocument = lambda _name: types.SimpleNamespace(  # type: ignore
    getInEdit=lambda: STATE.in_edit)
SELECTED: list[tuple[str, ...]] = []
Gui.Selection = types.SimpleNamespace(  # type: ignore[attr-defined]
    addSelection=lambda *names: SELECTED.append(names))
Sketcher = types.ModuleType("Sketcher")
Sketcher.Constraint = lambda *args: args  # type: ignore[attr-defined]
sys.modules.update(FreeCAD=App, FreeCADGui=Gui, Sketcher=Sketcher)

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt import sketch_repair  # noqa: E402


class RepairTests(unittest.TestCase):

    def setUp(self) -> None:
        STORE.clear()
        STATE.transaction = STATE.in_edit = None
        DOC.objects.clear()
        DOC.log.clear()
        SELECTED.clear()
        self.said: list[tuple[str, bool]] = []
        #: The last toast's other buttons, by label, and whether it stays.
        self.buttons: dict[str, Any] = {}
        self.sticky = False
        self.addCleanup(setattr, sketch_repair.services, "toast",
                        sketch_repair.services.toast)
        sketch_repair.services.toast = self.toast
        self.edited: list[tuple[str, str]] = []
        self.addCleanup(setattr, sketch_repair.editing, "enter_edit",
                        sketch_repair.editing.enter_edit)
        sketch_repair.editing.enter_edit = (
            lambda doc, name: self.edited.append((doc, name)))
        self.repair = sketch_repair.SketchRepair()
        self.observer = self.repair._observer

    def toast(self, _doc: Any, message: str, after_undo: Any = None,
              undoable: bool = True, actions: Any = (),
              sticky: bool = False) -> None:
        self.said.append((message, undoable))
        self.buttons, self.sticky = dict(actions), sticky

    def feature_fails(self) -> None:
        """A recompute in which a feature has failed."""
        self.observer.slotRecomputedDocument(DOC)
        APP.processEvents()

    def leave(self, sketch: Sketch) -> None:
        """The user finishes editing the sketch."""
        self.observer.slotResetEdit(types.SimpleNamespace(Object=sketch))
        APP.processEvents()

    def test_a_gap_in_a_profile_is_closed_in_one_undo_step(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch)
        self.leave(sketch)
        self.assertEqual(sketch.constraints, [("Coincident", 0, 1, 3, 2)])
        self.assertEqual(DOC.log, ["open", "commit", "recompute"])
        self.assertEqual(self.said,
                         [("Repaired Sketch (gaps closed: 1)", True)])

    def test_an_edge_drawn_twice_is_deleted(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry += [Line((0, 0), (SIDE, 0)), Circle()]
        Pad(sketch)
        self.leave(sketch)
        self.assertEqual(sketch.deleted, [4])
        self.assertEqual(self.said,
                         [("Repaired Sketch (extra edges removed: 1)", True)])

    def test_construction_geometry_is_not_part_of_the_profile(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (SIDE, SIDE)))
        sketch.construction = {4}
        Pad(sketch)
        self.leave(sketch)
        self.assertEqual((DOC.log, self.said), ([], []))

    def test_a_sketch_that_is_nothing_s_profile_is_left_alone(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        self.leave(sketch)
        self.assertEqual((sketch.constraints, DOC.log), ([], []))

    def test_it_waits_for_an_open_undo_step_to_close(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch)
        STATE.transaction = ("Pad", 1)
        self.leave(sketch)
        self.assertEqual(sketch.constraints, [])
        STATE.transaction = None
        self.observer.slotCommitTransaction(DOC)
        APP.processEvents()
        self.assertEqual(len(sketch.constraints), 1)

    def test_it_waits_while_something_is_being_edited(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch)
        STATE.in_edit = object()
        self.leave(sketch)
        self.assertEqual(sketch.constraints, [])

    def test_a_repair_that_conflicts_is_taken_back_and_not_retried(
            self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        sketch.conflicts_when_solved = True
        Pad(sketch, failed=True)
        self.leave(sketch)
        self.assertEqual((DOC.log, self.said), (["open", "abort"], []))
        self.observer.slotRecomputedDocument(DOC)
        APP.processEvents()
        self.assertEqual(DOC.log, ["open", "abort"])

    def test_a_failed_feature_has_its_profile_looked_at(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch, failed=True)
        self.observer.slotRecomputedDocument(DOC)
        APP.processEvents()
        self.assertEqual(len(sketch.constraints), 1)

    def test_a_wide_opening_is_reported_once_with_no_undo(self) -> None:
        sketch = Sketch(DOC, gap=30.0)
        Pad(sketch, failed=True)
        for _again in range(2):
            self.observer.slotRecomputedDocument(DOC)
            APP.processEvents()
        self.assertEqual((sketch.constraints, DOC.log), ([], []))
        self.assertEqual(self.said,
                         [("Sketch is not closed (open ends: 2)", False)])

    def test_and_not_at_all_until_a_feature_fails_on_it(self) -> None:
        sketch = Sketch(DOC, gap=30.0)
        pad = Pad(sketch)
        self.leave(sketch)
        self.assertEqual(self.said, [])
        pad.State = ["Invalid"]
        self.observer.slotRecomputedDocument(DOC)
        APP.processEvents()
        self.assertEqual(len(self.said), 1)

    def test_what_is_left_to_the_user_stays_up_with_edit(self) -> None:
        sketch = Sketch(DOC, gap=30.0)
        Pad(sketch, failed=True)
        self.feature_fails()
        self.assertEqual((list(self.buttons), self.sticky), (["Edit"], True))
        self.buttons["Edit"]()
        self.assertEqual(self.edited, [])       # not inside the click
        APP.processEvents()
        self.assertEqual(self.edited, [("Doc", "Sketch")])

    def test_a_repair_that_leaves_trouble_says_both(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        sketch.Geometry.append(Line((SIDE, SIDE), (140, 140)))
        Pad(sketch)
        self.leave(sketch)
        self.assertEqual(self.said, [(
            "Repaired Sketch (gaps closed: 1); still not closed "
            "(open ends: 1, branch points: 1)", True)])
        self.assertEqual(list(self.buttons), ["Edit"])

    def overlapping(self) -> Sketch:
        """A square with a short line drawn over its first side."""
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((20, 0), (60, 0)))
        Pad(sketch, failed=True)
        self.feature_fails()
        return sketch

    def test_an_overlap_is_reported_not_repaired(self) -> None:
        sketch = self.overlapping()
        self.assertEqual((sketch.deleted, DOC.log), ([], []))
        self.assertEqual(self.said, [(
            "Sketch is not closed (open ends: 2, overlapping edges: 1)",
            False)])
        self.assertEqual(list(self.buttons), ["Edit", "Repair"])

    def test_edit_opens_the_sketch_on_the_overlapping_edges(self) -> None:
        self.overlapping()
        self.buttons["Edit"]()
        APP.processEvents()
        self.assertEqual(SELECTED, [("Doc", "Sketch", "Edge1"),
                                    ("Doc", "Sketch", "Edge5")])

    def test_repair_deletes_the_edge_that_was_in_the_way(self) -> None:
        sketch = self.overlapping()
        self.buttons["Repair"]()
        self.assertEqual(sketch.deleted, [4])
        self.assertEqual(DOC.log, ["open", "commit", "recompute"])
        self.assertEqual(self.said[-1],
                         ("Repaired Sketch (extra edges removed: 1)", True))

    def test_repair_is_not_offered_where_it_would_not_close(self) -> None:
        sketch = Sketch(DOC, gap=30.0)
        sketch.Geometry.append(Line((20, 0), (60, 0)))
        Pad(sketch, failed=True)
        self.feature_fails()
        self.assertEqual(list(self.buttons), ["Edit"])

    def test_repair_on_a_sketch_since_changed_looks_again(self) -> None:
        sketch = self.overlapping()
        repair = self.buttons["Repair"]
        sketch.Geometry.insert(0, Line((200, 200), (300, 300)))
        repair()
        self.assertEqual((sketch.deleted, DOC.log), ([], []))
        APP.processEvents()
        self.assertEqual(len(self.said), 2)

    def test_the_preference_turns_it_off(self) -> None:
        STORE["RepairProfiles"] = False
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch, failed=True)
        self.leave(sketch)
        self.observer.slotRecomputedDocument(DOC)
        APP.processEvents()
        self.assertEqual((sketch.constraints, DOC.log), ([], []))

    def test_a_closed_document_is_forgotten(self) -> None:
        sketch = Sketch(DOC, gap=30.0)
        Pad(sketch, failed=True)
        self.leave(sketch)
        self.observer.slotDeletedDocument(DOC)
        self.assertEqual(self.repair._settled, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
