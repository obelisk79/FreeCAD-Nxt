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

import fakes  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

App, Gui = fakes.install()

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

from freecad.nxt.core import view3d  # noqa: E402
from freecad.nxt.tools import visibility  # noqa: E402


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

    def test_a_face_picked_in_the_view_is_its_body(self) -> None:
        self.picked = [entry(self.body, "Pad.Face3")]
        self.assertEqual(visibility.targets(self.doc), [self.body])
        self.picked = [entry(self.body, "Face6")]
        self.assertEqual(visibility.targets(self.doc), [self.body])

    def test_hiding_a_feature_shows_no_other(self) -> None:
        self.picked = [entry(self.body, "Pocket.")]
        visibility.toggle(self.doc, visibility.targets(self.doc))
        self.assertFalse(self.pocket.ViewObject.Visibility)
        self.assertFalse(self.pad.ViewObject.Visibility)
        self.assertTrue(self.body.ViewObject.Visibility)

    def test_the_body_picked_whole_is_the_body(self) -> None:
        self.picked = [entry(self.body)]
        self.assertEqual(visibility.targets(self.doc), [self.body])

    def test_space_in_the_view_hides_the_body_and_nothing_else(self) -> None:
        self.picked = [entry(self.body, "Face6"), entry(self.body, "Edge2")]
        visibility.toggle(self.doc, visibility.targets(self.doc))
        self.assertFalse(self.body.ViewObject.Visibility)
        self.assertTrue(self.pocket.ViewObject.Visibility)
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
        self.saved = view3d.VIEW3D_CLASS
        view3d.VIEW3D_CLASS = View3D.staticMetaObject.className()
        Gui.ActiveDocument = types.SimpleNamespace(getInEdit=lambda: None)

    def tearDown(self) -> None:
        view3d.VIEW3D_CLASS = self.saved

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


class TreeShortcutTests(unittest.TestCase):
    """FreeCAD's shortcut for a key the Nxt tree takes is dropped there."""

    def setUp(self) -> None:
        self.space = visibility.SpaceInView(action=lambda: None)
        self.panel = QtWidgets.QWidget()
        self.panel.setObjectName(visibility.TREE_PANEL)
        self.inner = QtWidgets.QWidget(self.panel)
        self.other = QtWidgets.QWidget()

    def shortcut(self, keys: str, focus: Any) -> bool:
        event = types.SimpleNamespace(
            type=lambda: QtCore.QEvent.Type.Shortcut,
            key=lambda: QtGui.QKeySequence(keys))
        saved = QtWidgets.QApplication.focusWidget
        QtWidgets.QApplication.focusWidget = staticmethod(  # type: ignore
            lambda: focus)
        try:
            return self.space.eventFilter(QtGui.QAction(), event)
        finally:
            QtWidgets.QApplication.focusWidget = saved  # type: ignore

    def test_dropped_in_the_tree(self) -> None:
        for keys in ("Space", "Home", "End", "Del", "Backspace"):
            self.assertTrue(self.shortcut(keys, self.inner), keys)

    def test_kept_elsewhere_or_for_other_keys(self) -> None:
        self.assertFalse(self.shortcut("Space", self.other))
        self.assertFalse(self.shortcut("Space", None))
        self.assertFalse(self.shortcut("Ctrl+Space", self.inner))
        self.assertFalse(self.shortcut("V", self.inner))


class NativeMenuBarTests(unittest.TestCase):
    """macOS: Space moves off FreeCAD's menu item to an action of ours."""

    def test_taken_then_given_back(self) -> None:
        main = QtWidgets.QMainWindow()
        stock = QtGui.QAction(main)
        stock.setShortcut(QtGui.QKeySequence("Space"))
        ran: list[str] = []
        Gui.Command = types.SimpleNamespace(
            get=lambda _name: types.SimpleNamespace(
                getAction=lambda: [stock]))
        Gui.getMainWindow = lambda: main
        Gui.runCommand = lambda name, _index=0: ran.append(name)
        space = visibility.SpaceInView(native_menu_bar=True)
        space.install()
        self.assertTrue(stock.shortcut().isEmpty())
        ours = space._fallback
        self.assertEqual(ours.shortcut().toString(), "Space")
        ours.trigger()
        self.assertEqual(ran, [visibility.STOCK])
        space.remove()
        self.assertEqual(stock.shortcut().toString(), "Space")
        self.assertNotIn(ours, main.actions())


if __name__ == "__main__":
    unittest.main(verbosity=2)
