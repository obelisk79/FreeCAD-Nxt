"""GUI entry point, loaded by FreeCAD once at startup.

Registers the icon path and commands, lists the panel commands in the View
menu, and brings the panel back if it was open last session. Nothing here
changes process-wide state: the scenegraph backend is set by the first QML
surface, when it is built.
"""

from __future__ import annotations

import traceback

import FreeCAD as App
import FreeCADGui as Gui

from . import commands, resources
from .qt import QtCore


class Manipulator:
    """Adds the FreeCAD-Nxt submenu to the View menu of every workbench."""

    def modifyMenuBar(self) -> list[dict[str, str]]:  # noqa: N802 - FreeCAD manipulator API
        # "append" adds to the end of the menu holding `menuItem`.
        return [{"append": commands.GROUP, "menuItem": "Std_DockViewMenu"}]


def _restore_panel() -> None:
    """Reopen the panel once the main window exists."""
    try:
        from .tree import panel
        panel.restore()
    except Exception:
        App.Console.PrintError("Nxt: panel autostart failed\n")
        App.Console.PrintError(traceback.format_exc())


Gui.addIconPath(str(resources.ICONS))
Gui.addLanguagePath(str(resources.TRANSLATIONS))
Gui.updateLocale()
commands.register()
Gui.addWorkbenchManipulator(Manipulator())
QtCore.QTimer.singleShot(0, _restore_panel)
