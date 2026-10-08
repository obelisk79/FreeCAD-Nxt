"""A new sketch on three picked points, against a stand-in sketch.

Run with: python3 tests/test_sketch_attach.py   (needs PySide6)
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6 import QtCore, QtWidgets  # noqa: E402

STORE: dict[str, Any] = {}
App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(  # type: ignore[attr-defined]
    PrintError=lambda _m: None, PrintMessage=lambda _m: None,
    PrintLog=lambda _m: None)
App.ParamGet = lambda _g: types.SimpleNamespace(  # type: ignore
    GetBool=lambda k, d: STORE.get(k, d), GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)
Gui = types.ModuleType("FreeCADGui")
sys.modules.update(FreeCAD=App, FreeCADGui=Gui)

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
MAIN = QtWidgets.QMainWindow()
Gui.getMainWindow = lambda: MAIN  # type: ignore[attr-defined]

from freecad.nxt import sketch_attach  # noqa: E402


class Thing:
    """A document object of one type."""

    def __init__(self, kind: str = "PartDesign::Pad") -> None:
        self.kind = kind

    def isDerivedFrom(self, kind: str) -> bool:
        return kind == self.kind


PAD = Thing()
THREE_POINTS = [(PAD, ("Vertex1", "Vertex4", "Vertex7"))]
EDGE_AND_POINT = [(PAD, ("Edge3",)), (PAD, ("Vertex7",))]


class Sketch(Thing):
    Name = "Sketch"

    def __init__(self, support: Any, applicable: bool = True,
                 in_line: bool = False) -> None:
        super().__init__("Sketcher::SketchObject")
        self.Document = types.SimpleNamespace(
            Name="Doc", getObject=lambda _name: self)
        self.AttachmentSupport = support
        self.MapMode = "NormalToEdge"
        self.in_line = in_line
        modes = ["NormalToEdge"] + ["ThreePointsPlane"] * applicable
        self.Attacher = types.SimpleNamespace(
            suggestModes=lambda: {"allApplicableModes": modes})

    def recompute(self) -> None:
        pass

    def isValid(self) -> bool:
        return not (self.in_line and self.MapMode == "ThreePointsPlane")


class AttachTests(unittest.TestCase):

    def setUp(self) -> None:
        STORE.clear()
        self.clicks = 0
        self.dialog_up = True
        self.shift = False
        saved = (sketch_attach._attacher_ok,
                 QtWidgets.QApplication.queryKeyboardModifiers)
        self.addCleanup(self.restore, *saved)
        sketch_attach._attacher_ok = lambda: (
            types.SimpleNamespace(click=self.click)
            if self.dialog_up else None)
        QtWidgets.QApplication.queryKeyboardModifiers = lambda: (
            QtCore.Qt.KeyboardModifier.ShiftModifier if self.shift
            else QtCore.Qt.KeyboardModifier.NoModifier)
        self.attach = sketch_attach.SketchAttach()

    @staticmethod
    def restore(attacher_ok: Any, modifiers: Any) -> None:
        sketch_attach._attacher_ok = attacher_ok
        QtWidgets.QApplication.queryKeyboardModifiers = modifiers

    def click(self) -> None:
        self.clicks += 1

    @staticmethod
    def wait() -> None:
        """Long enough for every retry to have run."""
        deadline = QtCore.QDeadlineTimer(
            sketch_attach.RETRY_MS * (sketch_attach.RETRIES + 2))
        while not deadline.hasExpired():
            APP.processEvents()

    def new_sketch(self, support: Any, **how: Any) -> Sketch:
        """New Sketch has just made a sketch with this selection."""
        sketch = Sketch(support, **how)
        App.ActiveDocument = sketch.Document  # type: ignore[attr-defined]
        self.attach._observer.slotCreatedObject(sketch)
        self.assertEqual(self.clicks, 0)        # not inside the command
        APP.processEvents()
        return sketch

    def test_three_points_are_a_plane(self) -> None:
        sketch = self.new_sketch(THREE_POINTS)
        self.assertEqual((sketch.MapMode, self.clicks),
                         ("ThreePointsPlane", 1))

    def test_so_are_an_edge_and_a_point(self) -> None:
        sketch = self.new_sketch(EDGE_AND_POINT)
        self.assertEqual((sketch.MapMode, self.clicks),
                         ("ThreePointsPlane", 1))

    def test_and_datum_points_and_lines_picked_whole(self) -> None:
        support = [(Thing("App::Line"), ("",)), (Thing("App::Point"), ())]
        self.assertEqual(sketch_attach._picked(support), (1, 1))
        self.assertEqual(self.new_sketch(support).MapMode,
                         "ThreePointsPlane")

    def test_other_selections_keep_the_dialog(self) -> None:
        for support in ([], [(PAD, ("Vertex1", "Vertex4"))],
                        [(PAD, ("Edge1", "Edge2"))],
                        [(PAD, ("Face1",)), (PAD, ("Vertex7",))],
                        [(PAD, ("",))]):
            sketch = self.new_sketch(support)
            self.assertEqual((sketch.MapMode, self.clicks),
                             ("NormalToEdge", 0))

    def test_an_element_is_read_from_the_end_of_its_path(self) -> None:
        support = [(PAD, ("Pad.Vertex1", "Pad.;g3;:H1,V.Vertex4",
                          "Vertex7"))]
        self.assertEqual(sketch_attach._picked(support), (3, 0))

    def test_a_curved_edge_keeps_the_dialog(self) -> None:
        sketch = self.new_sketch(EDGE_AND_POINT, applicable=False)
        self.assertEqual((sketch.MapMode, self.clicks), ("NormalToEdge", 0))

    def test_points_in_line_keep_the_dialog_and_the_mode(self) -> None:
        sketch = self.new_sketch(THREE_POINTS, in_line=True)
        self.assertEqual((sketch.MapMode, self.clicks), ("NormalToEdge", 0))

    def test_shift_asks_for_the_dialog(self) -> None:
        self.shift = True
        self.assertEqual(self.new_sketch(THREE_POINTS).MapMode,
                         "NormalToEdge")

    def test_so_does_freecad_s_preference(self) -> None:
        STORE["NewSketchUseAttachmentDialog"] = True
        self.new_sketch(THREE_POINTS)
        self.assertEqual(self.clicks, 0)

    def test_it_waits_for_the_dialog_to_come_up(self) -> None:
        self.dialog_up = False
        self.new_sketch(THREE_POINTS)
        self.assertEqual(self.clicks, 0)
        self.dialog_up = True
        self.wait()
        self.assertEqual(self.clicks, 1)

    def test_but_not_for_ever(self) -> None:
        self.dialog_up = False
        sketch_attach.RETRIES, tries = 2, sketch_attach.RETRIES
        self.addCleanup(setattr, sketch_attach, "RETRIES", tries)
        self.new_sketch(THREE_POINTS)
        self.wait()
        self.dialog_up = True
        self.wait()
        self.assertEqual(self.clicks, 0)

    def test_nothing_in_another_document(self) -> None:
        sketch = Sketch(THREE_POINTS)
        App.ActiveDocument = types.SimpleNamespace(  # type: ignore
            Name="Other")
        self.attach._observer.slotCreatedObject(sketch)
        APP.processEvents()
        self.assertEqual(self.clicks, 0)

    def test_it_can_be_turned_off(self) -> None:
        STORE["AttachSketchByPoints"] = False
        self.new_sketch(THREE_POINTS)
        self.assertEqual(self.clicks, 0)


class AttacherPanelTests(unittest.TestCase):
    """OK is pressed only on the attachment dialog."""

    def setUp(self) -> None:
        self.addCleanup(setattr, sketch_attach, "task_ok_button",
                        sketch_attach.task_ok_button)
        sketch_attach.task_ok_button = lambda: "OK"
        MAIN.show()
        self.addCleanup(MAIN.hide)

    def test_not_on_some_other_task(self) -> None:
        self.assertIsNone(sketch_attach._attacher_ok())

    def test_on_the_attachment_panel_however_it_is_named(self) -> None:
        for name in ("PartGui::TaskAttacher", "PartGui__TaskAttacher"):
            panel = QtWidgets.QWidget(MAIN)
            panel.setObjectName(name)
            self.assertIsNone(sketch_attach._attacher_ok())     # not shown
            panel.show()
            self.assertEqual(sketch_attach._attacher_ok(), "OK")
            panel.setParent(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
