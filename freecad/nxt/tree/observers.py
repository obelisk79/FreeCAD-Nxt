"""Document and selection observers.

All call `bridge.invalidate()`, which coalesces bursts into one rebuild;
selection syncs synchronously.
"""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import fc, log

#: Undrawn properties; skipping them avoids rebuilds during drags.
_IGNORED_PROPERTIES: frozenset[str] = frozenset({
    "Placement", "Shape", "_Body", "AttachmentOffset",
    "ExpressionEngine", "Proxy",
})


class _AppObserver(object):
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    def slotCreatedObject(self, obj: Any) -> None:
        self._bridge.invalidate(icons=True)
        self._bridge.auto_rename.created(obj)
        if not (App.isRestoring() or getattr(obj.Document, "Restoring", False)
                or getattr(obj.Document, "Transacting", False)):
            self._bridge.note_created(obj.Name)

    def slotDeletedObject(self, obj: Any) -> None:
        self._bridge.invalidate()
        self._bridge.auto_rename.deleted(obj)

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

    def slotStartSaveDocument(self, doc: Any, label: str) -> None:
        with contextlib.suppress(Exception):
            self._bridge.save_expansion(doc)

    def slotFinishSaveDocument(self, doc: Any, label: str) -> None:
        self._bridge.invalidate()

    def slotChangedDocument(self, doc: Any, prop: str) -> None:
        if prop == "Label":
            self._bridge.invalidate()


class _GuiObserver(object):
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    # No slotChangedObject: it converts view providers to Python mid-
    # construction, fixing their type at a base class. Visibility comes
    # via the App observer.

    def slotCreatedObject(self, vobj: Any) -> None:
        self._bridge.invalidate(icons=True)

    def slotDeletedObject(self, vobj: Any) -> None:
        self._bridge.invalidate()

    def slotInEdit(self, vobj: Any) -> None:
        self._bridge.invalidate(icons=True)
        obj = fc.object_of(vobj)
        if obj is not None:
            self._bridge.auto_rename.edit_opened(obj)

    def slotResetEdit(self, vobj: Any) -> None:
        self._bridge.invalidate(icons=True)
        obj = fc.object_of(vobj)
        if obj is not None:
            self._bridge.auto_rename.edit_closed(obj)

    def slotActivateDocument(self, doc: Any) -> None:
        self._bridge.invalidate(icons=True)


class _SelectionObserver(object):
    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge

    # Only adding reveals rows; removing and clearing just update them.
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
        self._services: Any = None

    def install(self) -> None:
        if self._app is not None:
            return
        self._app = _AppObserver(self._bridge)
        self._gui = _GuiObserver(self._bridge)
        self._sel = _SelectionObserver(self._bridge)
        try:
            App.addDocumentObserver(self._app)
        except Exception:
            log.error("could not install App observer")
            self._app = None
        try:
            Gui.addDocumentObserver(self._gui)
        except Exception:
            log.error("could not install Gui observer")
            self._gui = None
        try:
            Gui.Selection.addObserver(self._sel)
        except Exception:
            log.error("could not install selection observer")
            self._sel = None
        try:
            from ..app import services
            live = services.start()
            if live is not None:
                live.featurePicked.connect(self._bridge.edit_feature)
                self._services = live
        except Exception:
            log.error("could not connect to the Nxt services")

    def remove(self) -> None:
        if self._app is not None:
            try:
                App.removeDocumentObserver(self._app)
            except Exception:
                log.error("could not remove App observer")
            self._app = None
        if self._gui is not None:
            try:
                Gui.removeDocumentObserver(self._gui)
            except Exception:
                log.error("could not remove Gui observer")
            self._gui = None
        if self._sel is not None:
            try:
                Gui.Selection.removeObserver(self._sel)
            except Exception:
                log.error("could not remove selection observer")
            self._sel = None
        if self._services is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                self._services.featurePicked.disconnect(
                    self._bridge.edit_feature)
            self._services = None
