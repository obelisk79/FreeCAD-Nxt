"""Isolate: show only some objects in the 3D view, for a while.

A view mode, not an edit: no undo step, and the document's modified
mark is cleared again where FreeCAD allows. Saves keep the prior view.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..app.i18n import translate
from ..core import log
from ..core.qt import QtCore

# -- plan: which objects to show and hide --


def _members(obj: Any) -> list[Any]:
    """What `obj` contains: its Group, and a Body's or Part's Origin."""
    out = list(getattr(obj, "Group", None) or [])
    origin = getattr(obj, "Origin", None)
    if origin is not None and hasattr(origin, "Name"):
        out.append(origin)
    return out


def parents(obj: Any) -> list[Any]:
    """The containers that hold `obj` directly."""
    return [p for p in (getattr(obj, "InList", None) or [])
            if any(m is obj or getattr(m, "Name", None) == obj.Name
                   for m in _members(p))]


def ancestors(obj: Any) -> set[str]:
    seen: set[str] = set()
    stack = parents(obj)
    while stack:
        parent = stack.pop()
        if parent.Name in seen:
            continue
        seen.add(parent.Name)
        stack.extend(parents(parent))
    return seen


def descendants(obj: Any) -> set[str]:
    seen: set[str] = set()
    stack = _members(obj)
    while stack:
        child = stack.pop()
        if child.Name in seen:
            continue
        seen.add(child.Name)
        stack.extend(_members(child))
    return seen


def plan(objects: Iterable[Any], targets: Iterable[Any]
         ) -> tuple[set[str], dict[str, bool]]:
    """(kept names, name -> new visibility for objects that change)."""
    targets = list(targets)
    inside: set[str] = set()
    above: set[str] = set()
    for target in targets:
        inside |= descendants(target)
        above |= ancestors(target)
    names = {t.Name for t in targets}
    kept = names | inside | above

    changes: dict[str, bool] = {}
    for obj in objects:
        view = getattr(obj, "ViewObject", None)
        if view is None:
            continue
        shown = bool(getattr(view, "Visibility", False))
        if obj.Name in names or obj.Name in above:
            if not shown:
                changes[obj.Name] = True
        elif obj.Name in inside:
            continue                    # left as the user had it
        elif shown:
            changes[obj.Name] = False
    return kept, changes


# -- the mode --

#: Passes over the saved visibility; each settles what the last upset.
RESTORE_ROUNDS = 4


def _visibility(doc: Any) -> dict[str, bool]:
    """Every object's visibility, not only the changed ones.

    FreeCAD hides a Body's other features itself when one is shown.
    """
    return {o.Name: bool(o.ViewObject.Visibility) for o in doc.Objects
            if getattr(o, "ViewObject", None) is not None}


class Isolation(QtCore.QObject):
    """The isolate mode, for one document at a time."""

    changed = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._doc: str | None = None
        self._targets: list[str] = []
        self._labels: list[str] = []
        self._kept: set[str] = set()
        self._saved: dict[str, bool] = {}
        self._changes: dict[str, bool] = {}
        self._was_modified: bool | None = None
        self._saving = False

    # -- state --

    def active(self) -> bool:
        return self._doc is not None

    def document(self) -> str | None:
        return self._doc

    def targets(self) -> list[str]:
        return list(self._targets)

    def kept(self) -> set[str]:
        """Targets, their containers and their contents."""
        return set(self._kept)

    def text(self) -> str:
        """The notice text."""
        if not self.active():
            return ""
        if len(self._labels) == 1:
            return translate("Nxt", "Isolated: %1").replace(
                "%1", self._labels[0])
        return translate("Nxt", "Isolated: %1 objects").replace(
            "%1", str(len(self._labels)))

    # -- QML API --

    @QtCore.Property(bool, notify=changed)
    def isActive(self) -> bool:  # noqa: N802 - QML API
        return self.active()

    @QtCore.Property(str, notify=changed)
    def notice(self) -> str:
        return self.text()

    @QtCore.Property("QVariantMap", notify=changed)  # type: ignore[arg-type]
    def keptNames(self) -> dict[str, bool]:  # noqa: N802 - QML API
        """Kept names as a map; the tree dims rows not in it."""
        return {name: True for name in self._kept}

    @QtCore.Slot(result=bool)
    def leave(self) -> bool:
        return self.exit()

    # -- entering and leaving --

    def toggle(self, names: Iterable[str],
               doc_name: str | None = None) -> None:
        if self.active():
            self.exit()
        else:
            self.isolate(names, doc_name)

    def toggle_selection(self) -> None:
        if self.active():
            self.exit()
            return
        doc = App.ActiveDocument
        if doc is None:
            return
        names = [o.Name for o in Gui.Selection.getSelection(doc.Name)]
        self.isolate(names, doc.Name)

    def isolate(self, names: Iterable[str],
                doc_name: str | None = None) -> bool:
        """Enter the mode. False if there was nothing to isolate."""
        if self.active():
            self.exit()
        doc = (App.getDocument(doc_name) if doc_name
               else App.ActiveDocument)
        if doc is None:
            return False
        targets = [o for o in (doc.getObject(n) for n in names)
                   if o is not None and getattr(o, "ViewObject", None)]
        if not targets:
            return False
        kept, changes = plan(doc.Objects, targets)
        self._was_modified = self._modified(doc.Name)
        saved = _visibility(doc)
        try:
            for name, shown in changes.items():
                doc.getObject(name).ViewObject.Visibility = shown
        except Exception:
            log.error("could not isolate")
            self._restore(doc.Name, saved)
            return False
        self._doc = doc.Name
        self._targets = [t.Name for t in targets]
        self._labels = [t.Label for t in targets]
        self._kept = kept
        self._saved = saved
        self._changes = dict(changes)
        self._reset_modified()
        self.changed.emit()
        return True

    def exit(self) -> bool:
        """Leave the mode, restoring visibility. False if off."""
        if not self.active():
            return False
        doc_name = self._doc
        self._restore(doc_name, self._saved)
        self._reset_modified()
        self._doc = None
        self._targets, self._labels = [], []
        self._kept, self._saved, self._changes = set(), {}, {}
        self._was_modified = None
        self.changed.emit()
        return True

    # -- helpers --

    @staticmethod
    def _restore(doc_name: str | None, saved: dict[str, bool]) -> None:
        try:
            doc = App.getDocument(doc_name) if doc_name else None
        except Exception:
            doc = None                  # closed
        if doc is None:
            return
        # Hide first: showing a Body feature hides its siblings. Showing
        # one object can change others too (a group, such as an
        # assembly's Joints, shows what it holds), so go round again
        # until every object is as it was.
        for _round in range(RESTORE_ROUNDS):
            wrong = False
            for name, shown in sorted(saved.items(), key=lambda kv: kv[1]):
                obj = doc.getObject(name)
                view = getattr(obj, "ViewObject", None)
                if view is None:
                    continue            # deleted meanwhile
                try:
                    if bool(view.Visibility) != shown:
                        view.Visibility = shown
                        wrong = True
                except Exception:
                    log.error("could not restore the visibility of %s"
                              % name)
            if not wrong:
                return

    @staticmethod
    def _modified(doc_name: str) -> bool | None:
        try:
            return bool(Gui.getDocument(doc_name).Modified)
        except Exception:
            return None

    def _reset_modified(self) -> None:
        """Clear the modified mark if the document was clean going in."""
        if self._was_modified is not False or self._doc is None:
            return
        try:
            gui_doc: Any = Gui.getDocument(self._doc)   # stubs: read-only
            gui_doc.Modified = False
        except Exception:
            pass                        # read-only in this build: harmless

    # -- document events --

    def document_closed(self, doc_name: str) -> None:
        if doc_name == self._doc:
            self._saved = {}            # nothing left to put back
            self.exit()

    def document_activated(self, doc_name: str) -> None:
        if self.active() and doc_name != self._doc:
            self.exit()

    def object_deleted(self, doc_name: str, name: str) -> None:
        if doc_name != self._doc:
            return
        self._saved.pop(name, None)
        if name in self._targets:
            self.exit()

    def saving(self, doc_name: str) -> None:
        """Lift the mode so the saved file keeps the user's view."""
        if doc_name != self._doc or self._saving:
            return
        self._saving = True
        self._restore(doc_name, self._saved)

    def saved(self, doc_name: str) -> None:
        if doc_name != self._doc or not self._saving:
            return
        self._saving = False
        self._restore(doc_name, self._changes)
        self._reset_modified()


class Observer:
    """App document events the mode follows."""

    def __init__(self, isolation: Isolation) -> None:
        self._isolation = isolation

    def slotDeletedDocument(self, doc: Any) -> None:  # noqa: N802
        self._isolation.document_closed(doc.Name)

    def slotActivateDocument(self, doc: Any) -> None:  # noqa: N802
        self._isolation.document_activated(doc.Name)

    def slotDeletedObject(self, obj: Any) -> None:  # noqa: N802
        doc = getattr(obj, "Document", None)
        if doc is not None:
            self._isolation.object_deleted(doc.Name, obj.Name)

    def slotStartSaveDocument(self, doc: Any, _path: Any) -> None:  # noqa: N802
        self._isolation.saving(doc.Name)

    def slotFinishSaveDocument(self, doc: Any, _path: Any) -> None:  # noqa: N802
        self._isolation.saved(doc.Name)
