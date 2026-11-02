"""The Nxt fillet's and chamfer's task panel: QML in FreeCAD's task view.

FreeCAD hosts it as one QQuickWidget and draws its own OK and Cancel;
everything inside is FilletTask.qml, talking to FilletBridge. Picks in
the 3D view add or remove the base feature's edges; a face adds its
edges. Each change recomputes the feature after a short pause, which is
the live preview, and refreshes each edge's fit.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any, NamedTuple

import FreeCAD as App
import FreeCADGui as Gui
import Part

from ..app.i18n import translate
from ..core import units, view3d, widgets
from ..core.qt import QtCore, QtWidgets
from ..ui import quick_host
from . import blend_fillet, expressions
from .float_input import Field
from .section_field import _Floating

#: One wheel notch on the floating radius box, in mm.
STEP = 0.1
#: Longest wait from a change to its preview, in ms.
SETTLE_MS = 200


class Kind(NamedTuple):
    """What differs between the fillet's panel and the chamfer's."""

    flat: bool
    title: str
    size: str           # the feature's size property
    label: str


FILLET = Kind(False, "Nxt fillet", "Radius", "Radius")
CHAMFER = Kind(True, "Nxt chamfer", "Size", "Distance")


def kind_of(obj: Any) -> Kind:
    return CHAMFER if getattr(obj.Proxy, "FLAT", False) else FILLET


def length_text(value: float) -> str:
    """A length as FreeCAD shows it, in the user's units."""
    try:
        return str(App.Units.Quantity(value, App.Units.Length).UserString)
    except Exception:
        return "%g mm" % value


def base_element(base: Any, picked: Any) -> str:
    """The base's edge or face that a picked element of the result is.

    Edges the fillet leaves alone survive, trimmed at most, so the base
    edge passing through the picked one's middle along the same line is
    it; a face is matched the same way by a point inside it.
    """
    tolerance = max(base.BoundBox.DiagonalLength * 1e-7, 1e-7)
    if picked.ShapeType == "Edge":
        middle = (picked.FirstParameter + picked.LastParameter) / 2
        point = picked.valueAt(middle)
        candidates = enumerate(base.Edges)
        kind = "Edge"
    elif picked.ShapeType == "Face":
        u0, u1, v0, v1 = picked.ParameterRange
        point = picked.valueAt((u0 + u1) / 2, (v0 + v1) / 2)
        if not picked.isInside(point, tolerance, True):
            point = picked.Vertexes[0].Point if not picked.Edges else \
                picked.Edges[0].valueAt(
                    (picked.Edges[0].FirstParameter
                     + picked.Edges[0].LastParameter) / 2)
        candidates = enumerate(base.Faces)
        kind = "Face"
    else:
        return ""
    vertex = Part.Vertex(point)
    best, found = tolerance, ""
    for index, element in candidates:
        gap = element.distToShape(vertex)[0]
        if gap <= best:
            best, found = gap, "%s%d" % (kind, index + 1)
    return found


class RadiusField(Field):
    """The size, as the floating box at the arrow's tip reads and sets it.

    "=..." binds an expression to the feature's size, as the task
    fields of Part Design features do.
    """

    def __init__(self, task: FilletTask) -> None:
        super().__init__()
        self._task = task
        self._label = translate("Nxt", task.kind.label)

    def sync(self) -> None:
        text = length_text(self._task.radius)
        if text != self._text:
            self._text = text
            self.textChanged.emit()

    def _type(self, text: str) -> bool:
        source = text.strip()
        if source.startswith("="):
            obj = self._task.obj
            try:
                expression = expressions.strip_marker(source)
                obj.setExpression(self._task.kind.size, expression)
                value = obj.evalExpression(expression)
                value = float(getattr(value, "Value", value))
            except Exception as exc:
                App.Console.PrintWarning(
                    "Nxt: could not bind %r: %s\n" % (text, exc))
                return False
        else:
            parsed = units.internal_value(text, "mm")
            if parsed is None or parsed <= 0:
                App.Console.PrintWarning(
                    "Nxt: %r is not a length FreeCAD can read\n" % text)
                return False
            value = parsed
        self._task.set_radius(value)
        return True

    @QtCore.Slot(str)
    def finish(self, text: str) -> None:
        """Enter: keep the value and finish the edit, as the task's OK.

        Deferred: OK closes this box's own view, from inside its key.
        """
        if self._type(text):
            QtCore.QTimer.singleShot(0, self._task.accept)
        self.sync()

    @QtCore.Slot(int, result=str)
    def stepped(self, steps: int) -> str:
        return length_text(max(STEP, self._task.radius + steps * STEP))

    @QtCore.Slot()
    def release(self) -> None:
        """Enter or Escape: the keyboard goes back to the 3D view."""
        viewport = view3d.active_viewport()
        if viewport is not None:
            viewport.setFocus()


class RadiusBox(_Floating):
    """The radius field, beside the first arrow's tip."""

    source = "FloatingValue.qml"

    def __init__(self, task: FilletTask) -> None:
        super().__init__()
        self.field = RadiusField(task)
        self._claimed = False
        # As the floating fields of Part Design features: a click in the
        # box gives it the keyboard, and it takes it once when it opens.
        self.field.grabbed.connect(self._take_keyboard)

    def context(self) -> dict[str, Any]:
        return {"expressions": expressions.helper(), "field": self.field}

    def refresh(self) -> None:
        self.field.sync()

    def place(self, view: Any, tip: Any) -> None:
        super().place(view, tip)
        if not self._claimed and widgets.alive(self._widget) \
                and self._widget.isVisible():
            self._claimed = True
            QtCore.QTimer.singleShot(
                0, lambda: self.field.focusRequested.emit(True))

    def _take_keyboard(self) -> None:
        widget = self._widget
        if widgets.alive(widget) and widget.isVisible():
            widget.activateWindow()
            widget.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)


class FilletBridge(QtCore.QObject):
    """What FilletTask.qml shows and changes."""

    changed = QtCore.Signal()

    def __init__(self, task: FilletTask) -> None:
        super().__init__()
        self._task = task
        self._radius_text = length_text(task.radius)

    @QtCore.Property(bool, constant=True)
    def flat(self) -> bool:
        return self._task.kind.flat

    @QtCore.Property(str, notify=changed)
    def radiusText(self) -> str:  # noqa: N802 - QML API
        return self._radius_text

    @QtCore.Property(str, notify=changed)
    def radiusNumber(self) -> str:  # noqa: N802 - QML API
        return units.split_number_and_unit(self._radius_text)[0]

    @QtCore.Property(str, notify=changed)
    def radiusUnit(self) -> str:  # noqa: N802 - QML API
        return units.split_number_and_unit(self._radius_text)[1]

    @QtCore.Property(float, notify=changed)
    def radius(self) -> float:
        return self._task.radius

    @QtCore.Property(float, notify=changed)
    def fits(self) -> float:
        """The largest radius every edge takes; -1 when all fit."""
        return self._task.fits()

    @QtCore.Property(str, notify=changed)
    def fitsText(self) -> str:  # noqa: N802 - QML API
        fits = self._task.fits()
        return length_text(fits) if fits >= 0 else ""

    @QtCore.Property(int, notify=changed)
    def failing(self) -> int:
        return sum(self._task.limit_of(n) is not None
                   for n in self._task.edge_names())

    @QtCore.Property(list, notify=changed)
    def edges(self) -> list[dict[str, Any]]:
        out = []
        for name in self._task.edge_names():
            limit = self._task.limit_of(name)
            out.append({"name": name, "short": limit is not None,
                        "limit": ("" if limit is None else
                                  "none fits" if limit <= 0 else
                                  length_text(limit) + " max")})
        return out

    @QtCore.Property(str, notify=changed)
    def source(self) -> str:
        base = self._task.base
        return base.Label if base is not None else ""

    @QtCore.Property(bool, notify=changed)
    def useAllEdges(self) -> bool:  # noqa: N802 - QML API
        return bool(getattr(self._task.obj, "UseAllEdges", False))

    @QtCore.Property(bool, notify=changed)
    def tangentEdges(self) -> bool:  # noqa: N802 - QML API
        return bool(getattr(self._task.obj, "TangentEdges", False))

    @QtCore.Slot(bool)
    def setTangentEdges(self, on: bool) -> None:  # noqa: N802 - QML API
        self._task.set_property("TangentEdges", on)

    @QtCore.Property(bool, notify=changed)
    def triangleCorners(self) -> bool:  # noqa: N802 - QML API
        return getattr(self._task.obj, "Corners",
                       blend_fillet.CORNERS[0]) == blend_fillet.CORNERS[0]

    @QtCore.Slot(bool)
    def setTriangleCorners(self, on: bool) -> None:  # noqa: N802 - QML API
        self._task.set_property("Corners",
                                blend_fillet.CORNERS[0 if on else 1])

    @QtCore.Property(bool, notify=changed)
    def refine(self) -> bool:
        return bool(getattr(self._task.obj, "Refine", True))

    @QtCore.Property(bool, notify=changed)
    def preview(self) -> bool:
        return self._task.preview_on

    @QtCore.Slot(bool)
    def setPreview(self, on: bool) -> None:  # noqa: N802 - QML API
        self._task.set_preview(on)

    @QtCore.Slot(str, result=bool)
    def setRadiusText(self, text: str) -> bool:  # noqa: N802 - QML API
        value = units.internal_value(
            text, units.split_number_and_unit(self._radius_text)[1])
        if value is None or value <= 0:
            return False
        self._task.set_radius(value)
        return True

    @QtCore.Slot(int, bool)
    def step(self, steps: int, fine: bool) -> None:
        """Up or down by a whole unit, or a tenth with `fine`."""
        unit = units.split_number_and_unit(self._radius_text)[1]
        one = units.internal_value("1", unit) or 1.0
        size = one * (0.1 if fine else 1.0)
        value = round((self._task.radius + steps * size) / size) * size
        if value > 0:
            self._task.set_radius(round(value, 6))

    @QtCore.Slot(int, int)
    def stepBy(self, steps: int, modifiers: int) -> None:  # noqa: N802
        """A wheel turn, by the drag handles' fine or coarse step."""
        from . import gizmos
        size = gizmos.wheel_step(gizmos.read(), "mm", modifiers)
        value = round((self._task.radius + steps * size) / size) * size
        if value > 0:
            self._task.set_radius(round(value, 6))

    @QtCore.Slot()
    def useFits(self) -> None:  # noqa: N802 - QML API
        fits = self._task.fits()
        if fits > 0:
            # Just under, so rounding in the display cannot overshoot.
            self._task.set_radius(int(fits * 100) / 100.0)

    @QtCore.Slot(str)
    def remove(self, name: str) -> None:
        self._task.toggle([name], add=False)

    @QtCore.Slot()
    def clear(self) -> None:
        self._task.set_names([])

    @QtCore.Slot(bool)
    def setUseAllEdges(self, on: bool) -> None:  # noqa: N802 - QML API
        self._task.set_property("UseAllEdges", on)

    @QtCore.Slot(bool)
    def setRefine(self, on: bool) -> None:  # noqa: N802 - QML API
        self._task.set_property("Refine", on)

    @QtCore.Slot(str)
    def hover(self, name: str) -> None:
        self._task.preselect(name)

    def refresh(self) -> None:
        self._radius_text = length_text(self._task.radius)
        self.changed.emit()


class MouseRelease(QtCore.QObject):
    """Calls `released` once a mouse button is let go, anywhere."""

    def __init__(self, released: Any) -> None:
        super().__init__()
        self._released = released

    def eventFilter(self, _obj: Any, event: Any) -> bool:  # noqa: N802
        if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            # After the dragger has had the release too.
            QtCore.QTimer.singleShot(0, self._released)
        return False


class FilletTask:
    """FreeCAD's task dialog for one Nxt fillet or chamfer."""

    def __init__(self, obj: Any, created: bool) -> None:
        self.obj = obj
        self.kind = kind_of(obj)
        self.doc = obj.Document
        self.base = obj.BaseFeature
        self.created = created
        self.radius = float(getattr(obj, self.kind.size))
        self.limits: dict[str, float] = {}
        self.preview_on = True
        if not created:
            self.doc.openTransaction("Edit " + self.kind.title)
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(SETTLE_MS)
        self._timer.timeout.connect(self._recompute)
        self._release = MouseRelease(lambda: self._held(False))
        self.bridge = FilletBridge(self)
        from ..app import services
        from ..ui.theme import Theme
        theme = services.theme() or Theme(None)
        self.form = quick_host.make_view(
            None, "FilletTask.qml", {"theme": theme, "task": self.bridge})
        self.form.setWindowTitle(self.kind.title)
        self.bridge.setParent(self.form)
        root = self.form.rootObject()
        # Resized later, never inside the frame that changed the height:
        # that nests the view's render and Qt Quick refuses it.
        root.implicitHeightChanged.connect(
            lambda: QtCore.QTimer.singleShot(0, self._fit_height))
        QtCore.QTimer.singleShot(0, self._fit_height)
        self._handles: Any = None
        self._box = RadiusBox(self)
        self._view: Any = None
        self._start_view()
        self._show_base(True)
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)
        self._recompute()

    # -- FreeCAD task dialog --

    def getStandardButtons(self) -> int:  # noqa: N802 - FreeCAD API
        buttons = QtWidgets.QDialogButtonBox.StandardButton
        return int((buttons.Ok | buttons.Cancel).value)

    def accept(self) -> bool:
        self._timer.stop()
        self._apply()
        self._finish()
        self.obj.Proxy.editing = False
        self.obj.Proxy.dragging = False
        self.obj.touch()
        self.doc.recompute()
        self.doc.commitTransaction()
        self._show_base(False)
        Gui.Control.closeDialog()
        return True

    def reject(self) -> bool:
        self._timer.stop()
        self._finish()
        self.obj.Proxy.editing = False
        self.obj.Proxy.dragging = False
        self.doc.abortTransaction()
        self.doc.recompute()
        if not self.created:
            self._show_base(False)
        elif self.base is not None and self.base.ViewObject is not None:
            self.base.ViewObject.Visibility = True
        Gui.Control.closeDialog()
        return True

    # -- picking in the 3D view --

    def addSelection(self, doc: str, name: str, sub: str,  # noqa: N802
                     _point: Any = None) -> None:
        if not sub or doc != self.doc.Name:
            return
        picked = self.doc.getObject(name)
        try:
            owner, _mapped, element = picked.resolveSubElement(sub)
        except Exception:
            return
        element = (element or "").lstrip("?")
        if owner is None or self.base is None:
            return
        if owner.Name == self.obj.Name:
            # The preview is what shows: find the base's own element.
            element = base_element(self.base.Shape,
                                   self.obj.Shape.getElement(element))
        elif owner.Name != self.base.Name:
            return
        if not element.startswith(("Edge", "Face")):
            return
        names = [element]
        current = set(self.edge_names())
        self.toggle(names, add=not all(n in current for n in names))
        QtCore.QTimer.singleShot(0, Gui.Selection.clearSelection)

    # -- changes from the panel --

    def edge_names(self) -> list[str]:
        if getattr(self.obj, "UseAllEdges", False) and self.base is not None:
            return ["Edge%d" % (i + 1)
                    for i in range(len(self.base.Shape.Edges))]
        return [n for _owner, names in self.obj.Edges for n in names]

    def limit_of(self, name: str) -> float | None:
        """The largest size `name` takes, if not this one.

        For a face, the smallest over its edges.
        """
        if not name.startswith("Face") or self.base is None:
            return self.limits.get(name)
        found = [self.limits[n] for n in
                 blend_fillet.face_edges(self.base.Shape, name)
                 if n in self.limits]
        return min(found) if found else None

    def set_names(self, names: list[str]) -> None:
        self.obj.Edges = [(self.base, names)] if names else []
        self._changed()

    def toggle(self, names: list[str], add: bool) -> None:
        current = [n for _owner, ns in self.obj.Edges for n in ns]
        if add:
            current += [n for n in names if n not in current]
        else:
            current = [n for n in current if n not in names]
        self.set_names(current)

    def set_radius(self, value: float, dragged: bool = False) -> None:
        if abs(value - self.radius) <= 1e-5 * max(1.0, value):
            return
        self.radius = value
        if dragged:
            self._held(True)
        if self._handles is not None and not dragged:
            self._handles.set_radius(value)
        self._changed()
        self._place_box()

    def set_preview(self, on: bool) -> None:
        self.preview_on = on
        self._show_preview(on)
        self.bridge.refresh()

    def _show_preview(self, on: bool) -> None:
        """Part Design's own preview of the feature, where FreeCAD has it."""
        view = self.obj.ViewObject
        if view is not None and hasattr(view, "showPreview"):
            view.showPreview(on)

    def set_property(self, name: str, value: Any) -> None:
        setattr(self.obj, name, value)
        self._changed()

    def fits(self) -> float:
        """The largest radius all edges take, or -1 when all fit."""
        if not self.limits:
            return -1.0
        return min(self.limits.values())

    def preselect(self, name: str) -> None:
        with contextlib.suppress(Exception):
            Gui.Selection.clearPreselection()
            if name and self.base is not None:
                Gui.Selection.setPreselection(self.base, name)

    # -- internals --

    def _changed(self) -> None:
        self.bridge.refresh()
        # A throttle, not a debounce: a steady drag still previews.
        if not self._timer.isActive():
            self._timer.start()

    def _held(self, holding: bool) -> None:
        """While a handle is held, previews skip what only matters at rest.

        Told from the mouse, not the dragger: pivy crashes calling Python
        from a dragger's start and finish callbacks.
        """
        if holding == bool(getattr(self.obj.Proxy, "dragging", False)):
            return
        self.obj.Proxy.dragging = holding
        app: Any = QtWidgets.QApplication.instance()
        if holding:
            app.installEventFilter(self._release)
            return
        app.removeEventFilter(self._release)
        self._timer.stop()
        self._recompute()

    def _apply(self) -> None:
        if abs(float(getattr(self.obj, self.kind.size))
               - self.radius) > 1e-9:
            setattr(self.obj, self.kind.size, self.radius)

    def _recompute(self) -> None:
        self._apply()
        # The fillet alone; features after it catch up on OK.
        self.obj.Proxy.editing = True
        started = time.perf_counter()
        self.obj.recompute()
        took_ms = int((time.perf_counter() - started) * 1000)
        # The view gets at least as long as the preview took before the
        # next one starts, so a slow part still turns and drags smoothly.
        self._timer.setInterval(max(SETTLE_MS, took_ms))
        if not getattr(self.obj.Proxy, "dragging", False):
            self.limits = dict(getattr(self.obj.Proxy, "limits", {}) or {})
        self._refresh_view()
        self.bridge.refresh()

    def _start_view(self) -> None:
        """Handles and the preview, where there is a 3D view to put them."""
        from . import fillet_gizmo
        view: Any = (Gui.ActiveDocument.ActiveView
                     if Gui.ActiveDocument else None)
        if view is None or not hasattr(view, "getSceneGraph"):
            return
        frame = App.Placement()
        body = blend_fillet._body_of(self.obj)
        if body is not None:
            frame = body.getGlobalPlacement()
        self._view = view
        try:
            self._handles = fillet_gizmo.Handles(
                view, lambda r: self.set_radius(r, dragged=True),
                self._place_box, self.kind.flat)
            self._handles.set_frame(frame)
        except Exception as exc:  # noqa: BLE001 - the panel works without
            App.Console.PrintWarning("%s: no handles: %s\n"
                                     % (self.kind.title, exc))
            self._handles = None
        self._show_preview(self.preview_on)

    def _refresh_view(self) -> None:
        if self.base is None:
            return
        names = blend_fillet.expanded(self.base.Shape, self.edge_names())
        if self._handles is not None:
            self._handles.place(self.base.Shape,
                                names[0] if names else None, self.radius)
        self._place_box()

    def _place_box(self) -> None:
        """The floating radius field at the first arrow's tip, if shown."""
        tip = self._handles.tip() if self._handles is not None else None
        if tip is None or self._view is None or not self.edge_names():
            self._box.hide()
            return
        self._box.place(self._view, tip)

    def _stop_view(self) -> None:
        self._box.remove()
        if self._handles is not None:
            self._handles.remove()
        self._handles = None
        self._show_preview(False)

    def _finish(self) -> None:
        app: Any = QtWidgets.QApplication.instance()
        app.removeEventFilter(self._release)
        self._stop_view()
        with contextlib.suppress(Exception):
            Gui.Selection.removeObserver(self)
        self.preselect("")

    def _show_base(self, editing: bool) -> None:
        """The result shows throughout; picks on it map to the base."""
        if self.base is not None and self.base.ViewObject is not None:
            self.base.ViewObject.Visibility = False
        if self.obj.ViewObject is not None:
            self.obj.ViewObject.Visibility = True
            self.obj.ViewObject.Selectable = True

    def _fit_height(self) -> None:
        try:
            root = self.form.rootObject()
        except RuntimeError:    # the panel closed before this ran
            return
        if root is None:
            return
        height = int(root.property("implicitHeight"))
        if height != self.form.minimumHeight():
            self.form.setMinimumHeight(height)


def open_for(obj: Any, created: bool) -> bool:
    """Show the panel for `obj`; False if another task is open."""
    if Gui.Control.activeDialog():
        return False
    Gui.Control.showDialog(FilletTask(obj, created))
    return True


def start(flat: bool = False) -> None:
    """A new fillet, or chamfer, on the picked edges or on none."""
    base, names = _start_base()
    doc = base.Document
    doc.openTransaction(CHAMFER.title if flat else FILLET.title)
    try:
        obj = blend_fillet.new_fillet(base, names,
                                      blend_fillet.DEFAULT_RADIUS, flat)
    except Exception:
        doc.abortTransaction()
        raise
    Gui.Selection.clearSelection()
    if not open_for(obj, created=True):
        doc.commitTransaction()


def _start_base() -> tuple[Any, list[str]]:
    """The picked edges' feature, else the active Body's tip."""
    try:
        return blend_fillet.picked_edges()
    except ValueError:
        if Gui.Selection.getSelectionEx("", 0):
            raise
    view: Any = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
    body: Any = (view.getActiveObject("pdbody") if view is not None
                 else None)
    if body is None or body.Tip is None:
        raise ValueError("Select edges of a Part Design feature, or make "
                         "a Body active")
    return body.Tip, []
