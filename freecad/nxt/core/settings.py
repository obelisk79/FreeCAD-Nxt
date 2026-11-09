"""Panel state that survives a restart, in FreeCAD's parameter store.

The dock is created after Qt and FreeCAD's overlay manager restore layout,
so its placement and overlay state must be recorded here.
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App

GROUP = "User parameter:BaseApp/Preferences/Mod/Nxt"

DEFAULTS: dict[str, bool | int | float | str] = {
    # First run only: the panel tabs itself beside the stock tree once.
    "Configured": False,
    "Visible": True,
    "Overlay": False,
    # Overlay came from FreeCAD's manager, not the panel's toggle.
    "HostOverlay": False,
    "Floating": False,
    "DockArea": 1,          # Qt.LeftDockWidgetArea
    "FloatX": 0,
    "FloatY": 0,
    "FloatWidth": 0,
    "FloatHeight": 0,
    # "expression" (timeline) or "nested" (the classic tree).
    "PartLayout": "expression",
    # The tree's quick settings; see prefs.py for the values each takes.
    "RowDensity": "normal",
    "ReferenceChips": "problems",
    "UnderConstrainedMarks": True,
    "RowToolTips": True,
    # "nxt" (drawn in the 3D view) or "freecad".
    "OverlayMode": "nxt",
    "ViewOverlay": False,
    # FreeCAD's own "Auto expand tree item" (see SHARED).
    "FollowSelection": True,
    "EditOnDoubleClick": True,
    "AttachSketchByPoints": True,
    "SnapToFaces": True,
    "RepairProfiles": True,
    # A new sketch, container or feature opens in rename.
    "AutoRename": False,
    # Look for addon updates after startup (app/update_check.py).
    "CheckAddonUpdates": True,
    # JSON of the Report view pop-up settings the check turned off.
    "QuietOriginals": "",
    "GizmoDefaultsApplied": False,
    # Before 2026-10: JSON of the drag settings the defaults replaced.
    "GizmoOriginals": "",
    # JSON of every FreeCAD value Nxt wrote and what it replaced
    # (gizmos.py), put back when Nxt is disabled or removed.
    "ForeignOriginals": "",
    "FloatingValues": True,
    "TreeEditHidesHandles": False,
    "TreeLines": False,
    "DetailAutoShow": False,
    "HighlightRelated": False,
    "DependencyArrows": False,
    # Quick Mass at the bottom of the 3D view (ui/quick_mass.py).
    "QuickMass": False,
    "QuickMassMaterial": "Steel-Generic",
    # kg/m³, used when the material is "Custom".
    "QuickMassDensity": 1000.0,
    "QuickMassUnits": "Internal",
    # Strip width: percent of screen, floored at HeaderMinWidth pixels.
    "HeaderMaxPercent": 18,
    "HeaderMinWidth": 220,
    # Inspector geometry; a size of 0 means never placed.
    "InspectorPinned": False,
    "InspectorTable": False,
    "InspectorX": 0,
    "InspectorY": 0,
    "InspectorWidth": 0,
    "InspectorHeight": 0,
}


#: Settings that are FreeCAD's own: key -> (group, name). Nxt's page
#: edits them in place, so both preference pages show one value.
SHARED: dict[str, tuple[str, str]] = {
    "FollowSelection": ("User parameter:BaseApp/Preferences/TreeView",
                        "SyncSelection"),
}


def _params(key: str) -> tuple[Any, str]:
    group, name = SHARED.get(key, (GROUP, key))
    return App.ParamGet(group), name


#: bool before int: bool is a subclass of int, so the order matters.
_ACCESSORS: tuple[tuple[type, str, str], ...] = (
    (bool, "GetBool", "SetBool"),
    (int, "GetInt", "SetInt"),
    (float, "GetFloat", "SetFloat"),
    (str, "GetString", "SetString"),
)


def _accessor(default: object) -> tuple[type, str, str]:
    for kind, getter, setter in _ACCESSORS:
        if isinstance(default, kind):
            return kind, getter, setter
    return str, "GetString", "SetString"


def get(key: str) -> Any:
    """Read one setting, falling back to its default on any error."""
    default = DEFAULTS[key]
    _kind, getter, _setter = _accessor(default)
    try:
        params, name = _params(key)
        return getattr(params, getter)(name, default)
    except Exception:
        App.Console.PrintError("Nxt: could not read preference %r\n" % key)
        return default


#: Set once Nxt's settings are deleted at uninstall, so the still-running
#: addon does not write them back.
removed = False


def put(key: str, value: object) -> None:
    if removed:
        return
    kind, _getter, setter = _accessor(DEFAULTS[key])
    try:
        params, name = _params(key)
        getattr(params, setter)(name, kind(value))
    except Exception:
        App.Console.PrintError("Nxt: could not write preference %r\n" % key)
        App.Console.PrintError(traceback.format_exc())
