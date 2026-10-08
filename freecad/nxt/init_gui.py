"""GUI entry point, loaded by FreeCAD once at startup.

Registers the icon path and commands, lists the panel commands in the View
menu, and brings the panel back if it was open last session. Nothing here
changes process-wide state: the scenegraph backend is set by the first QML
surface, when it is built.
"""

from __future__ import annotations

import traceback
from pathlib import Path

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
    """Start the services, then reopen the panel, once the window exists.

    The services first: they are what works with the panel closed, and the
    panel connects to them as it opens.
    """
    try:
        from . import services
        services.start()
    except Exception:
        App.Console.PrintError("Nxt: services failed to start\n")
        App.Console.PrintError(traceback.format_exc())
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
#: Nxt's folder, where the Addon Manager marks it disabled.
ROOT = Path(__file__).resolve().parents[2]


def _leaving() -> None:
    """At quit, put FreeCAD's drag settings back if Nxt is going away."""
    try:
        from .tree import gizmos
        gizmos.restore_if_leaving(ROOT)
    except Exception:
        App.Console.PrintError("Nxt: could not restore the drag settings\n")


try:
    from .tree import gizmos as _gizmos
    _gizmos.apply_defaults_once()
except Exception:
    App.Console.PrintError("Nxt: could not set the drag defaults\n")
_app = QtCore.QCoreApplication.instance()
if _app is not None:
    _app.aboutToQuit.connect(_leaving)
try:
    from .tree import prefs as _prefs
    Gui.addPreferencePage(_prefs.PreferencesPage, _prefs.GROUP)
except Exception:
    App.Console.PrintError("Nxt: could not add the Preferences page\n")
    App.Console.PrintError(traceback.format_exc())
QtCore.QTimer.singleShot(0, _restore_panel)
