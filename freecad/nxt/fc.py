"""Small typed doors into FreeCAD's Python API, for the type checker.

`freecad-stubs` types most of FreeCAD's API, which is what lets mypy find
an unchecked `None` from `ActiveDocument`. A few calls Nxt makes are not
in the stubs, or are typed narrower than FreeCAD allows; these helpers
give them one honest place, rather than an `# type: ignore` at every use.
"""

from __future__ import annotations

from typing import Any

import FreeCADGui as Gui


def active_view() -> Any:
    """The active document's view, or None.

    Typed Any: the 3D view's Python API (getActiveObject, setActiveObject,
    getPointOnViewport, getObjectInfo, getCursorPos) is wider than the
    stubs' View3DInventorPy, and ActiveView may be any MDI view.
    """
    gui_doc = Gui.ActiveDocument
    return gui_doc.ActiveView if gui_doc is not None else None


def list_commands() -> list[str]:
    """Every registered command's name (not in the stubs)."""
    return list(getattr(Gui, "listCommands")())
