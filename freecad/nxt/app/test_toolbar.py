"""A toolbar of Nxt commands under test, shown in Part Design."""

from __future__ import annotations

import FreeCADGui as Gui

from ..core.qt import QtCore, QtGui, QtWidgets
from ..resources import ICONS

NAME = "NxtTesting"
TITLE = "Nxt Fillet/Chamfer"
WORKBENCH = "PartDesignWorkbench"
COMMANDS = (("Nxt_BlendFillet", "Nxt fillet", "NxtFillet.svg"),
            ("Nxt_BlendChamfer", "Nxt chamfer", "NxtChamfer.svg"))


def _toolbar() -> QtWidgets.QToolBar:
    window = Gui.getMainWindow()
    toolbar = window.findChild(QtWidgets.QToolBar, NAME)
    if toolbar is None:
        toolbar = window.addToolBar(TITLE)
        toolbar.setObjectName(NAME)
        for command, text, icon in COMMANDS:
            # Icons only, as FreeCAD's toolbars: the name is the tooltip.
            action = QtGui.QAction(
                QtGui.QIcon(str(ICONS / icon)), text, toolbar)
            action.setObjectName(command)
            action.triggered.connect(
                lambda _checked=False, name=command: Gui.runCommand(name))
            toolbar.addAction(action)
    return toolbar


def update(*_args: object) -> None:
    workbench = Gui.activeWorkbench()
    active = workbench is not None and workbench.name() == WORKBENCH
    _toolbar().setVisible(active)


def _later(*_args: object) -> None:
    QtCore.QTimer.singleShot(0, update)


def install() -> None:
    Gui.getMainWindow().workbenchActivated.connect(_later)
    _later()
