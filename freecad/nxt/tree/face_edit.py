"""Double-click a face in the 3D view to edit the feature that made it.

FreeCAD's own double-click on a Part Design solid edits whatever it takes
the picked object to be - the Body's tip, whichever feature made the
face. This catches the double-click first and opens the feature the face
is traced to instead (see picking.py): the Pad for a Pad's face, even
with three Pockets after it.

It steps aside, and FreeCAD's double-click happens as it always did,
whenever:
  * the setting "Double-click a face to edit the feature that made it" is
    off;
  * something is already being edited - a sketch, where double-clicks
    edit constraints, or a feature's task;
  * nothing is under the pointer (a navigation style may use the
    double-click on empty space);
  * no face is selected to trace;
  * an origin plane, axis or point is double-clicked while a task panel
    is open, where it is a reference being picked for the task.

A face the tip made opens the tip: FreeCAD's own double-click on a
Body's solid does not open anything, so this handles that case too.

The first click of a double-click has already selected the face, so the
trace works from the selection, exactly as the single-click reveal does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import FreeCAD as App
import FreeCADGui as Gui

from ..qt import QtCore, QtWidgets
from . import editing, picking, settings

if TYPE_CHECKING:
    from typing import Protocol

    class Editor(Protocol):
        def edit_feature(self, doc_name: str, name: str) -> None: ...

#: Qt class of the MDI view that holds a 3D view.
_VIEW_CLASS = "Gui::View3DInventor"


def _in_3d_view(widget: Any) -> Any:
    """The View3DInventor `widget` belongs to, or None."""
    while widget is not None:
        try:
            if widget.metaObject().className() == _VIEW_CLASS:
                return widget
            widget = widget.parentWidget()
        except (RuntimeError, AttributeError):
            return None
    return None


def picked_feature() -> tuple[str, str] | None:
    """(document, feature) for the face selected last, traced to its maker.

    The feature is the selected object itself when it made the face - the
    tip, for its own faces. None when no element is selected.
    """
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
            continue
        sub = subs[-1]
        name = picking.target(doc, entry.Object.Name, sub)
        return (doc.Name, name) if name else None
    return None


class DoubleClickEditor(QtCore.QObject):
    """An application event filter that sees double-clicks in 3D views."""

    def __init__(self, editor: Editor) -> None:
        # Owned by the services (services.py), not the panel: this works
        # with the panel closed. `editor` opens the feature.
        super().__init__(editor if isinstance(editor, QtCore.QObject)
                         else None)
        self._editor = editor

    def install(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def remove(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        # Every event in the application comes through here: the first
        # test has to be the cheap one.
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
                or _in_3d_view(watched) is None:
            return False
        gui_doc = Gui.ActiveDocument
        if gui_doc is None or gui_doc.getInEdit() is not None:
            return False
        try:
            view = gui_doc.ActiveView
            if view.getObjectInfo(view.getCursorPos()) is None:
                return False            # empty space: FreeCAD's
        except Exception:
            pass
        found = picked_feature()
        if found is None or editing.is_reference_pick(
                App.ActiveDocument.getObject(found[1])):
            return False
        App.Console.PrintLog("Nxt double-click: edit %s\n" % found[1])
        self._editor.edit_feature(*found)
        return True                     # FreeCAD's double-click is replaced
