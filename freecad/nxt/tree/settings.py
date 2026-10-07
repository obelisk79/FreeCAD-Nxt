"""Panel state that should survive a restart.

Kept in FreeCAD's own parameter store rather than a file of our own, so it
travels with the user's configuration, is visible in the parameter editor,
and needs no migration or cleanup of ours.

What this records is the handful of facts nothing else will restore for a
dock that does not exist yet when the main window state is read back: it is
created by an addon, long after Qt has replayed its saved layout.

That applies to the overlay state too. It seemed reasonable that FreeCAD's
overlay manager would restore its own docks - and it does, for docks that
exist when it runs. Ours does not, so it has to be recorded here like
everything else.
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App

GROUP = "User parameter:BaseApp/Preferences/Mod/Nxt"

#: Open at startup unless the user closed it last time. Defaulting to true
#: is the point of persisting any of this - the panel is meant to be there.
DEFAULTS: dict[str, bool | int | float | str] = {
    # False only on the very first run, which is when the panel gets its
    # one chance to tab itself beside the stock tree. After that the user's
    # arrangement wins and is never second-guessed.
    "Configured": False,
    "Visible": True,
    "Overlay": False,
    # Whether the overlay presentation came from FreeCAD's overlay manager
    # rather than from the panel's own toggle. Restoring the two is not the
    # same operation, so which it was has to be recorded.
    "HostOverlay": False,
    "Floating": False,
    "DockArea": 1,          # Qt.LeftDockWidgetArea
    "FloatX": 0,
    "FloatY": 0,
    "FloatWidth": 0,
    "FloatHeight": 0,
    # How the tree is structured: "expression" (sketches in the timeline,
    # Part models as flat steps) or "nested" (the classic tree).
    "PartLayout": "expression",
    # The tree's quick settings; see prefs.py for the values each takes.
    "RowDensity": "normal",
    "ReferenceChips": "problems",
    "UnderConstrainedMarks": True,
    # Hovering a row's controls explains them (NxtToolTip.qml).
    "RowToolTips": True,
    # Whose overlay the panel uses: Nxt's own, drawn inside the 3D view
    # with clicks passing through ("nxt"), or FreeCAD's ("freecad").
    "OverlayMode": "nxt",
    # The panel was in the 3D view (Nxt's overlay) when FreeCAD closed.
    "ViewOverlay": False,
    # Picking an object in the 3D view scrolls the tree to its row.
    "FollowSelection": True,
    # Double-clicking a face in the 3D view edits the feature that made it.
    "EditOnDoubleClick": True,
    # Set once Nxt has put its drag-handle defaults in place (gizmos.py).
    "GizmoDefaultsApplied": False,
    # A value field floats beside a feature's drag arrow (float_input.py).
    "FloatingValues": True,
    # A feature opened by double-clicking its row is edited without the
    # 3D drag handles; a newly created one still gets them.
    "TreeEditHidesHandles": False,
    # Dotted connector lines from each container to its children.
    "TreeLines": False,
    # Clicking a row opens its detail strip, after a moment.
    "DetailAutoShow": False,
    # Selecting an object lights up the rows it reads and the rows that
    # read it.
    "HighlightRelated": False,
    # Arrows in the tree's gutter for the selection's dependencies.
    "DependencyArrows": False,
    # The header and detail strips are capped at this percentage
    # of the screen's width, but never below HeaderMinWidth pixels.
    "HeaderMaxPercent": 18,
    "HeaderMinWidth": 220,
    # The Property Inspector: whether it stays open, and where it was left
    # while pinned. A width or height of 0 means "never placed yet".
    "InspectorPinned": False,
    # The inspector opens on FreeCAD's property table, not Nxt's page.
    "InspectorTable": False,
    "InspectorX": 0,
    "InspectorY": 0,
    "InspectorWidth": 0,
    "InspectorHeight": 0,
}


def _params() -> Any:
    return App.ParamGet(GROUP)


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
    """Read one setting, falling back to its default on any trouble.

    Preferences are never worth an exception: a corrupt or absent value
    should give the user a working panel, not a stack trace at startup.
    """
    default = DEFAULTS[key]
    _kind, getter, _setter = _accessor(default)
    try:
        return getattr(_params(), getter)(key, default)
    except Exception:
        App.Console.PrintError("Nxt: could not read preference %r\n" % key)
        return default


def put(key: str, value: object) -> None:
    kind, _getter, setter = _accessor(DEFAULTS[key])
    try:
        getattr(_params(), setter)(key, kind(value))
    except Exception:
        App.Console.PrintError("Nxt: could not write preference %r\n" % key)
        App.Console.PrintError(traceback.format_exc())
