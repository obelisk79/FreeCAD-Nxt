"""Snap a dragged Pad or Pocket length to a parallel face of the model.

Faces are gathered once per edit; the task panel's length fields are then
polled and set through their rawValue, as their own arrows do.
"""

from __future__ import annotations

import bisect
import contextlib
import traceback
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import fc, settings
from ..core.qt import QtCore, QtWidgets

FEATURES = ("PartDesign::Pad", "PartDesign::Pocket")
LENGTH_TYPES = ("Length", "TwoLengths")
#: Task panel field names for the first and second length.
FORWARD, BACKWARD = "lengthEdit", "lengthEdit2"
#: Snap distance on screen.
SNAP_PIXELS = 10.0
#: Bounds the gathering cost on huge models.
MAX_FACES = 20000
#: Minimum cosine between normals.
PARALLEL = 1.0 - 1e-6
#: Distances closer than this are one face.
SAME = 1e-6
TICK_MS = 33


@dataclass(frozen=True)
class Face:
    """A face the length can snap to: how far along, and which it is."""

    distance: float
    obj: str            # object name
    element: str        # "Face7"


def facing(faces: Iterable[tuple[Any, Any, str, str]], origin: Any,
           direction: Any) -> list[Face]:
    """Faces square to `direction`, sorted and deduped by distance."""
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
    """Positive lengths each face would give this field, ascending."""
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


# -- reading the model --

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
    """The base feature and other visible Bodies (not the own Body)."""
    sources: list[Any] = []
    base = getattr(feature, "BaseFeature", None)
    if base is not None:
        sources.append(base)
    body = None
    with contextlib.suppress(Exception):
        body = feature.getParentGeoFeatureGroup()
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
        except Exception:  # nosec B112  # no shape to snap to
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


# -- the watcher --

def _fields() -> dict[str, Any]:
    """The task's length fields, shown or not.

    Nxt's cards replace the box that holds them, so they are hidden, yet
    every edit, the cards' and the 3D handles', still goes through them.
    """
    found: dict[str, Any] = {}
    for widget in Gui.getMainWindow().findChildren(
            QtWidgets.QAbstractSpinBox):
        name = widget.objectName()
        if name in (FORWARD, BACKWARD):
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
        #: (document, feature) the faces were gathered for.
        self._session: tuple[str, str] | None = None
        self._faces: list[Face] = []
        self._origin: Any = None
        self._direction: Any = None
        self._last: dict[str, float] = {}
        #: (field, face, length) while held on a face.
        self._held: tuple[str, Face, float] | None = None

    def install(self) -> None:
        self._timer.start(TICK_MS)

    def remove(self) -> None:
        self._timer.stop()
        self._unhighlight()

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
                    # The arrow may write its own position on release.
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
            view = fc.active_view()
            if view is None:
                return 0.5
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

    # -- highlight via FreeCAD preselection --

    def _highlight(self, doc_name: str, face: Face) -> None:
        with contextlib.suppress(Exception):
            Gui.Selection.setPreselection(
                App.getDocument(doc_name).getObject(face.obj), face.element)

    def _unhighlight(self) -> None:
        with contextlib.suppress(Exception):
            Gui.Selection.clearPreselection()

    def _release(self) -> None:
        if self._held is not None:
            self._held = None
            self._unhighlight()
