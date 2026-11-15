"""The tool strip's Python half: reading, covering and acting on toolbars.

Builds a main window with toolbars as FreeCAD leaves them: global and
workbench bars, a lingering hidden one, a dropdown command group, a
widget button with a menu, a workbench selector and a widget Nxt cannot
show.

Run with: QT_QPA_PLATFORM=offscreen python3 tests/test_tool_strip.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import fakes  # noqa: E402

fakes.install()

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from freecad.nxt.toolbars import models, source  # noqa: E402
from freecad.nxt.toolbars.bridge import ToolStripBridge  # noqa: E402
from freecad.nxt.toolbars.hider import ToolbarHider  # noqa: E402
from freecad.nxt.toolbars.source import Kind  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
OWN = ("NxtToolStrip",)
TOP = QtCore.Qt.ToolBarArea.TopToolBarArea
SPLIT = QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup


def settle() -> None:
    for _ in range(3):
        APP.processEvents()


class Window:
    """A main window with toolbars laid out as FreeCAD leaves them."""

    def __init__(self) -> None:
        self.main = QtWidgets.QMainWindow()
        self.main.setCentralWidget(QtWidgets.QWidget())
        self.fired: list[str] = []
        file_bar = self.bar("File")
        self.new = self.command(file_bar, "&New")
        self.command(file_bar, "Open")
        file_bar.addSeparator()
        self.command(file_bar, "Save")
        self.command(file_bar, "Hidden").setVisible(False)
        stale = self.bar("Sketcher")
        self.command(stale, "Line")
        stale.hide()
        part = self.bar("Part")
        self.pad = self.command(part, "Pad")
        self.pad.setCheckable(True)
        self.fillet = self.command(part, "Fillet")
        self.group_menu = QtWidgets.QMenu(part)
        self.group_menu.addAction("Chamfer")
        group_button = part.widgetForAction(self.fillet)
        group_button.setMenu(self.group_menu)
        group_button.setPopupMode(SPLIT)
        tray = self.bar("Tray")
        self.layer = QtWidgets.QPushButton("Layer 1")
        self.layer_menu = QtWidgets.QMenu(self.layer)
        self.layer.setMenu(self.layer_menu)
        self.widget(tray, self.layer)
        self.plain = QtWidgets.QPushButton("Style")
        self.plain.clicked.connect(lambda: self.fired.append("Style"))
        self.widget(tray, self.plain)
        self.widget(tray, QtWidgets.QSlider())
        selector = self.bar("Workbench")
        holder = QtWidgets.QWidget()
        self.tabs = QtWidgets.QTabBar(holder)
        for name in ("Part Design", "Sketcher"):
            self.tabs.addTab(name)
        self.widget(selector, holder)
        self.own = self.bar(OWN[0])
        self.own.addAction("Strip")
        self.main.show()
        settle()

    def bar(self, name: str) -> QtWidgets.QToolBar:
        toolbar = QtWidgets.QToolBar(name, self.main)
        toolbar.setObjectName(name)
        self.main.addToolBar(TOP, toolbar)
        return toolbar

    def command(self, bar: QtWidgets.QToolBar, text: str) -> QtGui.QAction:
        action = QtGui.QAction(text, self.main)
        action.triggered.connect(lambda: self.fired.append(text))
        bar.addAction(action)
        return action

    def widget(self, bar: QtWidgets.QToolBar,
               widget: QtWidgets.QWidget) -> None:
        action = QtWidgets.QWidgetAction(bar)
        action.setDefaultWidget(widget)
        bar.addAction(action)

    def close(self) -> None:
        self.main.close()
        self.main.deleteLater()
        settle()


class Reading(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Window()
        self.entries, self.unsupported = source.read(self.window.main, OWN)

    def tearDown(self) -> None:
        self.window.close()

    def labels(self) -> list[str]:
        return ["|" if e.kind is Kind.SEPARATOR
                else e.action.text() if e.kind is Kind.COMMAND
                else e.kind.value for e in self.entries]

    def test_shown_toolbars_flattened_with_a_separator_between(self) -> None:
        self.assertEqual(self.labels(), [
            "&New", "Open", "|", "Save", "|", "Pad", "Fillet", "|",
            "button", "button", "|", "choice"])

    def test_lingering_toolbars_and_hidden_actions_left_out(self) -> None:
        texts = self.labels()
        self.assertNotIn("Line", texts)
        self.assertNotIn("Hidden", texts)

    def test_own_toolbar_left_out(self) -> None:
        self.assertNotIn("Strip", self.labels())

    def test_dropdown_group_keeps_its_button(self) -> None:
        fillet = self.entries[self.labels().index("Fillet")]
        self.assertIs(fillet.widget.menu(), self.window.group_menu)

    def test_selector_proxied_by_its_tab_bar(self) -> None:
        self.assertIs(self.entries[-1].widget, self.window.tabs)

    def test_unshowable_widget_reported(self) -> None:
        self.assertEqual(self.unsupported, ["QSlider"])

    def test_separators_tidied(self) -> None:
        sep = source.SEPARATOR
        command = source.Entry(Kind.COMMAND)
        self.assertEqual(source.tidy([sep, command, sep, sep, command, sep]),
                         [command, sep, command])


class Hiding(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Window()
        self.hider = ToolbarHider(self.window.main, OWN)
        self.changes: list[bool] = []
        self.hider.toolbarsChanged.connect(lambda: self.changes.append(True))
        self.hider.install()
        settle()

    def tearDown(self) -> None:
        self.hider.remove()
        self.window.close()

    def bars(self) -> list[QtWidgets.QToolBar]:
        return [b for b in self.window.main.findChildren(QtWidgets.QToolBar)
                if b is not self.window.own]

    def test_covered_not_hidden(self) -> None:
        for bar in self.bars():
            self.assertEqual(bar.maximumSize(), QtCore.QSize(0, 0))
        part = self.window.main.findChild(QtWidgets.QToolBar, "Part")
        self.assertFalse(part.isHidden())
        self.assertTrue(part.toggleViewAction().isChecked())

    def test_own_toolbar_untouched(self) -> None:
        self.assertNotEqual(self.window.own.maximumSize(),
                            QtCore.QSize(0, 0))

    def test_toolbar_added_later_is_covered(self) -> None:
        late = self.window.bar("Late")
        settle()
        self.assertEqual(late.maximumSize(), QtCore.QSize(0, 0))
        self.assertTrue(self.changes)

    def test_changed_actions_announced(self) -> None:
        self.changes.clear()
        self.window.command(self.bars()[0], "Extra")
        self.assertTrue(self.changes)

    def test_removed_cover_restores_sizes(self) -> None:
        self.hider.remove()
        for bar in self.bars():
            self.assertNotEqual(bar.maximumSize(), QtCore.QSize(0, 0))


class Acting(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Window()
        self.global_point = QtCore.QPoint(5, 5)
        self.bridge = ToolStripBridge(self.window.main, OWN,
                                      lambda _p: self.global_point)
        self.model = self.bridge.model
        self.bridge.rebuild()

    def tearDown(self) -> None:
        self.bridge.stop()
        self.window.close()

    def row_of(self, text: str) -> int:
        role = self.role("text")
        for row in range(self.model.rowCount()):
            if self.model.data(self.model.index(row), role) == text:
                return row
        raise AssertionError(text)

    def role(self, name: str) -> int:
        names = {v.data().decode(): k
                 for k, v in self.model.roleNames().items()}
        return names[name]

    def value(self, row: int, name: str) -> object:
        return self.model.data(self.model.index(row), self.role(name))

    def test_rows_describe_commands(self) -> None:
        row = self.row_of("New")
        self.assertEqual(self.value(row, "kind"), "command")
        self.assertEqual(self.value(self.row_of("Fillet"), "dropdown"),
                         models.SPLIT)
        self.assertEqual(self.value(self.row_of("Layer 1"), "dropdown"),
                         models.INSTANT)

    def test_checked_state_follows_the_action(self) -> None:
        row = self.row_of("Pad")
        changed: list[int] = []
        self.model.dataChanged.connect(lambda a, _b: changed.append(a.row()))
        self.window.pad.setChecked(True)
        self.assertEqual(changed, [row])
        self.assertTrue(self.value(row, "checked"))

    def test_same_toolbars_no_reset(self) -> None:
        resets: list[bool] = []
        self.model.modelReset.connect(lambda: resets.append(True))
        self.bridge.rebuild()
        self.assertEqual(resets, [])

    def test_activate_runs_enabled_commands_only(self) -> None:
        self.bridge.activate(self.row_of("New"), 0.0, 0.0)
        self.window.new.setEnabled(False)
        self.bridge.activate(self.row_of("New"), 0.0, 0.0)
        self.assertEqual(self.window.fired, ["&New"])

    def test_activate_clicks_a_proxied_button(self) -> None:
        self.bridge.activate(self.row_of("Style"), 0.0, 0.0)
        self.assertEqual(self.window.fired, ["Style"])

    def test_menu_a_button_opens_itself_lands_at_the_item(self) -> None:
        menu = QtWidgets.QMenu()
        menu.addAction("Group")
        self.window.plain.clicked.connect(
            lambda: menu.popup(QtCore.QPoint(0, 0)))
        self.bridge.activate(self.row_of("Style"), 3.0, 4.0)
        self.assertEqual(menu.pos(), self.global_point)
        menu.close()

    def test_dropdown_opens_its_menu_at_the_item(self) -> None:
        with mock.patch.object(QtWidgets.QMenu, "popup") as popup:
            self.bridge.openMenu(self.row_of("Fillet"), 3.0, 4.0)
        popup.assert_called_once_with(self.global_point)

    def test_choose_switches_the_selector(self) -> None:
        row = self.model.rowCount() - 1
        self.bridge.choose(row, 1)
        self.assertEqual(self.window.tabs.currentIndex(), 1)
        self.assertEqual(self.value(row, "current"), 1)

    def test_mnemonics_dropped_from_labels(self) -> None:
        self.assertEqual(models.plain("&Save && Close"), "Save & Close")


if __name__ == "__main__":
    unittest.main()
