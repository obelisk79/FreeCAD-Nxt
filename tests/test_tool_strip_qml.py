"""The tool strip's QML, offscreen, driven by the real bridge.

Checks that every entry is drawn (commands, separators, buttons, the
selector), that the strip wraps rather than clipping in a narrow window,
that a click runs its command a frame later, that a split dropdown's
arrow asks for its menu, and that a choice switches the selector.

Run with: python3 tests/test_tool_strip_qml.py
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fakes  # noqa: E402

fakes.install()

from PySide6 import QtCore, QtQuick, QtWidgets  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from test_tool_strip import OWN, WORKBENCH, Window  # noqa: E402

from freecad.nxt.toolbars import layouts  # noqa: E402
from freecad.nxt.toolbars.bridge import ToolStripBridge  # noqa: E402
from freecad.nxt.ui.theme import Theme  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
QML = ROOT / "freecad" / "nxt" / "resources" / "qml"
BAD = ("binding loop", "is not defined", "cannot read property",
       "unable to assign", "typeerror", "referenceerror", "cannot assign",
       "is not a function", "required property", "cannot override",
       "insufficient arguments", "too many arguments")
WIDE, NARROW = 1200, 120
problems: list[str] = []


def _handler(_mode: Any, _context: Any, message: str) -> None:
    if any(token in str(message).lower() for token in BAD):
        problems.append(str(message))


QtCore.qInstallMessageHandler(_handler)


def settle(seconds: float = 0.15) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        APP.processEvents()
        QTest.qWait(10)


#: Drag ghosts: drawn like strip items, but not ones.
GHOST = "dragGhost"


def items_of(item: Any, name: str) -> list[Any]:
    found = []
    for child in item.childItems():
        if child.metaObject().className().startswith(name) \
                and child.objectName() != GHOST:
            found.append(child)
        found += items_of(child, name)
    return found


class StripView(unittest.TestCase):
    def setUp(self) -> None:
        problems.clear()
        self.window = Window()
        layouts.save(WORKBENCH, None)
        self.bridge = ToolStripBridge(self.window.main, OWN,
                                      lambda _area, p: p, lambda: WORKBENCH)
        self.bridge.rebuild()
        self.view = QtQuick.QQuickView()
        self.view.engine().addImportPath(str(QML))
        context = self.view.rootContext()
        self.theme = Theme()
        context.setContextProperty("theme", self.theme)
        context.setContextProperty("strip", self.bridge)
        context.setContextProperty("area", "top")
        self.view.setResizeMode(
            QtQuick.QQuickView.ResizeMode.SizeRootObjectToView)
        self.view.setSource(QtCore.QUrl.fromLocalFile(
            str(QML / "Nxt" / "Toolbar" / "ToolStrip.qml")))
        self.view.resize(WIDE, 60)
        self.view.show()
        settle()
        self.root = self.view.rootObject()

    def edit(self) -> None:
        """Edit mode, the view grown to fit as the strip's host does."""
        self.bridge.setEditing(True)
        settle(0.3)
        self.view.resize(WIDE, round(self.root.property("implicitHeight")))
        settle(0.3)

    def tearDown(self) -> None:
        self.view.close()
        self.view.deleteLater()
        settle()
        self.bridge.stop()
        self.window.close()
        self.assertEqual(problems, [])

    def tools(self) -> list[Any]:
        return items_of(self.root, "ToolItem")

    def click(self, item: Any, x_fraction: float = 0.3) -> None:
        point = item.mapToScene(QtCore.QPointF(
            item.width() * x_fraction, item.height() / 2)).toPoint()
        QTest.mouseClick(self.view, QtCore.Qt.MouseButton.LeftButton,
                         QtCore.Qt.KeyboardModifier.NoModifier, point)
        settle()

    def test_every_entry_drawn(self) -> None:
        self.assertEqual(len(self.tools()), 7)
        self.assertEqual(len(items_of(self.root, "StripSeparator")), 4)
        self.assertEqual(len(items_of(self.root, "ChoiceBar")), 1)

    def test_narrow_window_wraps(self) -> None:
        one_row = self.root.property("implicitHeight")
        self.view.resize(NARROW, 60)
        settle()
        self.assertGreater(self.root.property("implicitHeight"), one_row)

    def test_click_runs_the_command(self) -> None:
        self.click(self.tools()[0])
        self.assertEqual(self.window.fired, ["&New"])

    def test_split_arrow_opens_the_menu(self) -> None:
        fillet = next(t for t in self.tools()
                      if t.property("dropdown") == "split")
        with mock.patch.object(QtWidgets.QMenu, "popup") as popup:
            self.click(fillet, x_fraction=0.95)
        popup.assert_called_once()
        self.assertEqual(self.window.fired, [])

    def test_choice_switches_the_selector(self) -> None:
        bar = items_of(self.root, "ChoiceBar")[0]
        pills = [p for p in items_of(bar, "Pill") if p.isVisible()]
        self.assertEqual([p.property("label") for p in pills],
                         ["Part Design", "Sketcher"])
        self.click(pills[1], x_fraction=0.5)
        self.assertEqual(self.window.tabs.currentIndex(), 1)

    def texts(self) -> list[str]:
        model = self.bridge.model
        role = {v.data().decode(): k
                for k, v in model.roleNames().items()}["text"]
        return [model.data(model.index(r), role) or "|"
                for r in range(model.rowCount())]

    def drag(self, item: Any, to: QtCore.QPoint) -> None:
        start = item.mapToScene(QtCore.QPointF(
            item.width() / 2, item.height() / 2)).toPoint()
        QTest.mousePress(self.view, QtCore.Qt.MouseButton.LeftButton,
                         QtCore.Qt.KeyboardModifier.NoModifier, start)
        steps = 8
        for step in range(1, steps + 1):
            point = start + (to - start) * step / steps
            QTest.mouseMove(self.view, point)
            settle(0.02)
        QTest.mouseRelease(self.view, QtCore.Qt.MouseButton.LeftButton,
                           QtCore.Qt.KeyboardModifier.NoModifier, to)
        settle()

    def test_pen_enters_edit_mode_and_escape_leaves(self) -> None:
        pen = [b for b in items_of(self.root, "IconButton")
               if b.isVisible() and b.property("tip") == "Edit the toolbar"]
        self.click(pen[0], x_fraction=0.5)
        self.assertTrue(self.bridge.property("editing"))
        QTest.keyClick(self.view, QtCore.Qt.Key.Key_Escape)
        settle()
        self.assertFalse(self.bridge.property("editing"))

    def test_drag_reorders_and_does_not_run(self) -> None:
        self.edit()
        tools = self.tools()
        target = tools[2].mapToScene(QtCore.QPointF(
            tools[2].width() * 0.9, tools[2].height() / 2)).toPoint()
        self.drag(tools[0], target)
        self.assertEqual(self.texts()[:4], ["Open", "|", "Save", "New"])
        self.assertEqual(self.window.fired, [])
        self.assertEqual(layouts.load(WORKBENCH).areas["top"][3], "&New")

    def test_drop_below_the_strip_removes(self) -> None:
        self.edit()
        first = self.tools()[0]
        below = QtCore.QPoint(
            round(first.mapToScene(QtCore.QPointF(0, 0)).x()) + 5,
            round(self.root.height()) - 10)
        self.drag(first, below)
        self.assertNotIn("New", self.texts())

    def open_drawer(self) -> list[Any]:
        self.edit()
        drawer = items_of(self.root, "CommandDrawer")[0]
        return [t for t in items_of(drawer, "Tile")
                if t.property("key") and t.isVisible()]

    def tile(self, key: str) -> Any:
        return next(t for t in self.open_drawer()
                    if t.property("key") == key)

    def test_drawer_lists_commands(self) -> None:
        keys = {t.property("key") for t in self.open_drawer()}
        self.assertIn("Sketcher_CreateCircle", keys)
        self.assertIn("|", keys)

    def test_double_click_adds_to_the_end(self) -> None:
        circle = self.tile("Sketcher_CreateCircle")
        point = circle.mapToScene(QtCore.QPointF(
            circle.width() / 2, circle.height() / 2)).toPoint()
        QTest.mouseDClick(self.view, QtCore.Qt.MouseButton.LeftButton,
                          QtCore.Qt.KeyboardModifier.NoModifier, point)
        settle()
        self.assertEqual(self.texts()[-1], "Circle")

    def test_drag_from_the_drawer_places_it(self) -> None:
        circle = self.tile("Sketcher_CreateCircle")
        first = self.tools()[0]
        target = first.mapToScene(QtCore.QPointF(
            first.width() / 4, first.height() / 2)).toPoint()
        self.drag(circle, target)
        self.assertEqual(self.texts()[0], "Circle")
        self.assertEqual(layouts.load(WORKBENCH).areas["top"][0],
                         "Sketcher_CreateCircle")

    def test_drag_back_onto_the_drawer_removes(self) -> None:
        tiles = self.open_drawer()
        first = self.tools()[0]
        on_drawer = tiles[-1].mapToScene(QtCore.QPointF(5, 5)).toPoint()
        self.drag(first, on_drawer)
        self.assertNotIn("New", self.texts())

    def group_item(self) -> Any:
        return next(t for t in self.tools() if t.property("kind") == "group")

    def middle(self, item: Any) -> QtCore.QPoint:
        return item.mapToScene(QtCore.QPointF(
            item.width() / 2, item.height() / 2)).toPoint()

    def make_group(self, *keys: str) -> None:
        self.edit()
        row = self.bridge.insertGroup(0)
        for key in keys:
            self.bridge.addToGroup(key, row)
        settle(0.3)

    def test_new_group_tile_adds_a_group_shown_while_editing(self) -> None:
        tile = self.tile("+group")
        QTest.mouseDClick(self.view, QtCore.Qt.MouseButton.LeftButton,
                          QtCore.Qt.KeyboardModifier.NoModifier,
                          self.middle(tile))
        settle()
        self.assertTrue(self.group_item().isVisible())

    def test_command_dropped_on_a_group_goes_in(self) -> None:
        self.make_group("PartDesign_Pocket")
        circle = self.tile("Sketcher_CreateCircle")
        self.drag(circle, self.middle(self.group_item()))
        model = self.bridge.model
        role = {v.data().decode(): k
                for k, v in model.roleNames().items()}["members"]
        self.assertEqual(model.data(model.index(0), role), 2)
        self.assertNotIn("Circle", self.texts()[1:])

    def test_click_opens_the_group_editor_and_drag_reorders(self) -> None:
        self.make_group("PartDesign_Pocket", "Sketcher_CreateCircle")
        self.click(self.group_item(), x_fraction=0.5)
        self.assertEqual(self.bridge.property("editedGroup"), 0)
        editor = items_of(self.root, "GroupEditor")[0]
        self.assertTrue(editor.isVisible())
        tiles = [t for t in items_of(editor, "QQuickRectangle")
                 if t.property("key")]
        self.assertEqual([t.property("key") for t in tiles],
                         ["PartDesign_Pocket", "Sketcher_CreateCircle"])
        second = tiles[1]
        beyond = second.mapToScene(QtCore.QPointF(
            second.width() * 0.8, second.height() / 2)).toPoint()
        self.drag(tiles[0], beyond)
        self.assertEqual(
            [m["key"] for m in self.bridge.property("groupMembers")],
            ["Sketcher_CreateCircle", "PartDesign_Pocket"])

    def kinds(self) -> list[str]:
        model = self.bridge.model
        role = {v.data().decode(): k
                for k, v in model.roleNames().items()}["kind"]
        return [model.data(model.index(r), role)
                for r in range(model.rowCount())]

    def past_first_row(self) -> QtCore.QPoint:
        """Empty space to the right of the first row's last item."""
        first = self.tools()[0]
        flow = first.parentItem()
        return flow.mapToScene(QtCore.QPointF(
            flow.width() - 2, first.y() + first.height() / 2)).toPoint()

    def test_drop_past_a_rows_last_item_ends_the_row(self) -> None:
        self.bridge.moveToNewRow(self.texts().index("Pad"), -1)
        self.edit()
        self.drag(self.tools()[0], self.past_first_row())
        texts, kinds = self.texts(), self.kinds()
        row = texts.index("New")
        self.assertEqual(kinds[row + 1], "break")
        self.assertNotEqual(kinds[row - 1], "break")

    def test_row_end_bar_spans_the_strip_while_edited(self) -> None:
        self.bridge.moveToNewRow(self.texts().index("Pad"), -1)
        self.edit()
        bar = items_of(self.root, "StripBreak")[0]
        self.assertEqual(bar.width(), bar.parentItem().width())

    def test_drop_on_a_rows_end_starts_a_new_row(self) -> None:
        self.bridge.moveToNewRow(self.texts().index("Pad"), -1)
        self.edit()
        self.drag(self.tools()[0],
                  self.middle(items_of(self.root, "StripBreak")[0]))
        texts, kinds = self.texts(), self.kinds()
        row = texts.index("New")
        self.assertEqual(kinds[row - 1], "break")
        self.assertEqual(kinds[row + 1], "break")

    def test_first_row_has_its_own_size(self) -> None:
        self.bridge.moveToNewRow(self.texts().index("Pad"), -1)
        self.bridge.setIconSize(16)
        self.bridge.setOtherIconSize(32)
        self.addCleanup(self.bridge.setIconSize, 0)
        self.addCleanup(self.bridge.setOtherIconSize, 0)
        settle()
        sizes = {t.property("tip"): t.height() for t in self.tools()}
        self.assertLess(sizes["New"], sizes["Pad"])

    def test_drop_after_the_last_row_starts_one(self) -> None:
        self.edit()
        zones = items_of(self.root, "StripBreak")
        end_zone = zones[-1]
        self.drag(self.tools()[0], self.middle(end_zone))
        self.assertEqual(self.kinds()[-2], "break")
        self.assertEqual(self.texts()[-1], "New")

    def side_tools(self, editing: bool) -> list[QtQuick.QQuickItem]:
        for _ in range(3):
            self.bridge.moveAcross("top", 0, "left", -1)
        self.bridge.setEditing(editing)
        return list(items_of(self.side_view().rootObject(), "ToolItem"))

    def side_view(self) -> QtQuick.QQuickView:
        side = QtQuick.QQuickView()
        self.addCleanup(settle)
        self.addCleanup(side.deleteLater)
        self.addCleanup(side.close)
        side.engine().addImportPath(str(QML))
        context = side.rootContext()
        context.setContextProperty("theme", self.theme)
        context.setContextProperty("strip", self.bridge)
        context.setContextProperty("area", "left")
        side.setResizeMode(QtQuick.QQuickView.ResizeMode.SizeRootObjectToView)
        side.setSource(QtCore.QUrl.fromLocalFile(
            str(QML / "Nxt" / "Toolbar" / "ToolStrip.qml")))
        side.resize(120, 400)
        side.show()
        settle()
        return side

    def left_texts(self) -> list[str]:
        model = self.bridge.modelOf("left")
        role = {v.data().decode(): k
                for k, v in model.roleNames().items()}["text"]
        return [model.data(model.index(r), role)
                for r in range(model.rowCount())]

    def test_carried_item_drawn_on_the_strip_under_it(self) -> None:
        self.edit()
        side = self.side_view().rootObject()
        self.bridge.carryKey("Sketcher_CreateCircle", "", "Circle")
        self.bridge.carriedOver.emit("left", 20.0, 20.0)
        settle()
        ghosts = [g for g in side.findChildren(QtQuick.QQuickItem)
                  if g.objectName() == GHOST and g.isVisible()]
        self.assertEqual(len(ghosts), 1)
        self.bridge.carriedDropped.emit("left", 20.0, 20.0)
        settle()
        self.assertEqual(self.left_texts(), ["Circle"])
        self.assertFalse(any(g.isVisible() for g in ghosts))

    def test_drag_out_of_the_view_lands_on_another_strip(self) -> None:
        self.edit()
        self.side_view()
        self.bridge._locate = lambda point: ("left", QtCore.QPointF(20, 20)) \
            if point.y() > self.view.height() else None
        save = next(t for t in self.tools() if t.property("tip") == "Save")
        below = QtCore.QPoint(self.middle(save).x(), self.view.height() + 40)
        self.drag(save, below)
        self.assertEqual(self.left_texts(), ["Save"])
        self.assertNotIn("Save", self.texts())

    def assert_stacked(self, tools: list[QtQuick.QQuickItem]) -> None:
        self.assertEqual([t.property("tip") for t in tools],
                         ["New", "Open", "Save"])
        self.assertEqual(tools[0].x(), tools[1].x())
        self.assertLess(tools[0].y(), tools[1].y())

    def test_side_strip_stacks_its_items(self) -> None:
        self.assert_stacked(self.side_tools(editing=False))

    def test_side_strip_stacks_them_while_edited(self) -> None:
        self.assert_stacked(self.side_tools(editing=True))


if __name__ == "__main__":
    unittest.main()
