"""The FreeCAD side of the menu: what commands say, and running them.

Nxt's own actions (`nxt:...`) need the tree's state and live on the bridge;
this module handles FreeCAD commands and view provider edit modes, and
opening FreeCAD's own menu when asked for it.
"""

from __future__ import annotations

import importlib
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .definitions import EDIT_MODES
from .present import CommandInfo

#: A command's prefix, and the module that registers it. A workbench's
#: commands exist only once its Gui module is imported - Sketcher's are
#: not there until Sketcher has been activated once - so the menu imports
#: it on first use, as FreeCAD's own toolbars do.
_GUI_MODULES = {
    "Sketcher": "SketcherGui",
    "PartDesign": "PartDesignGui",
    "Part": "PartGui",
}


def _command(name: str) -> Any:
    try:
        command = Gui.Command.get(name)
    except Exception:
        command = None
    module = _GUI_MODULES.get(name.split("_", 1)[0])
    if command is None and module:
        try:
            importlib.import_module(module)
            command = Gui.Command.get(name)
        except Exception:
            command = None
    return command


#: Commands the menu must never offer. Std_Expressions' isActive() - which
#: FreeCAD calls before running any command - updates the entries of its
#: own submenu, which exist only once FreeCAD has shown it somewhere; run
#: from anywhere else first, it crashes FreeCAD. Nxt has its own
#: expression actions (tree/menu_actions.py).
UNSAFE = frozenset({"Std_Expressions"})


def lookup(name: str) -> CommandInfo | None:
    """What FreeCAD says about a command, or None if it is not registered.

    None too for a command in UNSAFE, so no definition file can offer it.
    """
    if name in UNSAFE:
        return None
    command = _command(name)
    if command is None:
        return None
    try:
        info = command.getInfo()
    except Exception:
        return None
    active = is_active(command)
    label = str(info.get("menuText", name)).replace("&", "")
    return CommandInfo(label=label,
                       shortcut=str(info.get("shortcut", "") or ""),
                       active=active,
                       icon=name if info.get("pixmap") else "")


def is_active(command: Any) -> bool:
    """Whether FreeCAD would enable a command now; True when unsure.

    Only asked of a command whose action FreeCAD has already built. Some
    commands' isActive() updates the entries of their own submenu, and
    until that submenu exists the pointers it follows are null: calling
    Std_Expressions.isActive() before anything has shown it took FreeCAD
    down with a segmentation fault. A command with no action yet has not
    been shown anywhere, so there is no enabled state to agree with.
    """
    try:
        if not command.getAction():
            return True
        return bool(command.isActive())
    except Exception:
        return True


def command_icon(name: str) -> Any:
    """A command's icon as a QIcon, or None; for the icon provider."""
    command = _command(name)
    if command is None:
        return None
    try:
        pixmap = command.getInfo().get("pixmap", "")
    except Exception:
        return None
    if not pixmap:
        return None
    if hasattr(Gui, "getIcon"):
        return Gui.getIcon(pixmap)
    from ..qt import QtGui
    return QtGui.QIcon(":/icons/%s.svg" % pixmap)


def run_command(name: str) -> bool:
    """Run a FreeCAD command on the current selection."""
    if name in UNSAFE:
        App.Console.PrintError("Nxt menu: %s is not run from here\n" % name)
        return False
    try:
        Gui.runCommand(name)
        return True
    except Exception as exc:
        App.Console.PrintError("Nxt menu: %s failed: %s\n" % (name, exc))
        return False


def run_edit(obj: Any, command: str) -> bool:
    """Start one of an object's edit modes, as its own menu entry would."""
    mode = EDIT_MODES.get(command.split(":", 1)[1], 0)
    try:
        Gui.ActiveDocument.setEdit(obj, mode)
        return True
    except Exception as exc:
        App.Console.PrintError("Nxt menu: could not edit %s: %s\n"
                               % (getattr(obj, "Name", obj), exc))
        return False


def open_native_menu() -> None:
    """Open FreeCAD's own tree menu for the selection, at the pointer.

    Sent to FreeCAD's Model tree as if it had been right-clicked there.
    Deferred, so the Nxt menu that asked for it has closed first.
    """
    from ..qt import QtCore, QtGui, QtWidgets

    def show() -> None:
        trees = [w for w in Gui.getMainWindow().findChildren(
            QtWidgets.QTreeWidget)
            if w.metaObject().className() == "Gui::TreeWidget"]
        if not trees:
            App.Console.PrintError("Nxt menu: FreeCAD's Model tree was "
                                   "not found\n")
            return
        tree = ([w for w in trees if w.isVisible()] or trees)[0]
        items = tree.selectedItems()
        point = (tree.visualItemRect(items[0]).center() if items
                 else QtCore.QPoint(1, 1))
        event = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Reason.Mouse, point, QtGui.QCursor.pos())
        QtWidgets.QApplication.sendEvent(tree.viewport(), event)

    QtCore.QTimer.singleShot(0, show)
