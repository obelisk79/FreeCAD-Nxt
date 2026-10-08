"""Mending a profile that will not close, against a stand-in sketch.

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
#: (left, bottom, right, top)
Box = tuple[float, float, float, float]
SIDE = 100.0


class Vector:
    def __init__(self, point: Point) -> None:
        self.x, self.y = point

    def __add__(self, other: Vector) -> Vector:
        return Vector((self.x + other.x, self.y + other.y))

    def __mul__(self, by: float) -> Vector:
        return Vector((self.x * by, self.y * by))


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


class Region:
    """One of a sketch's internal faces: its outline, and a point in it."""

    def __init__(self, outline: Box, inside: Point) -> None:
        self.OuterWire = outline
        self.inside = inside
        self.BoundBox = types.SimpleNamespace(DiagonalLength=SIDE)

    def tessellate(self, _coarseness: float) -> tuple[list[Vector], Any]:
        point = Vector(self.inside)
        return [point, point, point], [(0, 1, 2)]


def outline_face(box: Box) -> Any:
    """Part.Face of an outline: inside is inside the box."""
    left, bottom, right, top = box
    return types.SimpleNamespace(isInside=lambda p, _tol, _on: (
        left < p.x < right and bottom < p.y < top))


SQUARE = Region((0, 0, SIDE, SIDE), (50, 50))


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
        for obj in self.Objects:
            obj.recompute()


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
        self.InList: list[Any] = []
        self.conflicts_when_solved = False
        self.MakeInternals = False
        #: Its closed regions, once it makes them: none with a gap.
        self.regions = [] if gap else [SQUARE]
        doc.objects[self.Name] = self

    @property
    def InternalShape(self) -> Any:  # noqa: N802
        return types.SimpleNamespace(
            Faces=self.regions if self.MakeInternals else [])

    @property
    def Constraints(self) -> list[tuple[Any, ...]]:  # noqa: N802
        return self.constraints

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

    def delConstraint(self, index: int) -> None:
        del self.constraints[index]

    def solve(self) -> int:
        if self.conflicts_when_solved:
            self.ConflictingConstraints = [1]
        return 0

    def recompute(self) -> None:
        pass


class Pad:
    """Builds from a closed sketch, or from the regions picked in it."""

    Name = Label = "Pad"

    def __init__(self, sketch: Sketch, failed: bool = False,
                 regions_work: bool = True) -> None:
        self.sketch = sketch
        self.Profile: Any = (sketch, ("",))
        self.AllowMultiFace = False
        self.regions_work = regions_work
        self.State = ["Invalid"] if failed else []
        sketch.InList.append(self)
        sketch.Document.objects[self.Name] = self

    def isDerivedFrom(self, _kind: str) -> bool:
        return False

    def recompute(self) -> None:
        if any(self.Profile[1]):
            works = self.regions_work and self.AllowMultiFace
        else:
            works = sketch_repair.sketch_closure.inspect(
                sketch_repair._edges(self.sketch)).closed()
        self.State = [] if works else ["Invalid"]


STORE: dict[str, Any] = {}
STATE = types.SimpleNamespace(transaction=None, in_edit=None, task=False)
DOC = Doc()
App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(  # type: ignore[attr-defined]
    PrintError=lambda _m: None, PrintMessage=lambda _m: None,
    PrintLog=lambda _m: None)
App.ParamGet = lambda _g: types.SimpleNamespace(  # type: ignore
    GetBool=lambda k, d: STORE.get(k, d), GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)
App.listDocuments = lambda: {DOC.Name: DOC}  # type: ignore[attr-defined]
App.getDocument = lambda _name: DOC  # type: ignore[attr-defined]
App.getActiveTransaction = (  # type: ignore[attr-defined]
    lambda: STATE.transaction)
Gui = types.ModuleType("FreeCADGui")
Gui.getDocument = lambda _name: types.SimpleNamespace(  # type: ignore
    getInEdit=lambda: STATE.in_edit)
SELECTED: list[tuple[str, ...]] = []
Gui.Selection = types.SimpleNamespace(  # type: ignore[attr-defined]
    addSelection=lambda *names: SELECTED.append(names))
Gui.Control = types.SimpleNamespace(  # type: ignore[attr-defined]
    activeDialog=lambda: STATE.task)
Sketcher = types.ModuleType("Sketcher")
Sketcher.Constraint = lambda *args: args  # type: ignore[attr-defined]
Part = types.ModuleType("Part")
Part.Face = outline_face  # type: ignore[attr-defined]
sys.modules.update(FreeCAD=App, FreeCADGui=Gui, Sketcher=Sketcher,
                   Part=Part)

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt import sketch_repair  # noqa: E402


class RepairTests(unittest.TestCase):

    def setUp(self) -> None:
        STORE.clear()
        STATE.transaction = STATE.in_edit = None
        STATE.task = False
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

    def in_task(self) -> None:
        """A feature's task is open, in its own undo step."""
        STATE.task, STATE.transaction = True, ("Pad", 1)
        STATE.in_edit = types.SimpleNamespace(Object=DOC.objects["Pad"])

    def pick(self, sketch: Sketch) -> None:
        self.observer.addSelection("Doc", sketch.Name, "", (0, 0, 0))
        APP.processEvents()

    # -- gaps ---------------------------------------------------------------#

    def test_a_gap_in_a_profile_is_closed_in_one_undo_step(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch)
        self.leave(sketch)
        self.assertEqual(sketch.constraints, [("Coincident", 0, 1, 3, 2)])
        self.assertEqual(DOC.log, ["open", "recompute", "commit",
                                   "recompute"])
        self.assertEqual(self.said,
                         [("Repaired Sketch (gaps closed: 1)", True)])

    def test_a_failed_feature_has_its_profile_looked_at(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        pad = Pad(sketch, failed=True)
        self.feature_fails()
        self.assertEqual(len(sketch.constraints), 1)
        self.assertEqual((pad.State, pad.Profile[1]), ([], ("",)))

    def test_construction_geometry_is_not_part_of_the_profile(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (SIDE, SIDE)))
        sketch.construction = {4}
        Pad(sketch, failed=True)
        self.feature_fails()
        self.assertEqual((DOC.log, self.said), ([], []))

    def test_a_sketch_that_is_nothing_s_profile_is_left_alone(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        self.leave(sketch)
        self.assertEqual((sketch.constraints, DOC.log), ([], []))

    def test_a_gap_that_conflicts_is_taken_back_and_not_retried(
            self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        sketch.conflicts_when_solved = True
        Pad(sketch, failed=True)
        self.leave(sketch)
        self.assertEqual(sketch.constraints, [])
        self.assertEqual(DOC.log, ["open", "abort"])
        self.feature_fails()
        self.assertEqual(DOC.log, ["open", "abort"])

    # -- closed regions -----------------------------------------------------#

    def test_a_stray_edge_leaves_the_feature_on_the_closed_regions(
            self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (-40, -40)))
        pad = Pad(sketch, failed=True)
        self.feature_fails()
        self.assertEqual(pad.Profile, (sketch, ["InternalFace1"]))
        self.assertTrue(sketch.MakeInternals and pad.AllowMultiFace)
        self.assertEqual((pad.State, len(sketch.Geometry)), ([], 5))
        self.assertEqual(DOC.log[0], "open")
        self.assertEqual(self.said, [(
            "Repaired Sketch (Pad uses its closed profiles: 1)", True)])

    def test_so_does_an_overlap(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((20, 0), (60, 0)))
        pad = Pad(sketch, failed=True)
        self.feature_fails()
        self.assertEqual(pad.Profile, (sketch, ["InternalFace1"]))

    def test_holes_stay_holes(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (-40, -40)))
        sketch.regions = [
            Region((0, 0, 100, 100), (5, 5)),        # the plate
            Region((20, 20, 80, 80), (25, 25)),      # a hole in it
            Region((40, 40, 60, 60), (50, 50)),      # an island in that
        ]
        pad = Pad(sketch, failed=True)
        self.feature_fails()
        self.assertEqual(pad.Profile[1], ["InternalFace1", "InternalFace3"])

    def test_a_second_feature_on_the_sketch_is_mended_too(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (-40, -40)))
        Pad(sketch, failed=True)
        self.feature_fails()
        pocket = Pad(sketch, failed=True)
        pocket.Name = pocket.Label = "Pocket"
        DOC.objects["Pocket"] = DOC.objects.pop("Pad")
        self.feature_fails()
        self.assertEqual(pocket.Profile, (sketch, ["InternalFace1"]))

    def test_a_cancelled_repair_is_made_again(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (-40, -40)))
        pad = Pad(sketch, failed=True)
        self.in_task()
        self.pick(sketch)
        # The task's Cancel puts the profile and the sketch back as they
        # were, and the feature fails again.
        pad.Profile, pad.AllowMultiFace = (sketch, ("",)), False
        sketch.MakeInternals, pad.State = False, ["Invalid"]
        self.pick(sketch)
        self.assertEqual(pad.Profile, (sketch, ["InternalFace1"]))
        self.assertEqual(len(self.said), 2)

    def test_regions_that_do_not_mend_it_are_put_back(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((20, 0), (60, 0)))
        pad = Pad(sketch, failed=True, regions_work=False)
        self.feature_fails()
        self.assertEqual(pad.Profile, (sketch, ("",)))
        self.assertFalse(sketch.MakeInternals or pad.AllowMultiFace)
        self.assertEqual(DOC.log, ["open", "abort"])
        self.assertEqual(self.said, [(
            "Sketch is not closed (open ends: 2, overlapping edges: 1)",
            False)])
        self.assertEqual((list(self.buttons), self.sticky), (["Edit"], True))

    def test_a_feature_using_parts_of_the_sketch_is_left_alone(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (-40, -40)))
        pad = Pad(sketch, failed=True)
        pad.Profile = (sketch, ("Edge1",))
        self.feature_fails()
        self.assertEqual(pad.Profile, (sketch, ("Edge1",)))

    def test_a_working_feature_is_left_alone(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (-40, -40)))
        pad = Pad(sketch)
        self.leave(sketch)
        self.assertEqual((pad.Profile, DOC.log, self.said),
                         ((sketch, ("",)), [], []))

    def test_a_wide_opening_is_reported_once_with_no_undo(self) -> None:
        sketch = Sketch(DOC, gap=30.0)
        Pad(sketch, failed=True)
        for _again in range(2):
            self.feature_fails()
        self.assertEqual(sketch.constraints, [])
        self.assertEqual(self.said,
                         [("Sketch is not closed (open ends: 2)", False)])

    def test_edit_opens_the_sketch_on_the_overlapping_edges(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((20, 0), (60, 0)))
        Pad(sketch, failed=True, regions_work=False)
        self.feature_fails()
        self.buttons["Edit"]()
        self.assertEqual(self.edited, [])       # not inside the click
        APP.processEvents()
        self.assertEqual(self.edited, [("Doc", "Sketch")])
        self.assertEqual(SELECTED, [("Doc", "Sketch", "Edge1"),
                                    ("Doc", "Sketch", "Edge5")])

    # -- tasks --------------------------------------------------------------#

    def test_a_profile_picked_in_a_task_is_mended_in_its_step(self) -> None:
        sketch = Sketch(DOC)
        sketch.Geometry.append(Line((0, 0), (-40, -40)))
        pad = Pad(sketch, failed=True)
        self.in_task()
        self.pick(sketch)
        self.assertEqual(pad.Profile, (sketch, ["InternalFace1"]))
        self.assertNotIn("open", DOC.log)       # no step of its own
        self.assertEqual(self.said, [(
            "Repaired Sketch (Pad uses its closed profiles: 1)", False)])

    def test_a_gap_picked_in_a_task_is_closed_in_its_step(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch)
        self.in_task()
        self.pick(sketch)
        self.assertEqual(len(sketch.constraints), 1)
        self.assertEqual(DOC.log, ["recompute", "recompute"])

    def test_a_pick_outside_a_task_is_only_a_pick(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch)
        self.pick(sketch)
        self.assertEqual(sketch.constraints, [])

    def test_it_waits_while_the_sketch_itself_is_open(self) -> None:
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch, failed=True)
        STATE.in_edit = types.SimpleNamespace(Object=sketch)
        self.feature_fails()
        self.assertEqual(sketch.constraints, [])
        STATE.in_edit = None
        self.leave(sketch)
        self.assertEqual(len(sketch.constraints), 1)

    # -- the rest -----------------------------------------------------------#

    def test_the_preference_turns_it_off(self) -> None:
        STORE["RepairProfiles"] = False
        sketch = Sketch(DOC, gap=0.5)
        Pad(sketch, failed=True)
        self.leave(sketch)
        self.feature_fails()
        self.assertEqual((sketch.constraints, DOC.log), ([], []))

    def test_a_closed_document_is_forgotten(self) -> None:
        sketch = Sketch(DOC, gap=30.0)
        Pad(sketch, failed=True)
        self.leave(sketch)
        self.observer.slotDeletedDocument(DOC)
        self.assertEqual(self.repair._settled, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
