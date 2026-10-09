"""Space shows or hides what is selected - the feature, not its Body.

FreeCAD records a feature picked in a Body as the Body with the feature's
path ("Body", "Pad."), even when it was picked from a tree by name, and a
face clicked on a Body's solid as the Body with the face ("Body",
"Face6"). Read naively, either one is the Body, and Space hid the Body -
sketches, datums and all.

Here each entry is read for what it means: the last object of its path,
or, for a bare face of a Body, the feature showing the solid (the tip,
or whichever is shown instead). A Body picked whole is still the Body.

`targets()` is that rule; the tree's Space uses it, and `SpaceInView`
applies it to Space pressed in a 3D view, ahead of FreeCAD's shortcut.
Nothing here depends on the tree.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .qt import QtCore, QtWidgets

BODY = "PartDesign::Body"
FEATURE = "PartDesign::Feature"
#: Qt class of the MDI view that holds a 3D view.
VIEW_CLASS = "Gui::View3DInventor"


def _is(obj: Any, type_name: str) -> bool:
    try:
        return bool(obj.isDerivedFrom(type_name))
    except Exception:
        return False


def _shown(obj: Any) -> bool:
    return bool(getattr(getattr(obj, "ViewObject", None), "Visibility",
                        False))


def shown_feature(body: Any) -> Any:
    """The feature a Body's solid is drawn through: its tip, normally."""
    tip = getattr(body, "Tip", None)
    if tip is not None and _shown(tip):
        return tip
    for obj in getattr(body, "Group", ()):
        if _is(obj, FEATURE) and _shown(obj):
            return obj
    return tip


def _picked(doc: Any, top: Any, sub: str) -> Any:
    """The object one selection entry means (see the module)."""
    path, _dot, element = sub.rpartition(".")
    if path:
        found = doc.getObject(path.split(".")[-1])
        if found is not None:
            return found
    if element and _is(top, BODY):
        return shown_feature(top) or top
    return top


def targets(doc: Any) -> list[Any]:
    """What Space should show or hide in `doc`, from the selection."""
    try:
        selection = Gui.Selection.getSelectionEx(doc.Name, 0)
    except Exception:
        return []
    found: list[Any] = []
    for entry in selection:
        top = getattr(entry, "Object", None)
        if top is None:
            continue
        subs = list(getattr(entry, "SubElementNames", ()) or ()) or [""]
        for sub in subs:
            obj = _picked(doc, top, sub or "")
            if obj is not None and obj not in found:
                found.append(obj)
    return found


def toggle(doc: Any, objects: list[Any],
           show_alone: Callable[[Any, list[str]], None] | None = None
           ) -> None:
    """Show or hide `objects` all the same way, as one undo step.

    If any is shown they are all hidden, otherwise all shown: flipping
    each would swap a mixed selection. `show_alone(doc, names)` runs after
    showing, for whoever keeps one feature per Body on show.
    """
    views = [(o, o.ViewObject) for o in objects
             if getattr(o, "ViewObject", None) is not None]
    if not views:
        return
    show = not any(bool(vo.Visibility) for _o, vo in views)
    try:
        doc.openTransaction("Toggle visibility")
        for _obj, vo in views:
            vo.Visibility = show
        if show and show_alone is not None:
            show_alone(doc, [o.Name for o, _vo in views])
        doc.commitTransaction()
    except Exception:
        doc.abortTransaction()
        App.Console.PrintError("Nxt: visibility toggle failed\n")


def toggle_selected() -> None:
    doc = App.ActiveDocument
    if doc is not None:
        toggle(doc, targets(doc))


def _in_3d_view(widget: Any) -> bool:
    while widget is not None:
        try:
            if widget.metaObject().className() == VIEW_CLASS:
                return True
            widget = widget.parentWidget()
        except (RuntimeError, AttributeError):
            return False
    return False


def _editing() -> bool:
    try:
        gui_doc = Gui.ActiveDocument
        return gui_doc is not None and gui_doc.getInEdit() is not None
    except Exception:
        return False


class SpaceInView(QtCore.QObject):
    """Space in a 3D view, taken from FreeCAD's shortcut (see the module).

    Steps aside while something is being edited - a sketch, a task - so
    Space there means whatever it meant before.
    """

    def __init__(self, parent: QtCore.QObject | None = None,
                 action: Callable[[], None] = toggle_selected) -> None:
        super().__init__(parent)
        self._action = action

    def install(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def remove(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        # Every event in the application comes through here: cheap first.
        kind = event.type()
        if kind not in (QtCore.QEvent.Type.ShortcutOverride,
                        QtCore.QEvent.Type.KeyPress):
            return False
        try:
            if (event.key() != QtCore.Qt.Key.Key_Space
                    or event.modifiers()
                    != QtCore.Qt.KeyboardModifier.NoModifier
                    or event.isAutoRepeat()
                    or not _in_3d_view(watched) or _editing()):
                return False
        except Exception:
            return False
        event.accept()
        if kind == QtCore.QEvent.Type.ShortcutOverride:
            return False        # accepted: the key comes as a KeyPress
        try:
            self._action()
        except Exception as exc:
            App.Console.PrintError("Nxt: Space failed: %s\n" % exc)
        return True
