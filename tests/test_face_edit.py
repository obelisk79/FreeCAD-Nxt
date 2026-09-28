"""Double-clicking a face in the 3D view edits the feature that made it.

Run with: python3 tests/test_face_edit.py   (needs PySide6)
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

STORE: dict[str, Any] = {}
App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintError=lambda _m: None,
                                    PrintLog=lambda _m: None)
App.ParamGet = lambda _g: types.SimpleNamespace(
    GetBool=lambda k, d: STORE.get(k, d), GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)
Gui = types.ModuleType("FreeCADGui")
sys.modules.setdefault("FreeCAD", App)
sys.modules.setdefault("FreeCADGui", Gui)
App = sys.modules["FreeCAD"]
Gui = sys.modules["FreeCADGui"]

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt.tree import face_edit  # noqa: E402


class View3D(QtWidgets.QWidget):
    """Stands in for Gui::View3DInventor (see setUp)."""


class Bridge(QtCore.QObject):
    def __init__(self) -> None:
        super().__init__()
        self.edited: list[tuple[str, str]] = []

    def edit_feature(self, doc: str, name: str) -> None:
        self.edited.append((doc, name))


def double_click(button: Any = QtCore.Qt.MouseButton.LeftButton) -> Any:
    return QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonDblClick, QtCore.QPointF(5, 5),
        QtCore.QPointF(5, 5), button, button,
        QtCore.Qt.KeyboardModifier.NoModifier)


class DoubleClickTests(unittest.TestCase):

    def setUp(self) -> None:
        STORE.clear()
        self.original_class = face_edit._VIEW_CLASS
        face_edit._VIEW_CLASS = "View3D"
        self.view = View3D()
        self.viewport = QtWidgets.QWidget(self.view)
        self.elsewhere = QtWidgets.QWidget()
        self.in_edit: Any = None
        self.under_pointer: Any = {"Object": "Body"}
        Gui.ActiveDocument = types.SimpleNamespace(
            getInEdit=lambda: self.in_edit,
            ActiveView=types.SimpleNamespace(
                getCursorPos=lambda: (5, 5),
                getObjectInfo=lambda _p: self.under_pointer))
        self.found: Any = ("Doc", "Pad")
        self.original_picked = face_edit.picked_feature
        face_edit.picked_feature = lambda: self.found
        self.bridge = Bridge()
        self.editor = face_edit.DoubleClickEditor(self.bridge)

    def tearDown(self) -> None:
        face_edit._VIEW_CLASS = self.original_class
        face_edit.picked_feature = self.original_picked

    def send(self, target: Any, event: Any = None) -> bool:
        return self.editor.eventFilter(target, event or double_click())

    def test_a_face_opens_the_feature_that_made_it(self) -> None:
        self.assertTrue(self.send(self.viewport))
        self.assertEqual(self.bridge.edited, [("Doc", "Pad")])

    def test_other_events_pass(self) -> None:
        press = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress, QtCore.QPointF(5, 5),
            QtCore.QPointF(5, 5), QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier)
        self.assertFalse(self.send(self.viewport, press))
        self.assertFalse(self.send(
            self.viewport, double_click(QtCore.Qt.MouseButton.RightButton)))

    def test_only_in_a_3d_view(self) -> None:
        self.assertFalse(self.send(self.elsewhere))

    def test_not_while_editing(self) -> None:
        self.in_edit = object()         # a sketch, say
        self.assertFalse(self.send(self.viewport))

    def test_not_on_empty_space(self) -> None:
        self.under_pointer = None
        self.assertFalse(self.send(self.viewport))

    def test_not_when_nothing_is_traced(self) -> None:
        self.found = None
        self.assertFalse(self.send(self.viewport))

    def test_it_can_be_turned_off(self) -> None:
        STORE["EditOnDoubleClick"] = False
        self.assertFalse(self.send(self.viewport))
        self.assertEqual(self.bridge.edited, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
