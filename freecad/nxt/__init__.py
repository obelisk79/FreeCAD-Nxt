"""Nxt - a QtQuick model panel for FreeCAD."""

from __future__ import annotations

import importlib
import sys
import traceback

from .version import __version__  # noqa: F401

# The binding shim is never reloaded; everything else is fair game.
_FROZEN = ("freecad.nxt.qt",)

# Reload order matters: leaves first, orchestrators last.
_RELOAD_ORDER = (
    # health before scene: scene imports it, so it has to be the new module
    # object by the time scene re-executes its own import.
    "freecad.nxt.resources",
    "freecad.nxt.tree.settings",
    "freecad.nxt.tree.health",
    "freecad.nxt.tree.scene",
    "freecad.nxt.tree.icons",
    "freecad.nxt.tree.qss_colours",
    "freecad.nxt.tree.theme",
    "freecad.nxt.tree.properties",
    "freecad.nxt.tree.inspector",
    "freecad.nxt.tree.inspector_bridge",
    "freecad.nxt.tree.reorder",
    "freecad.nxt.tree.picking",
    "freecad.nxt.tree.editing",
    "freecad.nxt.tree.face_edit",
    "freecad.nxt.tree.gizmos",
    "freecad.nxt.tree.float_input",
    "freecad.nxt.tree.models",
    "freecad.nxt.tree.links",
    "freecad.nxt.tree.bridge",
    "freecad.nxt.tree.observers",
    "freecad.nxt.tree.probe",
    "freecad.nxt.menus.definitions",
    "freecad.nxt.menus.facts",
    "freecad.nxt.menus.labels",
    "freecad.nxt.menus.present",
    "freecad.nxt.menus.runner",
    "freecad.nxt.menus",
    "freecad.nxt.tree.menu_actions",
    "freecad.nxt.tree.prefs",
    "freecad.nxt.tree.panel",
    "freecad.nxt.property_inspector",
    "freecad.nxt.isolate",
    "freecad.nxt.isolate_notice",
    "freecad.nxt.services",
)


def reload_all() -> bool:
    """Tear down, reload the mutable modules, and report what happened.

    Run this from the Python console, or as Nxt_Reload, after editing
    addon source.
    """
    import FreeCAD as App

    # The panel holds document observers and a live QML engine. Both must be
    # torn down before their modules are swapped out, or the reload leaves
    # observers pointing at dead code and QML bindings at deleted QObjects.
    # The inspector holds FreeCAD's own Property editor; it goes home first.
    inspector = sys.modules.get("freecad.nxt.property_inspector")
    if inspector is not None:
        try:
            inspector.shutdown()
        except Exception:
            App.Console.PrintError("Nxt: Property Inspector teardown failed\n")
            App.Console.PrintError(traceback.format_exc())

    services = sys.modules.get("freecad.nxt.services")
    services_were_up = services is not None and services.instance() is not None
    if services is not None:
        try:
            services.stop()
        except Exception:
            App.Console.PrintError("Nxt: services teardown failed\n")
            App.Console.PrintError(traceback.format_exc())

    panel_was_open = False
    try:
        if "freecad.nxt.tree.panel" in sys.modules:
            panel = sys.modules["freecad.nxt.tree.panel"]
            panel_was_open = panel.is_open()
            panel.close()
    except Exception:
        App.Console.PrintError("Nxt: panel teardown failed on reload\n")
        App.Console.PrintError(traceback.format_exc())

    failed: str | None = None
    for name in _RELOAD_ORDER:
        if name in _FROZEN or name not in sys.modules:
            continue
        try:
            importlib.reload(sys.modules[name])
        except Exception:
            App.Console.PrintError("Nxt: reload failed for %s\n" % name)
            App.Console.PrintError(traceback.format_exc())
            failed = name
            break

    if services_were_up:
        try:
            sys.modules["freecad.nxt.services"].start()
        except Exception:
            App.Console.PrintError("Nxt: services did not come back\n")
            App.Console.PrintError(traceback.format_exc())

    # Put the panel back either way. A failed reload used to return here, so
    # the panel stayed closed with nothing on screen saying how to get it
    # back - the same stranded state the rest of this addon works to avoid.
    # If the panel cannot start on the half-reloaded modules it says so in
    # its own body rather than throwing.
    if panel_was_open:
        try:
            sys.modules["freecad.nxt.tree.panel"].show()
        except Exception:
            App.Console.PrintError(
                "Nxt: panel did not come back - fix the error above, "
                "then run Nxt_Reload again\n")
            App.Console.PrintError(traceback.format_exc())

    if failed is not None:
        App.Console.PrintError(
            "Nxt: reload stopped at %s; modules after it in the reload "
            "order are still the old ones\n" % failed)
        return False

    App.Console.PrintMessage("Nxt: modules reloaded\n")
    return True
