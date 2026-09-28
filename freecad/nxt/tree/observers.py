"""Document and selection observers.

Three separate FreeCAD observer channels feed the panel:

    App observer   structure and data - objects created, deleted, relabelled,
                   recomputed, undone.
    Gui observer   view state - visibility, edit mode, view provider changes.
    Selection      the global selection, which we mirror rather than own.

None of them rebuild anything directly. They call `bridge.invalidate()`,
which collapses a burst of a thousand signals during a recompute into one
rebuild on the next event-loop turn. Selection is the exception: it is cheap
and needs to feel instant, so it syncs synchronously.
"""

from __future__ import annotations

import traceback
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

#: Property changes that cannot affect anything the panel draws. Skipping
#: them keeps a Placement drag from queueing a rebuild on every mouse move.
_IGNORED_PROPERTIES: frozenset[str] = frozenset({
    "Placement", "Shape", "_Body", "AttachmentOffset",
    "ExpressionEngine", "Proxy",
})


def _err(message: str) -> None:
    App.Console.PrintError("Nxt: %s\n" % message)
    App.Console.PrintError(traceback.format_exc())


class _AppObserver(object):
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def slotCreatedObject(self, obj: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotDeletedObject(self, obj: Any) -> None:
        self._bridge.invalidate()

    def slotChangedObject(self, obj: Any, prop: str) -> None:
        if prop in _IGNORED_PROPERTIES:
            return
        self._bridge.invalidate()

    def slotRelabelObject(self, obj: Any) -> None:
        self._bridge.invalidate()

    def slotRecomputedDocument(self, doc: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotUndoDocument(self, doc: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotRedoDocument(self, doc: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotActivateDocument(self, doc: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotDeletedDocument(self, doc: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotFinishSaveDocument(self, doc: Any, label: str) -> None:
        pass


class _GuiObserver(object):
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def slotChangedObject(self, vobj: Any, prop: str) -> None:
        # Visibility is the one view property the panel renders directly.
        self._bridge.invalidate(icons=(prop != "Visibility"))

    def slotCreatedObject(self, vobj: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotDeletedObject(self, vobj: Any) -> None:
        self._bridge.invalidate()

    def slotInEdit(self, vobj: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotResetEdit(self, vobj: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotActivateDocument(self, doc: Any) -> None:
        self._bridge.invalidate(icons=True)


class _SelectionObserver(object):
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    # Adding to the selection from outside the panel is what reveals rows;
    # removing and clearing only update them.
    def addSelection(self, doc: Any, obj: Any, sub: Any, pnt: Any) -> None:
        self._bridge.sync_selection()
        self._bridge.picked(str(doc), str(obj), str(sub or ""))

    def removeSelection(self, doc: Any, obj: Any, sub: Any) -> None:
        self._bridge.sync_selection()

    def setSelection(self, doc: Any, *args: Any) -> None:
        self._bridge.sync_selection(picked=True)

    def clearSelection(self, doc: Any) -> None:
        self._bridge.sync_selection()


class Observers(object):
    """Install/remove as a unit. Idempotent in both directions."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge
        self._app: _AppObserver | None = None
        self._gui: _GuiObserver | None = None
        self._sel: _SelectionObserver | None = None
        self._dbl: Any = None

    def install(self) -> None:
        if self._app is not None:
            return
        self._app = _AppObserver(self._bridge)
        self._gui = _GuiObserver(self._bridge)
        self._sel = _SelectionObserver(self._bridge)
        try:
            App.addDocumentObserver(self._app)
        except Exception:
            _err("could not install App observer")
            self._app = None
        try:
            Gui.addDocumentObserver(self._gui)
        except Exception:
            _err("could not install Gui observer")
            self._gui = None
        try:
            Gui.Selection.addObserver(self._sel)
        except Exception:
            _err("could not install selection observer")
            self._sel = None
        try:
            from .face_edit import DoubleClickEditor
            self._dbl = DoubleClickEditor(self._bridge)
            self._dbl.install()
        except Exception:
            _err("could not install the 3D double-click editor")
            self._dbl = None

    def remove(self) -> None:
        if self._app is not None:
            try:
                App.removeDocumentObserver(self._app)
            except Exception:
                _err("could not remove App observer")
            self._app = None
        if self._gui is not None:
            try:
                Gui.removeDocumentObserver(self._gui)
            except Exception:
                _err("could not remove Gui observer")
            self._gui = None
        if self._sel is not None:
            try:
                Gui.Selection.removeObserver(self._sel)
            except Exception:
                _err("could not remove selection observer")
            self._sel = None
        if self._dbl is not None:
            try:
                self._dbl.remove()
            except Exception:
                _err("could not remove the 3D double-click editor")
            self._dbl = None
