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
       "is not a function", "required property", "cannot override")
WIDE, NARROW = 900, 120
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


def items_of(item: Any, name: str) -> list[Any]:
    found = []
    for child in item.childItems():
        if child.metaObject().className().startswith(name):
            found.append(child)
        found += items_of(child, name)
    return found


class StripView(unittest.TestCase):
    def setUp(self) -> None:
        problems.clear()
        self.window = Window()
        layouts.save(WORKBENCH, None)
        self.bridge = ToolStripBridge(self.window.main, OWN,
                                      lambda p: p, lambda: WORKBENCH)
        self.bridge.rebuild()
        self.view = QtQuick.QQuickView()
        self.view.engine().addImportPath(str(QML))
        context = self.view.rootContext()
        self.theme = Theme()
        context.setContextProperty("theme", self.theme)
        context.setContextProperty("strip", self.bridge)
        self.view.setResizeMode(
            QtQuick.QQuickView.ResizeMode.SizeRootObjectToView)
        self.view.setSource(QtCore.QUrl.fromLocalFile(
            str(QML / "Nxt" / "Toolbar" / "ToolStrip.qml")))
        self.view.resize(WIDE, 60)
        self.view.show()
        settle()
        self.root = self.view.rootObject()

    def tearDown(self) -> None:
        self.view.close()
        self.view.deleteLater()
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
        row = items_of(bar, "QQuickRow")[0]
        second = [c for c in row.childItems()
                  if c.metaObject().className().startswith("QQuickItem")][1]
        self.click(second, x_fraction=0.5)
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
        self.bridge.setEditing(True)
        settle()
        tools = self.tools()
        target = tools[2].mapToScene(QtCore.QPointF(
            tools[2].width() * 0.9, tools[2].height() / 2)).toPoint()
        self.drag(tools[0], target)
        self.assertEqual(self.texts()[:4], ["Open", "|", "Save", "New"])
        self.assertEqual(self.window.fired, [])
        self.assertEqual(layouts.load(WORKBENCH).order[3], "&New")

    def test_drop_outside_removes(self) -> None:
        self.bridge.setEditing(True)
        settle()
        first = self.tools()[0]
        below = QtCore.QPoint(
            round(first.mapToScene(QtCore.QPointF(0, 0)).x()) + 5,
            round(self.root.height()) + 200)
        self.drag(first, below)
        self.assertNotIn("New", self.texts())


if __name__ == "__main__":
    unittest.main()
