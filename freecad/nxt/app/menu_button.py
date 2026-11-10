"""FreeCAD's menus behind one button: its logo, first on the toolbars.

The menu bar is hidden while the button is in use; its shortcuts keep
working. Not on macOS, whose menu bar is the system's, outside the
window. Turned off in the preferences, the menu bar comes back.
"""

from __future__ import annotations

import sys
from typing import Any

import FreeCADGui as Gui

from ..core import settings
from ..core.qt import QtCore, QtWidgets
from .i18n import translate

TOOLBAR = "NxtMenuToolbar"
SETTING = "MenuInToolbar"

_button: MenuButton | None = None


def supported() -> bool:
    """Whether the menus may move into a button here (not on macOS)."""
    return sys.platform != "darwin"


class MenuButton(QtCore.QObject):
    """The logo button holding the menu bar's menus, and its toolbar."""

    def __init__(self, main: QtWidgets.QMainWindow) -> None:
        super().__init__(main)
        self._main = main
        self.toolbar = QtWidgets.QToolBar(translate("Nxt", "Menu"), main)
        self.toolbar.setObjectName(TOOLBAR)
        # Hidden from the toolbars' own menu: hiding it would leave no menu.
        self.toolbar.toggleViewAction().setVisible(False)
        # Fixed first: never dragged elsewhere, locked or not.
        self.toolbar.setMovable(False)
        self.menu = QtWidgets.QMenu(self.toolbar)
        self.menu.aboutToShow.connect(self._fill)
        button = QtWidgets.QToolButton(self.toolbar)
        button.setIcon(main.windowIcon())
        button.setToolTip(translate("Nxt", "Menu"))
        button.setMenu(self.menu)
        button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        # No arrow: the logo alone says what it is.
        button.setStyleSheet(
            "QToolButton::menu-indicator { image: none; width: 0; }")
        self.toolbar.addWidget(button)

    def _fill(self) -> None:
        """The menu bar's menus, as they are now (workbenches change them)."""
        self.menu.clear()
        self.menu.addActions(self._main.menuBar().actions())

    def apply(self) -> None:
        on = bool(settings.get(SETTING))
        if on:
            self._place_first()
        self.toolbar.setVisible(on)
        self._main.menuBar().setVisible(not on)

    def _place_first(self) -> None:
        """Put the toolbar first on the top row, if it is not already.

        FreeCAD restores its saved toolbar layout on each workbench
        switch, which can move this one anywhere.
        """
        top = QtCore.Qt.ToolBarArea.TopToolBarArea
        others = [t for t in self._main.findChildren(QtWidgets.QToolBar)
                  if t is not self.toolbar and t.isVisible()
                  and self._main.toolBarArea(t) == top]
        first = min(others, key=lambda t: (t.y(), t.x()), default=None)
        if first is None:
            if self._main.toolBarArea(self.toolbar) != top:
                self._main.addToolBar(top, self.toolbar)
            return
        if (self._main.toolBarArea(self.toolbar) == top
                and (self.toolbar.y(), self.toolbar.x())
                <= (first.y(), first.x())):
            return
        self._main.insertToolBar(first, self.toolbar)

    def remove(self) -> None:
        self._main.menuBar().setVisible(True)
        self._main.removeToolBar(self.toolbar)
        self.toolbar.deleteLater()


def apply() -> None:
    """Bring the button and the menu bar in line with the setting."""
    if _button is not None:
        _button.apply()


def _later(*_args: Any) -> None:
    # FreeCAD sets up a workbench's toolbars after the signal fires,
    # hiding any it does not list.
    QtCore.QTimer.singleShot(0, apply)


def install() -> None:
    global _button
    if not supported():
        return
    main = Gui.getMainWindow()
    old = main.findChild(QtWidgets.QToolBar, TOOLBAR)
    if old is not None:     # left by a reload of Nxt
        main.removeToolBar(old)
        old.deleteLater()
    _button = MenuButton(main)
    main.workbenchActivated.connect(_later)
    _later()


def remove() -> None:
    global _button
    if _button is None:
        return
    Gui.getMainWindow().workbenchActivated.disconnect(_later)
    _button.remove()
    _button = None
