"""Snap a dragged Pad or Pocket length to a parallel face of the model.

While a Pad or Pocket's length arrow is dragged, a planar face of the
model square to the arrow - the top of a boss, the floor of a pocket,
another body's face - pulls the length onto it once the arrow comes
within a few pixels of it, and holds it there until the arrow is dragged
clear. The face is highlighted while it holds, and the length it set is
exact, not the nearest drag step.

Separate from the tree and from the floating value field: it watches the
edit on its own, reads the task panel's own length fields, and sets them
the way their own arrows do (the spin box's raw value), so the panel, the
arrow and the model stay one thing.

How it works:
  * When a Pad or Pocket is opened for editing, the faces are gathered
    once: every planar face of what the feature is built on (its base
    feature) and of the other visible solids, whose normal lies along
    the extrusion. Each is kept as its distance along that direction
    from the sketch plane. On a big model this is the only real cost,
    and it is bounded (MAX_FACES).
  * Then, at the floating field's pace, the length fields are watched.
    A change while the mouse button is down is a drag. The length is
    compared with the distances - a sorted list, so a lookup - and when
    one is within SNAP_PIXELS on screen the field is set to it.
  * The drag's own steps keep Shift and Ctrl; Alt held turns snapping
    off for as long as it is held.

Lengths, as FreeCAD measures them: the first length runs from the sketch
plane along the extrusion, the second (two lengths) the other way, and a
symmetric length is the whole of it, half either side.
"""

from __future__ import annotations

import bisect
import traceback
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .qt import QtCore, QtWidgets
from .tree import settings

#: The features whose lengths snap, and the length types that are a length.
FEATURES = ("PartDesign::Pad", "PartDesign::Pocket")
LENGTH_TYPES = ("Length", "TwoLengths")
#: The task panel's fields: the first length, and the second.
FORWARD, BACKWARD = "lengthEdit", "lengthEdit2"
#: How near, on screen, the arrow has to come to a face to snap to it.
SNAP_PIXELS = 10.0
#: Faces looked at, at most: a bound on the cost of opening a huge model.
MAX_FACES = 20000
#: How parallel counts as parallel: the cosine between the normals.
PARALLEL = 1.0 - 1e-6
#: Distances closer than this are one face.
SAME = 1e-6
TICK_MS = 33


@dataclass(frozen=True)
class Face:
    """A face the length can snap to: how far along, and which it is."""

    distance: float
    obj: str            # the object it is a face of, by name
    element: str        # "Face7"


def facing(faces: Iterable[tuple[Any, Any, str, str]], origin: Any,
           direction: Any) -> list[Face]:
    """The faces square to `direction`, by distance from `origin`.

    `faces` gives (normal, a point on the face, object, element) for each
    planar face; the vectors need only `dot` and subtraction. Sorted by
    distance, one entry per distance.
    """
    found: dict[float, Face] = {}
    for normal, point, obj, element in faces:
        if abs(normal.dot(direction)) < PARALLEL:
            continue
        distance = (point - origin).dot(direction)
        key = round(distance / SAME)
        found.setdefault(key, Face(distance, obj, element))
    return sorted(found.values(), key=lambda face: face.distance)


def candidates(faces: Sequence[Face], field: str,
               symmetric: bool) -> list[tuple[float, Face]]:
    """What each face would make this field's length, in order.

    The first length reaches forward, the second backward; a symmetric
    length is twice the distance to a face on either side. Lengths of
    zero or less are no length at all.
    """
    out: list[tuple[float, Face]] = []
    for face in faces:
        if symmetric:
            length = 2 * abs(face.distance)
        elif field == BACKWARD:
            length = -face.distance
        else:
            length = face.distance
        if length > SAME:
            out.append((length, face))
    out.sort(key=lambda pair: pair[0])
    return out


def nearest(length: float, lengths: Sequence[tuple[float, Face]],
            tolerance: float) -> tuple[float, Face] | None:
    """The candidate within `tolerance` of `length`, nearest first."""
    if not lengths:
        return None
    keys = [pair[0] for pair in lengths]
    at = bisect.bisect_left(keys, length)
    best = None
    for i in (at - 1, at):
        if 0 <= i < len(lengths):
            gap = abs(lengths[i][0] - length)
            if gap <= tolerance and (best is None or gap < best[0]):
                best = (gap, lengths[i])
    return best[1] if best else None


# --------------------------------------------------------------------------- #
# reading the model
# --------------------------------------------------------------------------- #

def _direction(feature: Any, normal: Any) -> Any:
    """Which way the first length runs, as a unit vector."""
    if getattr(feature, "UseCustomVector", False):
        custom = App.Vector(feature.Direction)
        if custom.Length > 1e-12:
            direction = custom.normalize()
            return -direction if getattr(feature, "Reversed", False) \
                else direction
    direction = App.Vector(normal)
    if feature.isDerivedFrom("PartDesign::Pocket"):
        direction = -direction
    if getattr(feature, "Reversed", False):
        direction = -direction
    return direction


def _sketch_frame(feature: Any) -> tuple[Any, Any] | None:
    """The sketch plane's origin and normal, in the document's frame."""
    profile = getattr(feature, "Profile", None)
    sketch: Any = profile
    if isinstance(profile, (list, tuple)):
        sketch = profile[0] if profile else None
    if sketch is None:
        return None
    try:
        placement = sketch.getGlobalPlacement()
    except Exception:
        placement = sketch.Placement
    normal = placement.Rotation.multVec(App.Vector(0, 0, 1))
    return placement.Base, normal


def _sources(feature: Any) -> list[Any]:
    """What can be snapped to: the base it is built on, and other solids.

    Not the feature itself, nor its own Body, whose shape is the result.
    """
    sources: list[Any] = []
    base = getattr(feature, "BaseFeature", None)
    if base is not None:
        sources.append(base)
    body = None
    try:
        body = feature.getParentGeoFeatureGroup()
    except Exception:
        pass
    for obj in feature.Document.Objects:
        if obj is feature or obj is body or obj is base:
            continue
        if not obj.isDerivedFrom("PartDesign::Body"):
            continue
        view = getattr(obj, "ViewObject", None)
        if view is not None and view.Visibility:
            sources.append(obj)
    return sources


Planar = tuple[Any, Any, str, str]


def _planar_faces(sources: Iterable[Any]) -> Iterable[Planar]:
    """(normal, point, object, element) for each planar face, bounded."""
    seen = 0
    for obj in sources:
        try:
            faces = obj.Shape.Faces
        except Exception:
            continue
        for index, face in enumerate(faces, start=1):
            seen += 1
            if seen > MAX_FACES:
                return
            surface = face.Surface
            if type(surface).__name__ != "Plane":
                continue
            yield (surface.Axis, face.Vertexes[0].Point if face.Vertexes
                   else surface.Position, obj.Name, "Face%d" % index)


def gather(feature: Any) -> tuple[list[Face], Any, Any] | None:
    """The faces a feature's length can snap to, with its frame."""
    frame = _sketch_frame(feature)
    if frame is None:
        return None
    origin, normal = frame
    direction = _direction(feature, normal)
    faces = facing(_planar_faces(_sources(feature)), origin, direction)
    return faces, origin, direction


# --------------------------------------------------------------------------- #
# the watcher
# --------------------------------------------------------------------------- #

def _fields() -> dict[str, Any]:
    found: dict[str, Any] = {}
    for widget in Gui.getMainWindow().findChildren(
            QtWidgets.QAbstractSpinBox):
        name = widget.objectName()
        if name in (FORWARD, BACKWARD) and widget.isVisible():
            found[name] = widget
    return found


def _raw(spin: Any) -> float | None:
    try:
        return float(spin.property("rawValue"))
    except (TypeError, ValueError, RuntimeError):
        return None


class FaceSnap(QtCore.QObject):
    """Watches a Pad or Pocket edit, and snaps its length to faces."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        #: The edit the faces were gathered for: (document, feature).
        self._session: tuple[str, str] | None = None
        self._faces: list[Face] = []
        self._origin: Any = None
        self._direction: Any = None
        self._last: dict[str, float] = {}
        #: The face the length is held on, while it is: (field, face,
        #: the length it gives).
        self._held: tuple[str, Face, float] | None = None

    def install(self) -> None:
        self._timer.start(TICK_MS)

    def remove(self) -> None:
        self._timer.stop()
        self._unhighlight()

    # ------------------------------------------------------------------

    def _tick(self) -> None:
        try:
            self._update()
        except Exception:
            App.Console.PrintLog("Nxt face snap: %s\n"
                                 % traceback.format_exc())
            self._release()

    def _update(self) -> None:
        feature = self._editing()
        if feature is None:
            self._session = None
            self._release()
            return
        session = (feature.Document.Name, feature.Name)
        if session != self._session:
            self._session = session
            self._last = {}
            self._release()
            gathered = gather(feature)
            self._faces, self._origin, self._direction = gathered or (
                [], None, None)
        if not self._faces or getattr(feature, "Type", "") not in \
                LENGTH_TYPES:
            return
        buttons = QtWidgets.QApplication.mouseButtons()
        dragging = bool(buttons & QtCore.Qt.MouseButton.LeftButton)
        held_off = bool(QtWidgets.QApplication.queryKeyboardModifiers()
                        & QtCore.Qt.KeyboardModifier.AltModifier)
        for name, spin in _fields().items():
            value = _raw(spin)
            if value is None:
                continue
            before = self._last.get(name)
            self._last[name] = value
            moved = before is not None and abs(value - before) > SAME
            if not dragging:
                if self._held and self._held[0] == name:
                    # Let go on a face: the length is that face's, even
                    # if the arrow wrote its own last position after.
                    if abs(value - self._held[2]) > SAME:
                        spin.setProperty("rawValue", self._held[2])
                        self._last[name] = self._held[2]
                    self._release()
                continue
            if held_off:
                if self._held:
                    self._release()
                continue
            if not moved and not (self._held and self._held[0] == name):
                continue
            self._snap(feature, name, spin, value)

    def _snap(self, feature: Any, name: str, spin: Any,
              value: float) -> None:
        lengths = candidates(self._faces, name,
                             bool(getattr(feature, "Midplane", False)))
        tolerance = self._tolerance(value, name)
        hit = nearest(value, lengths, tolerance)
        if hit is None:
            if self._held and self._held[0] == name:
                self._release()
            return
        length, face = hit
        if abs(value - length) > SAME:
            spin.setProperty("rawValue", length)
            self._last[name] = length
        if self._held is None or self._held[:2] != (name, face):
            self._held = (name, face, length)
            self._highlight(feature.Document.Name, face)

    def _tolerance(self, value: float, name: str) -> float:
        """SNAP_PIXELS on screen, as a length along the extrusion."""
        try:
            view = Gui.ActiveDocument.ActiveView
            sign = -1.0 if name == BACKWARD else 1.0
            here = self._origin + self._direction * (sign * value)
            there = self._origin + self._direction * (sign * (value + 1.0))
            a = view.getPointOnViewport(here)
            b = view.getPointOnViewport(there)
            per_mm = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            ratio = QtWidgets.QApplication.primaryScreen() \
                .devicePixelRatio() or 1.0
            per_mm /= ratio
        except Exception:
            return 0.5
        if per_mm < 1e-9:
            return 0.0      # looking straight down the arrow: no snap
        return SNAP_PIXELS / per_mm

    @staticmethod
    def _editing() -> Any:
        if not settings.get("SnapToFaces"):
            return None
        gui_doc = Gui.ActiveDocument
        edit = gui_doc.getInEdit() if gui_doc is not None else None
        feature = getattr(edit, "Object", None)
        if feature is None or str(feature.TypeId) not in FEATURES:
            return None
        return feature

    # -- the highlight: FreeCAD's own preselection --------------------------

    def _highlight(self, doc_name: str, face: Face) -> None:
        try:
            Gui.Selection.setPreselection(
                App.getDocument(doc_name).getObject(face.obj), face.element)
        except Exception:
            pass

    def _unhighlight(self) -> None:
        try:
            Gui.Selection.clearPreselection()
        except Exception:
            pass

    def _release(self) -> None:
        if self._held is not None:
            self._held = None
            self._unhighlight()
