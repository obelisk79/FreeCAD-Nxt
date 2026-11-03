"""Double-click a face in the 3D view to edit the feature that made it.

FreeCAD would edit the Body's tip. Steps aside during edits, on empty
space, and for reference picks; the first click has already selected
the face, so the trace works from the selection.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import fc, settings, view3d
from ..core.events import ApplicationEventFilter
from ..core.qt import QtCore, QtWidgets
from ..tree import picking
from . import editing

if TYPE_CHECKING:
    from typing import Protocol

    class Editor(Protocol):
        def edit_feature(self, doc_name: str, name: str) -> None: ...


def picked_feature() -> tuple[str, str] | None:
    """(document, feature) for the face selected last, traced to its maker."""
    doc = App.ActiveDocument
    if doc is None:
        return None
    try:
        selection = Gui.Selection.getSelectionEx(doc.Name, 0)
    except Exception:
        return None
    for entry in reversed(list(selection)):
        subs = list(entry.SubElementNames or [])
        if not subs:
            # A datum may be picked whole, with no element.
            if editing.is_datum(entry.Object):
                return (doc.Name, entry.Object.Name)
            continue
        sub = subs[-1]
        name = picking.target(doc, entry.Object.Name, sub)
        return (doc.Name, name) if name else None
    return None


class DoubleClickEditor(ApplicationEventFilter):
    """Takes double-clicks in 3D views ahead of FreeCAD."""

    def __init__(self, editor: Editor) -> None:
        super().__init__(editor if isinstance(editor, QtCore.QObject)
                         else None)
        self._editor = editor

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        # Sees every application event: cheap test first.
        if event.type() != QtCore.QEvent.Type.MouseButtonDblClick:
            return False
        try:
            return self._double_click(watched, event)
        except Exception as exc:
            App.Console.PrintError("Nxt: double-click edit failed: %s\n"
                                   % exc)
            return False

    def _double_click(self, watched: Any, event: Any) -> bool:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return False
        if not settings.get("EditOnDoubleClick"):
            return False
        if not isinstance(watched, QtWidgets.QWidget) \
                or view3d.view3d_holding(watched) is None:
            return False
        gui_doc = Gui.ActiveDocument
        if gui_doc is None or gui_doc.getInEdit() is not None:
            return False
        info: Any = None
        with contextlib.suppress(Exception):
            view = fc.active_view()
            info = view.getObjectInfo(view.getCursorPos())
            if info is None:
                return False            # empty space: FreeCAD's
        from . import section_object, section_view
        section = None
        with contextlib.suppress(Exception):  # no section, then
            section = section_view.section_at(info)
        if section is not None:
            # Deferred: editing opens a dialog, not inside the click.
            QtCore.QTimer.singleShot(0, lambda: section_object.edit(section))
            return True
        found = picked_feature()
        doc = App.ActiveDocument
        if found is None or doc is None or editing.is_reference_pick(
                doc.getObject(found[1])):
            return False
        App.Console.PrintLog("Nxt double-click: edit %s\n" % found[1])
        self._editor.edit_feature(*found)
        return True                     # FreeCAD's double-click is replaced
