"""Nxt - a QtQuick model panel for FreeCAD."""

from __future__ import annotations

import importlib
import sys
import traceback

from .app.version import __version__  # noqa: F401

# The binding shim is never reloaded; everything else is fair game.
_FROZEN = ("freecad.nxt.core.qt",)

# Reload order matters: leaves first, orchestrators last.
_RELOAD_ORDER = (
    # tree.health before tree.scene, which imports it.
    "freecad.nxt.core.log",
    "freecad.nxt.core.widgets",
    "freecad.nxt.core.view3d",
    "freecad.nxt.core.events",
    "freecad.nxt.core.transaction",
    "freecad.nxt.core.units",
    "freecad.nxt.core.property_kinds",
    "freecad.nxt.resources",
    "freecad.nxt.core.settings",
    "freecad.nxt.tree.health",
    "freecad.nxt.tree.scene",
    "freecad.nxt.tree.icons",
    "freecad.nxt.ui.qss_colours",
    "freecad.nxt.ui.theme",
    "freecad.nxt.inspector.properties",
    "freecad.nxt.inspector.templates",
    "freecad.nxt.inspector.layout",
    "freecad.nxt.tools.task_sync",
    "freecad.nxt.inspector.bridge",
    "freecad.nxt.tools.task_layout",
    "freecad.nxt.tree.reorder",
    "freecad.nxt.tree.picking",
    "freecad.nxt.tools.editing",
    "freecad.nxt.tools.face_edit",
    "freecad.nxt.tools.gizmos",
    "freecad.nxt.tools.float_input",
    "freecad.nxt.tools.drag_guard",
    "freecad.nxt.tree.saved_expansion",
    "freecad.nxt.tree.models",
    "freecad.nxt.tree.links",
    "freecad.nxt.tree.bridge",
    "freecad.nxt.tree.view_overlay",
    "freecad.nxt.tree.observers",
    "freecad.nxt.diagnostics.probe",
    "freecad.nxt.menus.definitions",
    "freecad.nxt.menus.facts",
    "freecad.nxt.menus.labels",
    "freecad.nxt.menus.present",
    "freecad.nxt.menus.runner",
    "freecad.nxt.menus",
    "freecad.nxt.tree.menu_actions",
    "freecad.nxt.ui.prefs",
    "freecad.nxt.tree.panel",
    "freecad.nxt.inspector.host",
    "freecad.nxt.tools.isolate",
    "freecad.nxt.ui.view_notice",
    "freecad.nxt.ui.isolate_notice",
    "freecad.nxt.ui.toast",
    "freecad.nxt.tools.sketch_closure",
    "freecad.nxt.tools.sketch_repair",
    "freecad.nxt.tools.sketch_attach",
    "freecad.nxt.tools.sketch_state",
    "freecad.nxt.tools.sketch_contents",
    "freecad.nxt.tools.sketch_contents_model",
    "freecad.nxt.tools.sketch_panel",
    "freecad.nxt.tools.face_snap",
    "freecad.nxt.core.fc",
    "freecad.nxt.tools.expressions",
    "freecad.nxt.tools.visibility",
    "freecad.nxt.app.services",
)


def reload_all() -> bool:
    """Tear down, reload the mutable modules, and report the outcome."""
    import FreeCAD as App

    # Observers and the QML engine must go before their modules are swapped,
    # or they point at dead code. The inspector returns FreeCAD's editor first.
    inspector = sys.modules.get("freecad.nxt.inspector.host")
    if inspector is not None:
        try:
            inspector.shutdown()
        except Exception:
            App.Console.PrintError("Nxt: Property Inspector teardown failed\n")
            App.Console.PrintError(traceback.format_exc())

    services = sys.modules.get("freecad.nxt.app.services")
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
            sys.modules["freecad.nxt.app.services"].start()
        except Exception:
            App.Console.PrintError("Nxt: services did not come back\n")
            App.Console.PrintError(traceback.format_exc())

    # Reopen even after a failed reload, so the panel is never stranded.
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
