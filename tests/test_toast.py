"""The undo toast: shown over the 3D view, and what its Undo undoes.

Run with: python3 tests/test_toast.py   (needs PySide6)
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


class Doc:
    Name = "Doc"

    def __init__(self) -> None:
        self.UndoCount = 3
        self.log: list[str] = []

    def undo(self) -> None:
        self.log.append("undo")

    def recompute(self) -> None:
        self.log.append("recompute")


PRINTED: list[str] = []
App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(  # type: ignore[attr-defined]
    PrintError=PRINTED.append, PrintMessage=PRINTED.append,
    PrintLog=PRINTED.append)
App.ParamGet = lambda _g: types.SimpleNamespace(  # type: ignore
    GetBool=lambda _k, d: d, GetInt=lambda _k, d: d,
    GetFloat=lambda _k, d: d, GetString=lambda _k, d: d)
Gui = types.ModuleType("FreeCADGui")
sys.modules.update(FreeCAD=App, FreeCADGui=Gui)

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
MAIN = QtWidgets.QMainWindow()
Gui.getMainWindow = lambda: MAIN  # type: ignore[attr-defined]

from freecad.nxt import toast as toast_mod  # noqa: E402
from freecad.nxt.tree import theme as theme_mod  # noqa: E402

VIEW_WIDTH = 800
THEME = theme_mod.Theme(None, MAIN)


class ToastTests(unittest.TestCase):

    def setUp(self) -> None:
        PRINTED.clear()
        self.doc = Doc()
        App.ActiveDocument = self.doc  # type: ignore[attr-defined]
        Gui.ActiveDocument = types.SimpleNamespace(  # type: ignore
            Document=self.doc)
        self.view: Any = QtWidgets.QWidget()
        self.view.resize(VIEW_WIDTH, 600)
        self.view.show()
        self.saved = toast_mod.active_view_widget
        toast_mod.active_view_widget = lambda: self.view  # type: ignore
        self.above: Any = None
        self.toast = toast_mod.Toast(
            THEME, lambda: self.above)

    def tearDown(self) -> None:
        self.toast.remove()
        toast_mod.active_view_widget = self.saved  # type: ignore
        # The widget is deleted later: now, while its theme still exists.
        APP.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

    def root(self) -> Any:
        return self.toast._widget.rootObject()

    def buttons(self) -> list[str]:
        """The buttons' labels. A Repeater's, so findChildren misses them."""
        return [item.property("text")
                for row in self.root().childItems()
                for item in row.childItems()
                if item.objectName() == "toastAction"]

    def test_it_is_shown_over_the_view_centred(self) -> None:
        self.toast.show(self.doc, "Renamed B to Bracket")
        APP.processEvents()
        widget = self.toast._widget
        self.assertTrue(widget.isVisible())
        self.assertIs(widget.parentWidget(), self.view)
        self.assertEqual(self.root().property("message"),
                         "Renamed B to Bracket")
        self.assertGreater(widget.width(), 0)
        self.assertAlmostEqual(widget.x() + widget.width() / 2,
                               VIEW_WIDTH / 2, delta=1)
        self.assertEqual(PRINTED, [])

    def test_a_second_message_reuses_the_widget(self) -> None:
        self.toast.show(self.doc, "one")
        first = self.toast._widget
        self.toast.dismissed()
        self.assertFalse(first.isVisible())
        self.toast.show(self.doc, "two")
        self.assertIs(self.toast._widget, first)
        self.assertTrue(first.isVisible())
        self.assertEqual(self.root().property("message"), "two")

    def test_a_long_message_stays_inside_the_view(self) -> None:
        self.toast.show(self.doc, "Moved " + "x" * 400)
        APP.processEvents()
        self.assertLessEqual(self.toast._widget.width(), VIEW_WIDTH)

    def test_it_sits_under_the_notice_above(self) -> None:
        self.toast.show(self.doc, "one")
        alone = self.toast._widget.y()
        self.above = types.SimpleNamespace(bottom=lambda: 40)
        self.toast.show(self.doc, "two")
        self.assertEqual(self.toast._widget.y(), alone + 40)

    def test_undo_undoes_it_once(self) -> None:
        self.toast.show(self.doc, "one")
        self.assertTrue(self.toast.undo())
        self.assertFalse(self.toast.undo())
        self.assertEqual(self.doc.log, ["undo", "recompute"])

    def test_after_undo_runs_between_undo_and_recompute(self) -> None:
        self.toast.show(self.doc, "one",
                        lambda doc: doc.log.append("after"))
        self.toast.undo()
        self.assertEqual(self.doc.log, ["undo", "after", "recompute"])

    def test_not_after_something_else_has_happened(self) -> None:
        self.toast.show(self.doc, "one")
        self.doc.UndoCount = 4
        self.assertFalse(self.toast.undo())
        self.assertEqual(self.doc.log, [])

    def test_not_once_it_has_gone(self) -> None:
        self.toast.show(self.doc, "one")
        self.toast.dismissed()
        self.assertFalse(self.toast.undo())

    def test_the_undo_button_undoes(self) -> None:
        self.toast.show(self.doc, "one")
        self.root().actionRequested.emit(0)
        self.assertEqual(self.doc.log, ["undo", "recompute"])

    def test_a_message_with_nothing_to_undo_has_no_undo(self) -> None:
        self.toast.show(self.doc, "one")
        APP.processEvents()
        with_undo = self.toast._widget.width()
        self.toast.show(self.doc, "one", undoable=False)
        APP.processEvents()
        self.assertEqual(self.buttons(), [])
        self.assertLess(self.toast._widget.width(), with_undo)
        self.assertFalse(self.toast.undo())
        self.assertEqual(self.doc.log, [])

    def test_further_buttons_follow_undo_and_do_what_they_say(self) -> None:
        used: list[str] = []
        self.toast.show(self.doc, "one", actions=[
            ("Edit", lambda: used.append("edit")),
            ("Repair", lambda: used.append("repair"))])
        APP.processEvents()
        self.assertEqual(self.buttons(), ["Undo", "Edit", "Repair"])
        self.root().actionRequested.emit(2)
        self.assertEqual((used, self.doc.log), (["repair"], []))
        self.assertFalse(self.toast._widget.isVisible())
        self.assertFalse(self.toast.undo())

    def test_a_sticky_one_stays(self) -> None:
        self.toast.show(self.doc, "one", undoable=False, sticky=True)
        self.root().setProperty("stay", 1)
        deadline = QtCore.QDeadlineTimer(300)
        while not deadline.hasExpired():
            APP.processEvents()
        self.assertTrue(self.toast._widget.isVisible())

    def test_it_goes_by_itself_and_takes_undo_with_it(self) -> None:
        self.toast.show(self.doc, "one")
        self.root().setProperty("stay", 1)
        self.root().show("one")
        deadline = QtCore.QDeadlineTimer(2000)
        while self.toast._widget.isVisible() and not deadline.hasExpired():
            APP.processEvents()
        self.assertFalse(self.toast._widget.isVisible())
        self.assertFalse(self.toast.undo())

    def test_it_goes_when_another_view_becomes_active(self) -> None:
        self.toast.show(self.doc, "one")
        self.view = QtWidgets.QWidget()
        self.toast._view_changed()
        self.assertFalse(self.toast.undo())

    def test_without_a_view_it_goes_to_the_report_view(self) -> None:
        self.view = None
        self.toast.show(self.doc, "one")
        self.assertEqual(PRINTED, ["Nxt: one\n"])
        self.assertFalse(self.toast.undo())


if __name__ == "__main__":
    unittest.main(verbosity=2)
