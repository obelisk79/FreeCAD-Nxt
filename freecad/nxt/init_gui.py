"""GUI entry point, loaded by FreeCAD once at startup.

Sets no process-wide state: the first QML surface sets the scenegraph.
"""

from __future__ import annotations

import traceback
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui

from . import resources
from .app import commands
from .core.qt import QtCore


class Manipulator:
    """Adds the FreeCAD-Nxt submenu to the View menu of every workbench."""

    def modifyMenuBar(self) -> list[dict[str, str]]:  # noqa: N802 - FreeCAD manipulator API
        return [{"append": commands.GROUP, "menuItem": "Std_DockViewMenu"}]


def _restore_panel() -> None:
    """Start the services, then reopen the panel, which connects to them."""
    try:
        from .app import services
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
    """At quit, undo Nxt's settings if it is disabled or removed."""
    try:
        from .app import cleanup
        cleanup.at_quit(ROOT)
    except Exception:
        App.Console.PrintError("Nxt: could not clean up its settings\n")


# Before any setting is written: a first run is told by none being there.
try:
    from .app import welcome as _welcome
    _welcome.schedule()
except Exception:
    App.Console.PrintError("Nxt: could not schedule the welcome\n")
try:
    from .tools import gizmos as _gizmos
    _gizmos.apply_defaults_once()
except Exception:
    App.Console.PrintError("Nxt: could not set the drag defaults\n")
_app = QtCore.QCoreApplication.instance()
if _app is not None:
    _app.aboutToQuit.connect(_leaving)
try:
    from .ui import prefs as _prefs
    Gui.addPreferencePage(_prefs.NxtPreferencesPage, _prefs.GROUP)
except Exception:
    App.Console.PrintError("Nxt: could not add the Preferences page\n")
    App.Console.PrintError(traceback.format_exc())
QtCore.QTimer.singleShot(0, _restore_panel)
try:
    from .app import view_toolbar as _view_toolbar
    _view_toolbar.install()
except Exception:
    App.Console.PrintError("Nxt: could not add the View toolbar button\n")
try:
    from .app import menu_button as _menu_button
    _menu_button.install()
except Exception:
    App.Console.PrintError("Nxt: could not add the menu button\n")
try:
    from .app import test_toolbar as _test_toolbar
    _test_toolbar.install()
except Exception:
    App.Console.PrintError("Nxt: could not add the Fillet/Chamfer toolbar\n")
try:
    from .app import update_check as _update_check
    _update_check.install()
except Exception:
    App.Console.PrintError("Nxt: could not schedule the addon update check\n")
