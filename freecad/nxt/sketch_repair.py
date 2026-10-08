"""Mending a sketch profile that will not close, without being asked.

"Wire is not closed" is most often one of two things. Two ends that look
joined and are not: those are joined in the sketch, with a coincident
constraint. Or edges the profile was never meant to have - a line drawn
twice, a stray edge, one edge lying over another: those are left in the
sketch, and the feature built on it is pointed at the sketch's closed
regions instead of the whole sketch (the sketch's "MakeInternals"
faces), as a user picking them by hand would. Holes stay holes: a region
inside an odd number of others is left out, as the whole sketch would
leave it.

Only a sketch that is a feature's profile, and only for a feature that
uses the whole sketch and has failed. What it does is said in the undo
toast; what it could not mend is said once, in a toast that stays, with
Edit to open the sketch on the trouble.

It looks at a sketch when its editing ends, when a feature built on it
fails to recompute, and when it is picked while a task is open - the
profile chosen in a Pad's task, say. Outside a task a repair is an undo
step of its own; inside one it is part of the task's, so the task's
Cancel takes it back with everything else, and the toast offers no Undo
of its own. It waits only while the sketch itself is open for editing.
sketch_closure.py does the reasoning.
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
#: A sketch's findings, with the features failing on it: (name, whether
#: it uses the whole sketch). The same again is neither retried nor
#: reported twice; a feature newly failing on it - another one built on
#: it, or one whose repair was cancelled - is something new.
Settled = tuple[Findings, tuple[tuple[str, bool], ...]]

#: The sub-element a closed region of a sketch is, once the sketch makes
#: its internal faces.
REGION = "InternalFace%d"
#: How coarse the mesh a region's inner point is taken from may be, as a
#: fraction of the region's size: only its first triangle is used.
MESH_FRACTION = 0.1

#: What is left to do, in the order the toast lists it: (phrase, the
#: finding it counts).
_LEFT = (
    (QT_TRANSLATE_NOOP("Nxt", "open ends: %d"), "open_ends"),
    (QT_TRANSLATE_NOOP("Nxt", "extra edges: %d"), "surplus"),
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


def _whole(feature: Any) -> bool:
    """Whether a feature takes the whole of its profile, not parts of it."""
    link = feature.Profile
    subs = link[1] if isinstance(link, (tuple, list)) and len(link) > 1 \
        else ()
    return not any(subs)


def _settled(found: Findings, users: list[Any]) -> Settled:
    return found, tuple(sorted((user.Name, _whole(user))
                               for user in users if _failed(user)))


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


def _close_gaps(sketch: Any, gaps: list[Any]) -> bool:
    """Join near-miss ends with coincident constraints.

    False, and taken back, if that leaves the sketch worse constrained.
    """
    import Sketcher
    before, _notes = health.inspect(sketch)
    count = len(sketch.Constraints)
    try:
        for (first, first_end), (second, second_end) in gaps:
            sketch.addConstraint(Sketcher.Constraint(
                "Coincident", first, first_end, second, second_end))
        sketch.solve()
        if health.inspect(sketch)[0] <= before:
            return True
    except Exception:
        _err("could not close the gaps in %s" % sketch.Name)
    try:
        for index in range(len(sketch.Constraints) - 1, count - 1, -1):
            sketch.delConstraint(index)
        sketch.solve()
    except Exception:
        _err("could not take back the constraints added to %s" % sketch.Name)
    return False


def _regions(sketch: Any) -> list[str]:
    """The sketch's closed regions, as profile sub-elements, less holes.

    Its internal faces are every region its edges bound, whatever stray
    or overlapping edges there are. One inside an odd number of others
    is a hole, as it would be in the whole sketch's profile.
    """
    import Part
    faces = sketch.InternalShape.Faces
    outlines = [Part.Face(face.OuterWire) for face in faces]
    kept = []
    for i, face in enumerate(faces):
        points, triangles = face.tessellate(
            face.BoundBox.DiagonalLength * MESH_FRACTION)
        if not triangles:
            continue
        a, b, c = (points[k] for k in triangles[0])
        inside = (a + b + c) * (1 / 3)
        depth = sum(1 for j, outline in enumerate(outlines) if j != i
                    and outline.isInside(inside, sketch_closure.JOINED, True))
        if depth % 2 == 0:
            kept.append(REGION % (i + 1))
    return kept


def _use_regions(sketch: Any, feature: Any) -> int:
    """Point a feature at the sketch's closed regions, not the whole.

    How many regions it now uses: 0, and nothing changed, if that does
    not mend it.
    """
    was = (feature.Profile, sketch.MakeInternals,
           getattr(feature, "AllowMultiFace", None))
    try:
        if not sketch.MakeInternals:
            sketch.MakeInternals = True
            sketch.recompute()
        regions = _regions(sketch)
        if regions:
            if was[2] is not None:
                feature.AllowMultiFace = True
            feature.Profile = (sketch, regions)
            feature.recompute()
            if not _failed(feature):
                return len(regions)
    except Exception:
        _err("could not use the closed regions of %s" % sketch.Name)
    try:
        feature.Profile = was[0]
        sketch.MakeInternals = was[1]
        if was[2] is not None:
            feature.AllowMultiFace = was[2]
        sketch.recompute()
        feature.recompute()
    except Exception:
        _err("could not put back the profile of %s" % feature.Name)
    return 0


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

    def addSelection(  # noqa: N802
            self, doc: str, name: str, *_rest: Any) -> None:
        """A sketch picked while a task is open: a profile being chosen."""
        try:
            if not Gui.Control.activeDialog():
                return
            document = App.getDocument(doc)
        except Exception:
            return
        self._repair.consider(document.getObject(name))


class SketchRepair(QtCore.QObject):
    """Mends the profiles put to it, as soon as it is safe to."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._observer = _Observer(self)
        #: Sketches to look at, in the order they were put.
        self._pending: dict[Key, None] = {}
        #: What was last found in each sketch and dealt with.
        self._settled: dict[Key, Settled] = {}
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._run)

    def install(self) -> None:
        App.addDocumentObserver(self._observer)
        Gui.addDocumentObserver(self._observer)
        Gui.Selection.addObserver(self._observer)

    def remove(self) -> None:
        self._timer.stop()
        for remove in (App.removeDocumentObserver,
                       Gui.removeDocumentObserver,
                       Gui.Selection.removeObserver):
            try:
                remove(self._observer)
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
    def _in_edit(key: Key) -> bool:
        """Whether the sketch itself is open for editing."""
        editing_now = Gui.getDocument(key[0]).getInEdit()
        return getattr(getattr(editing_now, "Object", None), "Name",
                       None) == key[1]

    @staticmethod
    def _in_task(doc_name: str) -> bool:
        """Whether a change now lands in a task's undo step, not its own."""
        return bool(App.getActiveTransaction()) \
            or Gui.getDocument(doc_name).getInEdit() is not None

    def _attend(self, key: Key) -> bool:
        """Deal with one sketch. False if it has to wait."""
        doc, sketch = self._find(key)
        if sketch is None:
            return True
        if self._in_edit(key):
            return False
        users = _users(sketch)
        if not users:
            return True
        found = sketch_closure.inspect(_edges(sketch))
        settled = _settled(found, users)
        if settled == self._settled.get(key):
            return True
        self._settled[key] = settled
        if found.gaps or not found.closed() and settled[1]:
            self._mend(key, doc, sketch, found, users)
        elif not found.closed():
            del self._settled[key]      # mend it if a feature fails on it
        return True

    def _mend(self, key: Key, doc: Any, sketch: Any, found: Findings,
              users: list[Any]) -> None:
        """Close the gaps, then repoint what still fails; say so."""
        own_step = not self._in_task(key[0])
        if own_step:
            doc.openTransaction("Close sketch profile")
        done = []
        if found.gaps and _close_gaps(sketch, found.gaps):
            done.append(translate("Nxt", "gaps closed: %d") % len(found.gaps))
            doc.recompute()
        for feature in users:
            if _failed(feature) and _whole(feature):
                count = _use_regions(sketch, feature)
                if count:
                    done.append(translate(
                        "Nxt", "%s uses its closed profiles: %d")
                        % (feature.Label, count))
        if own_step:
            (doc.commitTransaction if done else doc.abortTransaction)()
        if done:
            doc.recompute()
        left = sketch_closure.inspect(_edges(sketch))
        self._settled[key] = _settled(left, users)
        self._tell(key, doc, sketch, left, done, own_step,
                   any(_failed(user) for user in users))

    def _tell(self, key: Key, doc: Any, sketch: Any, found: Findings,
              done: list[str], undoable: bool, failing: bool) -> None:
        """The toast: what was mended, and what still stops a feature.

        Not `undoable`: the repair was part of a task's undo step.
        """
        repaired = translate("Nxt", "Repaired %s (%s)") % (
            sketch.Label, ", ".join(done))
        left = _counts(_LEFT, found) if failing else []
        if not left:
            if done:
                services.toast(doc, repaired, undoable=undoable)
            return
        if done:
            message = translate("Nxt", "%s; still not closed (%s)") % (
                repaired, ", ".join(left))
        else:
            message = translate("Nxt", "%s is not closed (%s)") % (
                sketch.Label, ", ".join(left))
        actions = [(translate("Nxt", "Edit"),
                    partial(self._edit, key, found))]
        services.toast(doc, message, undoable=bool(done) and undoable,
                       actions=actions, sticky=True)

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
