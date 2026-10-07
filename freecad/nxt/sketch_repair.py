"""Closing a sketch profile that all but closes, without being asked.

"Wire is not closed" is most often two ends that look joined and are
not, or an edge drawn twice. When a sketch is the profile of a feature
(a Pad, a Pocket, a Revolution...), this joins such ends with coincident
constraints and deletes such edges, in one undo step of its own, and
says so in the undo toast. What it cannot be sure of - an opening too
wide to be a slip, a stray edge, edges lying over one another - it
leaves alone, and says so once if the feature has failed: in a toast
that stays, with Edit to open the sketch on the trouble, and Repair
where deleting the overlapping edges would close the profile.

It looks at a sketch when its editing ends and when a feature built on
it fails to recompute, and acts once nothing is being edited and no
undo step is open: a repair inside someone else's would be cancelled or
undone along with it. sketch_closure.py does the reasoning.
"""

from __future__ import annotations

import traceback
from functools import partial
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from . import services, sketch_closure
from .i18n import QT_TRANSLATE_NOOP, translate
from .qt import QtCore
from .sketch_closure import END, START, Edge, Findings
from .tree import editing, health, settings

SKETCH = "Sketcher::SketchObject"
LINE = "Part::GeomLineSegment"
ARC = "Part::GeomArcOfCircle"

#: (document, sketch), by name.
Key = tuple[str, str]

#: What a repair did, and what is left to do, in the order the toast
#: lists them: (phrase, the finding it counts).
_DONE = (
    (QT_TRANSLATE_NOOP("Nxt", "gaps closed: %d"), "gaps"),
    (QT_TRANSLATE_NOOP("Nxt", "extra edges removed: %d"), "surplus"),
)
_LEFT = (
    (QT_TRANSLATE_NOOP("Nxt", "open ends: %d"), "open_ends"),
    (QT_TRANSLATE_NOOP("Nxt", "branch points: %d"), "forks"),
    (QT_TRANSLATE_NOOP("Nxt", "overlapping edges: %d"), "overlaps"),
)


def _err(message: str) -> None:
    App.Console.PrintError("Nxt: %s\n" % message)
    App.Console.PrintError(traceback.format_exc())


def _failed(obj: Any) -> bool:
    state = obj.State
    return "Invalid" in state or "Error" in state


def _profile(feature: Any) -> Any:
    """The object a feature takes its profile from, or None."""
    link = getattr(feature, "Profile", None)
    if isinstance(link, (tuple, list)):
        return link[0] if link else None
    return link


def _users(sketch: Any) -> list[Any]:
    """The features this sketch is the profile of."""
    return [user for user in sketch.InList
            if getattr(_profile(user), "Name", None) == sketch.Name]


def _edges(sketch: Any) -> list[Edge]:
    """The sketch's open curves, less its construction geometry."""
    edges = []
    for index, curve in enumerate(sketch.Geometry):
        if sketch.getConstruction(index) or not hasattr(curve, "StartPoint"):
            continue
        # The Sketcher's own idea of which end is which: the constraint
        # that joins two ends names them the same way.
        start, end = (sketch.getPoint(index, pos) for pos in (START, END))
        mid = curve.value((curve.FirstParameter + curve.LastParameter) / 2)
        kind = curve.TypeId
        edges.append(Edge(
            index, (start.x, start.y), (end.x, end.y), (mid.x, mid.y),
            curve.length(), straight=kind == LINE,
            centre=(curve.Center.x, curve.Center.y) if kind == ARC else None))
    return edges


def _apply(doc: Any, sketch: Any, found: Findings) -> bool:
    """Mend the sketch in one undo step.

    False, and no change, if that would leave it worse constrained.
    """
    import Sketcher
    before, _notes = health.inspect(sketch)
    doc.openTransaction("Close sketch profile")
    try:
        for (first, first_end), (second, second_end) in found.gaps:
            sketch.addConstraint(Sketcher.Constraint(
                "Coincident", first, first_end, second, second_end))
        if found.surplus:
            # Highest first: deleting one renumbers those after it.
            sketch.delGeometries(sorted(found.surplus, reverse=True))
        sketch.solve()
        worse = health.inspect(sketch)[0] > before
    except Exception:
        _err("could not close the profile of %s" % sketch.Name)
        worse = True
    if worse:
        doc.abortTransaction()
        return False
    doc.commitTransaction()
    doc.recompute()
    return True


def _counts(phrases: tuple[tuple[str, str], ...],
            found: Findings) -> list[str]:
    """Each phrase whose finding is there, with how many."""
    counted = []
    for phrase, what in phrases:
        value = getattr(found, what)
        count = value if isinstance(value, int) else len(value)
        if count:
            counted.append(translate("Nxt", phrase) % count)
    return counted


class _Observer:
    """Both a document and a view observer: the slots do not overlap."""

    def __init__(self, repair: SketchRepair) -> None:
        self._repair = repair

    def slotResetEdit(self, view_object: Any) -> None:  # noqa: N802
        self._repair.consider(view_object.Object, edited=True)

    def slotRecomputedDocument(self, doc: Any) -> None:  # noqa: N802
        if settings.get("RepairProfiles"):
            for obj in doc.Objects:
                if _failed(obj):
                    self._repair.consider(_profile(obj))
        self._repair.retry()

    def slotCommitTransaction(self, _doc: Any) -> None:  # noqa: N802
        self._repair.retry()

    slotAbortTransaction = slotCommitTransaction  # noqa: N815

    def slotDeletedDocument(self, doc: Any) -> None:  # noqa: N802
        self._repair.forget(getattr(doc, "Document", doc).Name)


class SketchRepair(QtCore.QObject):
    """Mends the profiles put to it, as soon as it is safe to."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._observer = _Observer(self)
        #: Sketches to look at, in the order they were put.
        self._pending: dict[Key, None] = {}
        #: What was last found in each sketch and dealt with: the same
        #: findings again are neither retried nor reported twice.
        self._settled: dict[Key, Findings] = {}
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._run)

    def install(self) -> None:
        App.addDocumentObserver(self._observer)
        Gui.addDocumentObserver(self._observer)

    def remove(self) -> None:
        self._timer.stop()
        for module in (App, Gui):
            try:
                module.removeDocumentObserver(self._observer)
            except Exception:
                pass

    def consider(self, sketch: Any, edited: bool = False) -> None:
        """Look at this sketch soon. `edited`: the user just changed it."""
        if sketch is None or not settings.get("RepairProfiles") \
                or not sketch.isDerivedFrom(SKETCH):
            return
        key = (sketch.Document.Name, sketch.Name)
        if edited:
            self._settled.pop(key, None)
        self._pending[key] = None
        self._timer.start()

    def retry(self) -> None:
        if self._pending:
            self._timer.start()

    def forget(self, doc_name: str) -> None:
        for store in (self._pending, self._settled):
            for key in [key for key in store if key[0] == doc_name]:
                del store[key]

    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        pending, self._pending = self._pending, {}
        for key in pending:
            try:
                if not self._attend(key):
                    self._pending[key] = None
            except Exception:
                _err("could not check the profile of %s" % key[1])

    def _find(self, key: Key) -> tuple[Any, Any]:
        """(document, sketch), either None if it has gone."""
        doc = App.listDocuments().get(key[0])
        return doc, doc.getObject(key[1]) if doc is not None else None

    @staticmethod
    def _busy(doc_name: str) -> bool:
        """Whether a change now would land inside someone else's."""
        return bool(App.getActiveTransaction()) \
            or Gui.getDocument(doc_name).getInEdit() is not None

    def _attend(self, key: Key) -> bool:
        """Deal with one sketch. False if it has to wait."""
        doc, sketch = self._find(key)
        if sketch is None:
            return True
        if self._busy(key[0]):
            return False
        users = _users(sketch)
        if not users:
            return True
        found = sketch_closure.inspect(_edges(sketch))
        if found == self._settled.get(key):
            return True
        self._settled[key] = found
        if found.repairable():
            self._mend(key, doc, sketch, found)
        elif found.closed():
            pass
        elif any(_failed(user) for user in users):
            self._tell(key, doc, sketch, found)
        else:
            del self._settled[key]      # say so if a feature fails on it
        return True

    def _mend(self, key: Key, doc: Any, sketch: Any, fix: Findings) -> None:
        """Apply a fix, and say what it did and what it left."""
        if not _apply(doc, sketch, fix):
            return
        left = sketch_closure.inspect(_edges(sketch))
        self._settled[key] = left
        self._tell(key, doc, sketch, left, _counts(_DONE, fix))

    def _tell(self, key: Key, doc: Any, sketch: Any, found: Findings,
              done: list[str] | None = None) -> None:
        """The toast: what was repaired, and what the user is left with."""
        repaired = translate("Nxt", "Repaired %s (%s)") % (
            sketch.Label, ", ".join(done or ()))
        left = _counts(_LEFT, found)
        if not left:
            services.toast(doc, repaired)
            return
        if done:
            message = translate("Nxt", "%s; still not closed (%s)") % (
                repaired, ", ".join(left))
        else:
            message = translate("Nxt", "%s is not closed (%s)") % (
                sketch.Label, ", ".join(left))
        actions = [(translate("Nxt", "Edit"),
                    partial(self._edit, key, found))]
        if found.removable:
            actions.append((translate("Nxt", "Repair"),
                            partial(self._remove, key, found)))
        services.toast(doc, message, undoable=bool(done), actions=actions,
                       sticky=True)

    # -- the toast's buttons ------------------------------------------------ #

    def _edit(self, key: Key, found: Findings) -> None:
        # Deferred: opening a sketch opens a task, from inside a click.
        QtCore.QTimer.singleShot(0, partial(self._enter, key, found))

    def _enter(self, key: Key, found: Findings) -> None:
        """Open the sketch with its overlapping edges selected."""
        live = services.instance()
        if live is not None:
            live.featurePicked.emit(*key)
        editing.enter_edit(*key)
        try:
            for index in sorted({i for pair in found.overlaps for i in pair}):
                Gui.Selection.addSelection(*key, "Edge%d" % (index + 1))
        except Exception:
            _err("could not select the overlapping edges of %s" % key[1])

    def _remove(self, key: Key, found: Findings) -> None:
        """Delete the overlapping edges the toast offered to."""
        doc, sketch = self._find(key)
        if sketch is None:
            return
        if self._busy(key[0]) \
                or sketch_closure.inspect(_edges(sketch)) != found:
            # Not now, or no longer the sketch the offer was made for:
            # look at it afresh.
            self.consider(sketch, edited=True)
            return
        self._mend(key, doc, sketch, Findings(surplus=found.removable))
