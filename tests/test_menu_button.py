"""The menu button: menu shortcuts keep working with the menu bar hidden.

Issues #191 and #206: Qt fires no shortcut of an action whose only
widgets are menus of a hidden menu bar, so Delete deleted nothing.

Run with: QT_QPA_PLATFORM=offscreen python3 tests/test_menu_button.py
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
from PySide6.QtTest import QTest  # noqa: E402

from freecad.nxt.app import menu_button  # noqa: E402

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
DELETE = QtCore.Qt.Key.Key_Delete
CTRL = QtCore.Qt.KeyboardModifier.ControlModifier


class MenuShortcuts(unittest.TestCase):
    def setUp(self) -> None:
        self.main = QtWidgets.QMainWindow()
        self.main.setCentralWidget(QtWidgets.QWidget())
        self.fired: list[str] = []
        edit = self.main.menuBar().addMenu("Edit")
        self.delete = self._action(edit, "Delete", "Del")
        self._action(edit.addMenu("Select"), "All", "Ctrl+A")
        patcher = mock.patch.object(menu_button.settings, "get",
                                    return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.button = menu_button.MenuButton(self.main)
        self.main.show()
        self.button.apply()
        APP.processEvents()

    def tearDown(self) -> None:
        self.main.close()
        self.main.deleteLater()
        APP.processEvents()

    def _action(self, menu: QtWidgets.QMenu, name: str,
                key: str) -> QtGui.QAction:
        action = QtGui.QAction(name, self.main)
        action.setShortcut(key)
        action.triggered.connect(lambda: self.fired.append(name))
        menu.addAction(action)
        return action

    def _press(self) -> list[str]:
        self.fired.clear()
        target = self.main.centralWidget()
        QTest.keyClick(target, DELETE)
        QTest.keyClick(target, QtCore.Qt.Key.Key_A, CTRL)
        APP.processEvents()
        return self.fired

    def test_shortcuts_fire_with_menu_bar_hidden(self) -> None:
        self.assertFalse(self.main.menuBar().isVisible())
        self.assertEqual(self._press(), ["Delete", "All"])

    def test_menus_rebuilt_by_a_workbench_switch(self) -> None:
        self.main.menuBar().clear()
        menu = self.main.menuBar().addMenu("Part")
        self._action(menu, "Box", "Ctrl+B")
        self.button.apply()
        self.assertNotIn(self.delete, self.main.actions())
        self.fired.clear()
        QTest.keyClick(self.main.centralWidget(), QtCore.Qt.Key.Key_B, CTRL)
        self.assertEqual(self.fired, ["Box"])

    def test_nothing_left_lent_when_removed(self) -> None:
        self.button.remove()
        self.assertTrue(self.main.menuBar().isVisible())
        self.assertNotIn(self.delete, self.main.actions())
        self.assertEqual(self._press(), ["Delete", "All"])


if __name__ == "__main__":
    unittest.main()
