"""Borrowing FreeCAD's Property editor into the inspector, and giving it back.

Runs offscreen against a stand-in main window, with a stand-in editor in
each of the places FreeCAD may keep the real one. Needs PySide6.

    python3 tests/test_property_inspector.py
"""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6 import QtCore, QtWidgets  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

App = types.ModuleType("FreeCAD")
App.Console = types.SimpleNamespace(PrintError=lambda _m: None,
                                    PrintMessage=lambda _m: None)
App.getUserAppDataDir = lambda: "/tmp/"


class FakeParams:
    """FreeCAD's parameter group, kept in a dict."""

    store: dict[str, object] = {}

    def __getattr__(self, name: str):
        if name.startswith("Get"):
            return lambda key, default: self.store.get(key, default)
        if name.startswith("Set"):
            return lambda key, value: self.store.__setitem__(key, value)
        raise AttributeError(name)


App.ParamGet = lambda _group: FakeParams()
Gui = types.ModuleType("FreeCADGui")
SELECTION = [types.SimpleNamespace(Label="Pad"),
             types.SimpleNamespace(Label="Pocket")]
Gui.Selection = types.SimpleNamespace(getSelection=lambda: SELECTION)
sys.modules.update(FreeCAD=App, FreeCADGui=Gui)

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
MAIN = QtWidgets.QMainWindow()
MAIN.resize(1200, 800)
Gui.getMainWindow = lambda: MAIN

panel_stub = types.ModuleType("freecad.nxt.tree.panel")
panel_stub.instance = lambda: None
sys.modules["freecad.nxt.tree.panel"] = panel_stub

import freecad.nxt.tree as tree_pkg  # noqa: E402

tree_pkg.panel = panel_stub

from freecad.nxt import property_inspector  # noqa: E402


class FakeView(QtWidgets.QWidget):
    """Stands in for Gui::PropertyView; matched by class name."""


property_inspector.PROPERTY_VIEW_CLASS = "FakeView"


def settle() -> None:
    APP.processEvents()


class _Harness(unittest.TestCase):

    def setUp(self) -> None:
        MAIN.show()
        self.view = FakeView()

    def tearDown(self) -> None:
        FakeParams.store.clear()
        property_inspector.shutdown()
        settle()
        for dock in MAIN.findChildren(QtWidgets.QDockWidget):
            MAIN.removeDockWidget(dock)
            dock.setParent(None)
        self.view.setParent(None)

    def dock(self, hidden: bool = False) -> QtWidgets.QDockWidget:
        dock = QtWidgets.QDockWidget("Property view", MAIN)
        dock.setObjectName("Property view")
        dock.setWidget(self.view)
        MAIN.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        if hidden:
            dock.hide()
        settle()
        return dock

    def round_trip(self) -> None:
        property_inspector.open_inspector(100, 100)
        settle()
        self.assertTrue(property_inspector.is_open())
        self.assertTrue(property_inspector._inspector.isAncestorOf(self.view))
        property_inspector.close()
        settle()
        self.assertIsNone(property_inspector._inspector._home)


class BorrowTests(_Harness):

    def test_from_a_dock(self) -> None:
        dock = self.dock()
        self.round_trip()
        self.assertIs(dock.widget(), self.view)
        self.assertFalse(self.view.isHidden())

    def test_from_a_hidden_dock_keeps_its_own_visibility(self) -> None:
        dock = self.dock(hidden=True)
        self.round_trip()
        self.assertIs(dock.widget(), self.view)
        self.assertFalse(self.view.isHidden())

    def test_from_a_grid_inside_a_dock(self) -> None:
        """FreeCAD's own arrangement, as probe() reported it.

        Gui::PropertyView sits in a Gui::DockWnd::PropertyDockView, which
        lays it out with a QGridLayout, inside the Property view dock.
        """
        holder = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.view, 0, 0)
        dock = QtWidgets.QDockWidget("Property view", MAIN)
        dock.setObjectName("Property view")
        dock.setWidget(holder)
        MAIN.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
                           dock)
        settle()
        self.round_trip()
        self.assertIs(self.view.parentWidget(), holder)
        self.assertEqual(grid.getItemPosition(grid.indexOf(self.view)),
                         (0, 0, 1, 1))
        self.assertFalse(self.view.isHidden())

    def test_from_a_splitter(self) -> None:
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(QtWidgets.QTreeView())
        splitter.addWidget(self.view)
        holder = QtWidgets.QDockWidget("Combo View", MAIN)
        holder.setWidget(splitter)
        MAIN.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
                           holder)
        self.round_trip()
        self.assertEqual(splitter.indexOf(self.view), 1)

    def test_from_a_tab_keeps_the_current_page(self) -> None:
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(QtWidgets.QLabel("model"), "Model")
        tabs.addTab(self.view, "Property")
        tabs.addTab(QtWidgets.QLabel("tasks"), "Tasks")
        tabs.setCurrentIndex(2)
        holder = QtWidgets.QDockWidget("Combo View", MAIN)
        holder.setWidget(tabs)
        MAIN.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
                           holder)
        self.round_trip()
        self.assertEqual(tabs.indexOf(self.view), 1)
        self.assertEqual(tabs.tabText(1), "Property")
        self.assertEqual(tabs.currentIndex(), 2)

    def test_shutdown_gives_it_back(self) -> None:
        """A reload shuts the inspector down; the editor must go home first."""
        dock = self.dock()
        property_inspector.open_inspector()
        settle()
        property_inspector.shutdown()
        settle()
        self.assertIs(dock.widget(), self.view)
        property_inspector.close()       # a second return must be harmless
        self.assertIs(dock.widget(), self.view)

    def test_title_names_the_selection(self) -> None:
        self.dock()
        property_inspector.open_inspector()
        self.assertEqual(property_inspector._inspector._title.text(),
                         "Pad, Pocket · 2 selected")


class ClickAwayTests(_Harness):

    def test_click_inside_keeps_it_open(self) -> None:
        self.dock()
        property_inspector.open_inspector()
        settle()
        QTest.mouseClick(property_inspector._inspector._title,
                         QtCore.Qt.MouseButton.LeftButton)
        settle()
        self.assertTrue(property_inspector.is_open())

    def test_click_away_closes_and_returns_it(self) -> None:
        dock = self.dock()
        property_inspector.open_inspector()
        settle()
        other = QtWidgets.QPushButton("elsewhere", MAIN)
        other.move(900, 700)
        other.show()
        QTest.mouseClick(other, QtCore.Qt.MouseButton.LeftButton)
        settle()
        self.assertFalse(property_inspector.is_open())
        self.assertIs(dock.widget(), self.view)
        other.setParent(None)

    def test_pinned_survives_a_click_away(self) -> None:
        self.dock()
        property_inspector.open_inspector()
        property_inspector._inspector._pin.setChecked(True)
        other = QtWidgets.QPushButton("elsewhere", MAIN)
        other.move(900, 700)
        other.show()
        QTest.mouseClick(other, QtCore.Qt.MouseButton.LeftButton)
        settle()
        self.assertTrue(property_inspector.is_open())
        other.setParent(None)


def drag(widget: QtWidgets.QWidget, start: QtCore.QPoint,
         delta: QtCore.QPoint) -> None:
    QTest.mousePress(widget, QtCore.Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(widget, start + delta)
    QTest.mouseRelease(widget, QtCore.Qt.MouseButton.LeftButton,
                       pos=start + delta)
    settle()


class MoveTests(_Harness):

    def open(self) -> property_inspector.PropertyInspector:
        self.dock()
        property_inspector.open_inspector(300, 200)
        settle()
        return property_inspector._inspector

    def test_it_opens_just_past_a_given_edge(self) -> None:
        """Overlay mode passes the row pill's right edge."""
        self.dock()
        property_inspector.open_inspector(400, 150)
        settle()
        corner = MAIN.mapFromGlobal(QtCore.QPoint(400, 150))
        self.assertEqual(property_inspector._inspector.pos(),
                         corner + QtCore.QPoint(
                             property_inspector.INSPECTOR_GAP, 0))

    def test_with_no_edge_it_lines_up_with_the_dock(self) -> None:
        """Docked mode passes no edge; the dock's border is used."""
        self.dock()
        property_inspector.open_inspector(None, 150)
        settle()
        self.assertEqual(property_inspector._inspector.x(),
                         property_inspector.INSPECTOR_MARGIN)

    def test_the_title_drags_the_card(self) -> None:
        inspector = self.open()
        before = inspector.pos()
        drag(inspector._title, QtCore.QPoint(20, 8), QtCore.QPoint(120, 60))
        self.assertEqual(inspector.pos(), before + QtCore.QPoint(120, 60))
        self.assertTrue(property_inspector.is_open())

    def test_it_cannot_be_dragged_off_the_window(self) -> None:
        inspector = self.open()
        drag(inspector._title, QtCore.QPoint(20, 8), QtCore.QPoint(5000, 5000))
        self.assertTrue(MAIN.rect().contains(inspector.geometry()))

    def test_an_unpinned_move_is_not_remembered(self) -> None:
        inspector = self.open()
        drag(inspector._title, QtCore.QPoint(20, 8), QtCore.QPoint(50, 50))
        self.assertNotIn("InspectorX", FakeParams.store)

    def test_a_pinned_card_reopens_where_it_was_left(self) -> None:
        inspector = self.open()
        inspector._pin.setChecked(True)
        drag(inspector._title, QtCore.QPoint(20, 8), QtCore.QPoint(200, 90))
        inspector.resize(360, 420)
        left = inspector.geometry()
        property_inspector.close()
        property_inspector.open_inspector(10, 10)
        settle()
        self.assertEqual(inspector.geometry(), left)
        self.assertTrue(FakeParams.store["InspectorPinned"])

    def test_the_grip_resizes_the_card_not_the_window(self) -> None:
        inspector = self.open()
        window = MAIN.size()
        grip = inspector.findChild(QtWidgets.QSizeGrip)
        before = inspector.size()
        drag(grip, QtCore.QPoint(4, 4), QtCore.QPoint(40, 30))
        self.assertEqual(MAIN.size(), window)
        self.assertGreater(inspector.width(), before.width())

    def test_a_smaller_window_pulls_the_card_back_inside(self) -> None:
        inspector = self.open()
        inspector.move(800, 300)
        MAIN.resize(700, 600)
        settle()
        self.assertTrue(MAIN.rect().contains(inspector.geometry()))
        MAIN.resize(1200, 800)
        settle()


class FakeInspectorBridge(QtCore.QObject):
    nativeRequested = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False


class InspectorPageTests(_Harness):
    """The QML page, with FreeCAD's editor borrowed only on request."""

    def setUp(self) -> None:
        super().setUp()
        self.bridge = FakeInspectorBridge()

        def make(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
            page = QtWidgets.QLabel("inspector", parent)
            page.nxt_bridge = self.bridge
            return page

        self._real = property_inspector._make_inspector
        property_inspector._make_inspector = make

    def tearDown(self) -> None:
        property_inspector._make_inspector = self._real
        super().tearDown()

    def test_opening_shows_the_inspector_and_borrows_nothing(self) -> None:
        dock = self.dock()
        property_inspector.open_inspector(100, 100)
        settle()
        self.assertIs(dock.widget(), self.view)
        self.assertTrue(self.bridge.running)
        self.assertIsNone(property_inspector._inspector._home)

    def test_edit_borrows_and_back_returns(self) -> None:
        dock = self.dock()
        property_inspector.open_inspector(100, 100)
        self.bridge.nativeRequested.emit("ThreadData")
        settle()
        inspector = property_inspector._inspector
        self.assertTrue(inspector.isAncestorOf(self.view))
        self.assertFalse(self.bridge.running)
        self.assertFalse(inspector._back.isHidden())
        inspector._back.click()
        settle()
        self.assertIs(dock.widget(), self.view)
        self.assertTrue(self.bridge.running)
        self.assertTrue(inspector._back.isHidden())


if __name__ == "__main__":
    unittest.main(verbosity=2)
