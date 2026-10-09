"""Space hides the feature picked, never its Body.

Run with: python3 tests/test_visibility.py   (needs PySide6)
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

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintError=lambda _m: None)
Gui = types.ModuleType("FreeCADGui")
sys.modules.setdefault("FreeCAD", App)
sys.modules.setdefault("FreeCADGui", Gui)
App = sys.modules["FreeCAD"]
Gui = sys.modules["FreeCADGui"]

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt import visibility  # noqa: E402


class Obj:
    def __init__(self, name: str, kind: str, shown: bool = True) -> None:
        self.Name = name
        self.kind = kind
        self.ViewObject = types.SimpleNamespace(Visibility=shown)
        self.Group: list[Any] = []
        self.Tip: Any = None

    def isDerivedFrom(self, kind: str) -> bool:  # noqa: N802
        return kind == self.kind


class Doc:
    Name = "Doc"

    def __init__(self) -> None:
        self.log: list[str] = []
        self.objects: dict[str, Any] = {}

    def getObject(self, name: str) -> Any:  # noqa: N802
        return self.objects.get(name)

    def openTransaction(self, name: str) -> None:  # noqa: N802
        self.log.append("open")

    def commitTransaction(self) -> None:  # noqa: N802
        self.log.append("commit")

    def abortTransaction(self) -> None:  # noqa: N802
        self.log.append("abort")


def entry(obj: Any, *subs: str) -> Any:
    return types.SimpleNamespace(Object=obj, SubElementNames=subs)


class TargetTests(unittest.TestCase):

    def setUp(self) -> None:
        self.body = Obj("Body", visibility.BODY)
        self.pad = Obj("Pad", visibility.FEATURE, shown=False)
        self.pocket = Obj("Pocket", visibility.FEATURE)
        self.sketch = Obj("Sketch", "Sketcher::SketchObject")
        self.body.Group = [self.sketch, self.pad, self.pocket]
        self.body.Tip = self.pocket
        self.picked: list[Any] = []
        Gui.Selection = types.SimpleNamespace(
            getSelectionEx=lambda _doc, _resolve=1: self.picked)
        self.doc = Doc()
        self.doc.objects = {o.Name: o for o in (
            self.body, self.pad, self.pocket, self.sketch)}

    def test_a_feature_picked_in_the_tree_is_that_feature(self) -> None:
        # FreeCAD files it under its Body: ("Body", "Pad.").
        self.picked = [entry(self.body, "Pad.")]
        self.assertEqual(visibility.targets(self.doc), [self.pad])
        visibility.toggle(self.doc, visibility.targets(self.doc))
        self.assertTrue(self.pad.ViewObject.Visibility)
        self.assertTrue(self.body.ViewObject.Visibility)

    def test_a_face_named_through_its_feature_is_that_feature(self) -> None:
        self.picked = [entry(self.body, "Pad.Face3")]
        self.assertEqual(visibility.targets(self.doc), [self.pad])

    def test_a_face_of_the_body_is_the_tips(self) -> None:
        self.picked = [entry(self.body, "Face6")]
        self.assertEqual(visibility.targets(self.doc), [self.pocket])

    def test_or_of_whichever_feature_is_showing(self) -> None:
        self.pocket.ViewObject.Visibility = False
        self.pad.ViewObject.Visibility = True
        self.picked = [entry(self.body, "Face6")]
        self.assertEqual(visibility.targets(self.doc), [self.pad])

    def test_the_body_picked_whole_is_the_body(self) -> None:
        self.picked = [entry(self.body)]
        self.assertEqual(visibility.targets(self.doc), [self.body])

    def test_space_hides_the_solid_and_nothing_else(self) -> None:
        self.picked = [entry(self.body, "Face6"), entry(self.body, "Edge2")]
        visibility.toggle(self.doc, visibility.targets(self.doc))
        self.assertFalse(self.pocket.ViewObject.Visibility)
        self.assertTrue(self.body.ViewObject.Visibility)
        self.assertTrue(self.sketch.ViewObject.Visibility)
        self.assertEqual(self.doc.log, ["open", "commit"])


class View3D(QtWidgets.QWidget):
    """Stands in for Gui::View3DInventor."""


class SpaceTests(unittest.TestCase):

    def setUp(self) -> None:
        self.calls: list[int] = []
        self.space = visibility.SpaceInView(
            action=lambda: self.calls.append(1))
        self.view = View3D()
        self.inner = QtWidgets.QWidget(self.view)
        self.saved = visibility.VIEW_CLASS
        visibility.VIEW_CLASS = View3D.staticMetaObject.className()
        Gui.ActiveDocument = types.SimpleNamespace(getInEdit=lambda: None)

    def tearDown(self) -> None:
        visibility.VIEW_CLASS = self.saved

    def send(self, widget: Any, kind: Any,
             modifiers: Any = QtCore.Qt.KeyboardModifier.NoModifier) -> Any:
        event = QtGui.QKeyEvent(kind, QtCore.Qt.Key.Key_Space, modifiers,
                                " ")
        event.ignore()
        taken = self.space.eventFilter(widget, event)
        return taken, event.isAccepted()

    def test_claimed_from_the_shortcut_in_a_3d_view(self) -> None:
        self.assertEqual(self.send(self.inner,
                                   QtCore.QEvent.Type.ShortcutOverride),
                         (False, True))
        self.assertEqual(self.send(self.inner, QtCore.QEvent.Type.KeyPress),
                         (True, True))
        self.assertEqual(self.calls, [1])

    def test_left_alone_elsewhere_with_modifiers_or_editing(self) -> None:
        other = QtWidgets.QWidget()
        self.assertFalse(self.send(other, QtCore.QEvent.Type.KeyPress)[0])
        self.assertFalse(self.send(
            self.inner, QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.KeyboardModifier.ControlModifier)[0])
        Gui.ActiveDocument = types.SimpleNamespace(getInEdit=lambda: "x")
        self.assertFalse(self.send(self.inner,
                                   QtCore.QEvent.Type.KeyPress)[0])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
