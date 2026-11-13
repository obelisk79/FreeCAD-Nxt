"""The attachment panel's core, against stand-in objects and widgets.

Checks that picks reach the object, that FreeCAD's own attachment box is
kept in step when the cards stand in for it, which object a dialog is
found to be for, and that a binder is made attachable when asked.

Run with: python3 tests/test_attach_task.py
"""

from __future__ import annotations

import os
import sys
import time
import types
import unittest
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

store: dict[str, Any] = {}
App, Gui = fakes.install(ParamGet=fakes.params(store))
selection_log: list[str] = []
Gui.Selection = types.SimpleNamespace(
    clearSelection=lambda: selection_log.append("clear"),
    addObserver=lambda _o: selection_log.append("observe"),
    removeObserver=lambda _o: selection_log.append("forget"))

from freecad.nxt.tools import attach_task  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
FRIENDLY = {"FlatFace": "Plane face", "ObjectXY": "Object's XY"}


class Engine:
    """An AttachEngine copy: a face fits two modes."""

    ImplementedModes = ["Deactivated", "FlatFace", "ObjectXY",
                        "TangentPlane"]

    def __init__(self, obj: Any) -> None:
        self.obj = obj
        self.References: list[tuple[Any, str]] = []
        self.Mode = "Deactivated"
        self.Reverse = False
        self.Parameter = 0.0
        self.AttachmentOffset = None

    def readParametersFromFeature(self, obj: Any) -> None:  # noqa: N802
        self.References = list(obj.refs)
        self.Mode = obj.MapMode

    def writeParametersToFeature(self, obj: Any) -> None:  # noqa: N802
        obj.refs = list(self.References)
        obj.MapMode = self.Mode

    def suggestModes(self) -> dict[str, Any]:  # noqa: N802
        if not self.References:
            return {"message": "NoModesFit", "references_Types": []}
        return {"message": "OK", "bestFitMode": "FlatFace",
                "allApplicableModes": ["FlatFace", "ObjectXY"],
                "reachableModes": {"TangentPlane": [["Vertex"]]},
                "references_Types": ["Plane"],
                "nextRefTypeHint": []}

    def getModeInfo(self, mode: str) -> dict[str, str]:  # noqa: N802
        return {"UserFriendlyName": FRIENDLY.get(mode, mode)}


class Thing:
    """A document object, attachable unless told otherwise."""

    def __init__(self, name: str, attachable: bool = True,
                 types_: tuple[str, ...] = ()) -> None:
        self.Name = self.Label = name
        self.Document = DOC
        self.refs: list[tuple[Any, str]] = []
        self.MapMode = "Deactivated"
        self.ViewObject = types.SimpleNamespace(Selectable=True)
        self._types = types_
        if attachable:
            self.make_attachable()

    def make_attachable(self) -> None:
        self.AttachmentSupport = []
        self.Attacher = Engine(self)

    def addExtension(self, name: str) -> None:  # noqa: N802
        self.extension = name
        self.make_attachable()

    def isDerivedFrom(self, kind: str) -> bool:  # noqa: N802
        return kind in self._types

    def positionBySupport(self) -> bool:  # noqa: N802
        return self.MapMode != "Deactivated"


DOC = types.SimpleNamespace(Name="Doc", objects={})


def stock_box() -> QtWidgets.QWidget:
    """FreeCAD's attachment box, as far as the cards touch it."""
    box = QtWidgets.QWidget()
    button = QtWidgets.QPushButton(box)
    button.setObjectName("buttonRef1")
    button.setCheckable(True)
    button.setChecked(True)
    box.edited = []  # type: ignore[attr-defined]
    for index in range(1, 5):
        line = QtWidgets.QLineEdit(box)
        line.setObjectName("lineRef%d" % index)
        line.textEdited.connect(
            lambda text, i=index: box.edited.append((i, text)))
    modes = QtWidgets.QListWidget(box)
    modes.setObjectName("listOfModes")
    modes.addItems(["Deactivated", "Plane face", "Object's XY"])
    return box


class EmbeddedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.obj = Thing("Sketch")
        self.face = (Thing("Pad"), "Face6")
        self.box = stock_box()
        self.attachment = attach_task.EmbeddedAttachment(self.obj, self.box)
        self.attachment.start()

    def modes(self) -> Any:
        return self.box.findChild(QtWidgets.QListWidget, "listOfModes")

    def test_freecads_box_stops_taking_picks(self) -> None:
        button = self.box.findChild(QtWidgets.QPushButton, "buttonRef1")
        self.assertFalse(button.isChecked())

    def test_a_pick_attaches_and_the_box_follows(self) -> None:
        self.attachment.add(self.face)
        self.assertEqual(self.obj.refs, [self.face])
        self.assertEqual(self.obj.MapMode, "FlatFace")
        self.assertTrue(self.attachment.attached)
        self.assertIn((2, ""), self.box.edited)
        self.assertEqual(self.modes().currentRow(), 1)

    def test_a_chosen_variant_reaches_the_box(self) -> None:
        self.attachment.add(self.face)
        self.attachment.choose_mode("ObjectXY")
        self.assertEqual(self.obj.MapMode, "ObjectXY")
        self.assertEqual(self.modes().currentRow(), 2)

    def test_a_way_needing_more_picks_waits_for_them(self) -> None:
        self.attachment.add(self.face)
        self.attachment.choose_mode("TangentPlane")
        self.assertEqual(self.obj.MapMode, "FlatFace")
        self.assertTrue(self.attachment.picking)
        self.assertEqual(self.attachment.wanted, "TangentPlane")

    def test_detach_puts_the_box_on_its_first_row(self) -> None:
        self.attachment.add(self.face)
        self.attachment.detach()
        self.assertEqual(self.obj.refs, [])
        self.assertEqual(self.modes().currentRow(), 0)

    def test_finishing_gives_the_object_its_picking_back(self) -> None:
        self.assertFalse(self.obj.ViewObject.Selectable)
        self.attachment.finish()
        self.assertTrue(self.obj.ViewObject.Selectable)


class TargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.panels = attach_task.AttachPanels()
        App.listDocuments = lambda: {"Doc": DOC}
        App.getDocument = lambda _name: DOC
        DOC.getObject = lambda name: DOC.objects.get(name)

    def editing(self, obj: Any) -> None:
        view = types.SimpleNamespace(Object=obj) if obj else None
        Gui.ActiveDocument = types.SimpleNamespace(getInEdit=lambda: view)

    def test_the_object_in_edit_comes_first(self) -> None:
        datum = Thing("DatumPlane")
        self.editing(datum)
        self.assertIs(self.panels._target(), datum)

    def test_else_the_object_just_made(self) -> None:
        sketch = DOC.objects["Sketch"] = Thing("Sketch")
        self.editing(None)
        self.panels._made.slotCreatedObject(sketch)
        self.assertIs(self.panels._target(), sketch)

    def test_an_object_made_long_ago_is_not_it(self) -> None:
        DOC.objects["Sketch"] = Thing("Sketch")
        self.editing(None)
        self.panels._made.last = ("Doc", "Sketch",
                                  time.monotonic() - 2 * attach_task.NEW_FOR_S)
        self.assertIsNone(self.panels._target())


class BinderTests(unittest.TestCase):
    def test_a_binder_is_made_attachable_when_asked(self) -> None:
        binder = Thing("Binder", attachable=False,
                       types_=attach_task.ATTACHES_ON_ASK)
        self.assertTrue(attach_task.make_attachable(binder))
        self.assertEqual(binder.extension, attach_task.ADDED_EXTENSION)

    def test_other_objects_are_not(self) -> None:
        box = Thing("Box", attachable=False, types_=("Part::Feature",))
        self.assertFalse(attach_task.make_attachable(box))


if __name__ == "__main__":
    unittest.main()
