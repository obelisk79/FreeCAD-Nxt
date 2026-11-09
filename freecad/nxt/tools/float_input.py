"""A value field in the 3D view, beside a feature's drag arrow.

Mirrors the task panel's QuantitySpinBox for each visible gizmo handle,
so the panel, arrow and model stay in step. Polled (4 Hz idle, 30 Hz
active): FreeCAD signals neither edit start nor gizmo appearance.
"""

from __future__ import annotations

import contextlib
import re
import time
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..app.i18n import translate
from ..core import settings, units, view3d, widgets
from ..core.qt import QtCore, QtWidgets
from ..ui import quick_host
from . import expressions, placement, task_sync

#: The property each task panel field sets, where it is known.
PROPERTIES = {
    "lengthEdit": "Length",
    "lengthEdit2": "Length2",
    "revolveAngle": "Angle",
    "revolveAngle2": "Angle2",
    "taperEdit": "TaperAngle",
    "taperEdit2": "TaperAngle2",
}

#: The scene nodes that hold a handle: an arrow, and a rotation handle.
LINEAR = "SoLinearDraggerContainer"
ROTATION = "SoRotationDraggerContainer"

_EXTRUDE = ((LINEAR, ("lengthEdit", "lengthEdit2")),
            (ROTATION, ("taperEdit", "taperEdit2")))
_REVOLVE = ((ROTATION, ("revolveAngle", "revolveAngle2")),)

#: Per feature type, each kind of handle and the task fields its handles
#: drag, in the order FreeCAD creates them.
HANDLES = {
    "PartDesign::Pad": _EXTRUDE,
    "PartDesign::Pocket": _EXTRUDE,
    "PartDesign::Revolution": _REVOLVE,
    "PartDesign::Groove": _REVOLVE,
}

#: The task panel field a feature's arrow drags, by feature type. Any
#: other type with an arrow falls back to the first length field shown.
FIELDS = {
    "PartDesign::Pad": "lengthEdit",
    "PartDesign::Pocket": "lengthEdit",
    "PartDesign::Revolution": "revolveAngle",
    "PartDesign::Groove": "revolveAngle",
}

#: The number a field's text starts with, and its decimals.
_NUMBER = re.compile(r"\s*-?\d+(?:[.,](\d+))?")

IDLE_MS = 250
ACTIVE_MS = 33


def _task_field(type_id: str) -> Any:
    """The visible task panel field the arrow drags, or None."""
    main = Gui.getMainWindow()
    wanted = FIELDS.get(type_id)
    fallback = None
    for widget in main.findChildren(QtWidgets.QAbstractSpinBox):
        if not task_sync.showing(widget):
            continue
        if "QuantitySpinBox" not in widget.metaObject().className():
            continue
        if wanted and widget.objectName() == wanted:
            return widget
        if fallback is None and "mm" in (widget.text() or ""):
            fallback = widget
    return fallback


def _task_fields() -> dict[str, Any]:
    """Every value field showing in the task panel, by its name."""
    found: dict[str, Any] = {}
    for widget in Gui.getMainWindow().findChildren(
            QtWidgets.QAbstractSpinBox):
        if task_sync.showing(widget) and widget.objectName() \
                and "QuantitySpinBox" in widget.metaObject().className():
            found.setdefault(widget.objectName(), widget)
    return found


def _handle_boxes(view: Any, kind: str = LINEAR) -> list[Any]:
    """Bounding box corners per handle of `kind`, None where hidden.

    Hidden handles keep their slot: the index says which field they drag.
    """
    from pivy import coin
    node_type = coin.SoType.fromName(kind)
    if node_type.isBad():
        return []
    search = coin.SoSearchAction()
    search.setType(node_type)
    search.setInterest(coin.SoSearchAction.ALL)
    search.setSearchingAll(True)
    search.apply(view.getSceneGraph())
    paths = search.getPaths()
    boxes: list[Any] = []
    for i in range(paths.getLength()):
        boxes.append(None)
        node = paths[i].getTail()
        try:
            if not node.visible.getValue():
                continue
        except Exception:  # nosec B112  # a node without visibility
            continue
        action = coin.SoGetBoundingBoxAction(coin.SbViewportRegion())
        action.apply(paths[i])
        box = action.getBoundingBox()
        if box.isEmpty():
            continue
        low, high = box.getMin().getValue(), box.getMax().getValue()
        boxes[-1] = [App.Vector(x, y, z) for x in (low[0], high[0])
                     for y in (low[1], high[1]) for z in (low[2], high[2])]
    return boxes


def _arrow_box(view: Any) -> Any:
    """The first visible arrow's 3D bounding box corners, or None."""
    for corners in _handle_boxes(view):
        if corners is not None:
            return corners
    return None


def pair(type_id: str, showing: dict[str, list[bool]],
         fields: Any) -> list[tuple[str, int, str]]:
    """(kind, index, field name) for each visible handle with its field."""
    pairs: list[tuple[str, int, str]] = []
    for kind, names in HANDLES.get(type_id, ()):
        for place, shown in enumerate(showing.get(kind, ())):
            if shown and place < len(names) and names[place] in fields:
                pairs.append((kind, place, names[place]))
    return pairs


def label_for(name: str) -> str:
    """What a box says it is, from its task field's name."""
    lower = name.lower()
    second = lower.endswith("2")
    if "taper" in lower:
        return translate("Nxt", "Taper 2") if second \
            else translate("Nxt", "Taper")
    if "angle" in lower:
        return translate("Nxt", "Angle 2") if second \
            else translate("Nxt", "Angle")
    return translate("Nxt", "Length 2") if second \
        else translate("Nxt", "Length")


#: How long after a release the dragged handle's box takes the keyboard.
DRAG_SETTLE_MS = 60


class FocusClaim:
    """Repeatedly claims the keyboard for the box when an edit begins.

    The task panel's start-up can steal focus back, so the claim repeats
    for WINDOW seconds or until the box has held focus once.
    """

    WINDOW = 1.5

    def __init__(self) -> None:
        self._until = 0.0
        self._held = False

    def start(self, now: float) -> None:
        self._until = now + self.WINDOW
        self._held = False

    def stop(self) -> None:
        self._until = 0.0

    def wanted(self, now: float, has_focus: bool) -> bool:
        """Whether to ask for the keyboard (again) now."""
        if has_focus:
            self._held = True
            self._until = 0.0
            return False
        return not self._held and now < self._until


def task_ok_button() -> Any:
    """The open task dialog's OK button, or None."""
    main = Gui.getMainWindow()
    for box in main.findChildren(QtWidgets.QDialogButtonBox):
        if not box.isVisible():
            continue
        parent = box.parentWidget()
        while parent is not None:
            if "TaskView" in parent.metaObject().className():
                ok = box.button(
                    QtWidgets.QDialogButtonBox.StandardButton.Ok)
                if ok is not None and ok.isVisible() and ok.isEnabled():
                    return ok
                break
            parent = parent.parentWidget()
    return None


class Field(QtCore.QObject):
    """What the QML box sees: the task field's text, and a way to set it."""

    textChanged = QtCore.Signal()
    labelChanged = QtCore.Signal()
    ownerChanged = QtCore.Signal()
    #: The QML box wants the keyboard (it was clicked).
    grabbed = QtCore.Signal()
    #: Give the box the keyboard; True also selects the whole value.
    focusRequested = QtCore.Signal(bool)
    #: A value was committed: recompute the feature being edited.
    committed = QtCore.Signal()
    #: Enter was pressed: commit and finish the edit, as the task's OK.
    finished = QtCore.Signal()
    #: Tab was pressed: on to the next box, or (True) back to the last.
    tabbed = QtCore.Signal(bool)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._spin: Any = None
        self._obj: Any = None
        self._closing = False
        self._text = ""
        self._label = ""
        self._owner = ""
        self.released = False

    def bind(self, spin: Any, label: str, obj: Any = None) -> None:
        self._spin = spin
        self._obj = obj
        self._closing = False
        doc = getattr(getattr(obj, "Document", None), "Name", "")
        name = getattr(obj, "Name", "")
        owner = "%s#%s" % (doc, name) if doc and name else name
        if owner != self._owner:
            self._owner = owner
            self.ownerChanged.emit()
        if label != self._label:
            self._label = label
            self.labelChanged.emit()
        self.sync()

    def _live_spin(self) -> Any:
        """The task field, or None once the task has deleted it."""
        spin = self._spin
        if spin is None:
            return None
        with contextlib.suppress(ImportError):
            import shiboken6
            if not shiboken6.isValid(spin):
                self._spin = None
                return None
        return spin

    def sync(self) -> None:
        spin = self._live_spin()
        try:
            text = spin.text() if spin is not None else self._text
        except RuntimeError:
            self._spin, text = None, self._text
        if text != self._text:
            self._text = text
            self.textChanged.emit()

    @QtCore.Property(str, notify=textChanged)
    def text(self) -> str:
        return self._text

    @QtCore.Property(str, notify=labelChanged)
    def label(self) -> str:
        return self._label

    @QtCore.Property(str, notify=ownerChanged)
    def owner(self) -> str:
        """The feature being edited, for expressions: "Document#Name"."""
        return self._owner

    def _type(self, text: str) -> bool:
        """Set the task field (and feature) from `text`; False if invalid.

        Setting the line edit text alone does not change the value, so the
        parsed quantity goes in as rawValue, as the spin box's arrows do.
        """
        spin = self._live_spin()
        if spin is None or self._closing:
            return False
        if text.strip().startswith("="):
            return self._bind_expression(spin, text)
        value = units.internal_value(text)
        if value is None:
            App.Console.PrintWarning(
                "Nxt: %r is not a value FreeCAD can read\n" % text)
            return False
        try:
            spin.setProperty("rawValue", value)
            self._set_property(spin.objectName(), value)
        except RuntimeError:            # deleted under us after all
            self._spin = None
            return False
        return True

    def _bind_expression(self, spin: Any, text: str) -> bool:
        """Bind an "=..." expression on the feature and mirror its value."""
        from . import expressions
        prop = PROPERTIES.get(spin.objectName())
        obj = self._obj
        expression = expressions.strip_marker(text)
        if obj is None or prop is None or not expression:
            return False
        try:
            obj.setExpression(prop, expression)
            value = obj.evalExpression(expression)
            spin.setProperty("rawValue",
                             float(getattr(value, "Value", value)))
        except Exception as exc:
            App.Console.PrintWarning("Nxt: could not bind %s to %r: %s\n"
                                     % (prop, expression, exc))
            return False
        return True

    def _set_property(self, field_name: str, value: float) -> None:
        """Make sure the feature has the value, if the panel did not."""
        prop = PROPERTIES.get(field_name)
        obj = self._obj
        if obj is None or prop is None or not hasattr(obj, prop):
            return
        current = getattr(obj, prop)
        number = getattr(current, "Value", current)
        try:
            if abs(float(number) - value) > 1e-9:
                setattr(obj, prop, value)
                App.Console.PrintLog("Nxt floating value: set %s.%s = %s\n"
                                     % (obj.Name, prop, value))
        except Exception as exc:
            App.Console.PrintError("Nxt: could not set %s.%s: %s\n"
                                   % (obj.Name, prop, exc))

    @QtCore.Slot(str)
    def preview(self, text: str) -> None:
        """While typing: nothing yet - a half-typed value is not one."""

    @QtCore.Slot(str)
    def commit(self, text: str) -> None:
        """Enter, or the box losing the keyboard, with a changed value."""
        ok = self._type(text)
        self.sync()
        if ok:
            self.committed.emit()

    @QtCore.Slot(str)
    def finish(self, text: str) -> None:
        """Enter: keep the value and close the edit, as OK does."""
        self._type(text)
        self.sync()
        self._closing = True
        self.finished.emit()

    @QtCore.Slot(int, result=str)
    def stepped(self, steps: int) -> str:
        """The value moved by `steps` single steps, formatted as the panel.

        Not set: the box commits once the wheel rests, to avoid a
        recompute per notch.
        """
        spin = self._live_spin()
        if spin is None or self._closing:
            return self._text
        try:
            raw = float(spin.property("rawValue"))
            size = float(spin.property("singleStep") or 1.0)
            value = raw + steps * size
            for name, limit in (("minimum", max), ("maximum", min)):
                bound = spin.property(name)
                if bound is not None:
                    value = limit(value, float(bound))
            shown = spin.text()
        except (RuntimeError, TypeError, ValueError):
            return self._text
        match = _NUMBER.match(shown)
        if match is None:
            return "%g" % value
        decimals = len(match.group(1) or "")
        return "%.*f%s" % (decimals, value, shown[match.end():])

    @QtCore.Slot(bool)
    def tab(self, backward: bool) -> None:
        """Tab or Shift+Tab: the keyboard goes to the next box."""
        self.tabbed.emit(backward)

    @QtCore.Slot()
    def grab(self) -> None:
        """Take the keyboard from the 3D view, for typing a value."""
        self.grabbed.emit()

    @QtCore.Slot()
    def release(self) -> None:
        """Hand the keyboard back to the 3D view."""
        self.released = True


def next_box(order: list[str], name: str, backward: bool = False) -> str:
    """The box Tab moves to from `name`, wrapping; never leaves the boxes."""
    if not order:
        return name
    if name not in order:
        return order[0]
    step = -1 if backward else 1
    return order[(order.index(name) + step) % len(order)]


def moved_box(before: dict[str, str], after: dict[str, str]) -> str | None:
    """The box whose value changed between press and release, if any."""
    for name, text in after.items():
        if name in before and before[name] != text:
            return name
    return None


class _Box:
    """One floating box: its field, and the widget once it is built."""

    def __init__(self, parent: QtCore.QObject) -> None:
        self.field = Field(parent)
        self.widget: Any = None


class FloatingInput(QtCore.QObject):
    """Shows a box for each handle that is up, and keeps it beside it."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._boxes: dict[str, _Box] = {}
        self._order: list[str] = []
        self._viewport: Any = None
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._session: tuple[str, str] | None = None
        self._started: tuple[str, str] | None = None
        self._claim = FocusClaim()
        # Values at a press in the 3D view: a handle dragged changes one.
        self._pressed: dict[str, str] | None = None
        self._drag_end = QtCore.QTimer(self)
        self._drag_end.setSingleShot(True)
        self._drag_end.setInterval(DRAG_SETTLE_MS)
        self._drag_end.timeout.connect(self._focus_dragged)

    def install(self) -> None:
        self._timer.start(IDLE_MS)

    def remove(self) -> None:
        self._timer.stop()
        QtWidgets.QApplication.instance().removeEventFilter(self)
        self._drop_widgets()

    def _box(self, name: str) -> _Box:
        box = self._boxes.get(name)
        if box is None:
            box = self._boxes[name] = _Box(self)
            field = box.field
            field.grabbed.connect(lambda: self._take_keyboard(name))
            field.focusRequested.connect(
                lambda _select: self._take_keyboard(name))
            field.committed.connect(self._recompute)
            field.tabbed.connect(
                lambda backward: self._tab_from(name, backward))
            # Queued: OK must not close the task inside its own key event.
            field.finished.connect(
                self._finish_edit,
                QtCore.Qt.ConnectionType.QueuedConnection)
        return box

    def _tab_from(self, name: str, backward: bool) -> None:
        target = self._boxes.get(next_box(self._order, name, backward))
        if target is not None:
            target.field.focusRequested.emit(True)

    def _drop_widgets(self) -> None:
        if widgets.alive(self._viewport):
            self._viewport.removeEventFilter(self)
        for box in self._boxes.values():
            if widgets.alive(box.widget):
                box.widget.hide()
                box.widget.deleteLater()
            box.widget = None
        self._viewport = None

    def _tick(self) -> None:
        try:
            for box in self._boxes.values():
                if not widgets.alive(box.widget):
                    box.widget = None
            shown = self._update()
        except Exception as exc:
            App.Console.PrintLog("Nxt floating value: %s\n" % exc)
            shown = False
        try:
            if not shown:
                self._hide()
        except Exception:
            for box in self._boxes.values():
                box.widget = None
        self._timer.setInterval(ACTIVE_MS if shown else IDLE_MS)

    def _targets(self, view: Any, type_id: str) -> list[tuple[str, Any, Any]]:
        """(box name, task field, the handle's corners) for each box."""
        fields = _task_fields()
        boxes = {kind: _handle_boxes(view, kind)
                 for kind, _names in HANDLES.get(type_id, ())}
        showing = {kind: [c is not None for c in found]
                   for kind, found in boxes.items()}
        targets = [(name, fields[name], boxes[kind][place])
                   for kind, place, name in pair(type_id, showing, fields)]
        if targets:
            return targets
        corners = _arrow_box(view)
        spin = _task_field(type_id) if corners is not None else None
        if spin is None:
            return []
        return [(spin.objectName() or "value", spin, corners)]

    def _update(self) -> bool:
        gui_doc: Any = Gui.ActiveDocument
        edit = gui_doc.getInEdit() if gui_doc is not None else None
        obj = getattr(edit, "Object", None)
        if obj is None:
            self._session = None
            self._started = None
            self._claim.stop()
            return False
        started = (gui_doc.Document.Name, obj.Name)
        if started != self._started:
            # Retried each tick until the task panel is built.
            if task_sync.start_with_offset(obj) \
                    or not task_sync.wants_offset_start(obj):
                self._started = started
        if not settings.get("FloatingValues"):
            return False
        view = gui_doc.ActiveView
        targets = self._targets(view, str(obj.TypeId))
        if not targets:
            return False
        viewport = view3d.active_viewport()
        if viewport is None:
            return False
        if self._viewport is not viewport:
            self._drop_widgets()
            self._viewport = viewport
            viewport.installEventFilter(self)
            # On the application too, after FreeCAD's overlay manager:
            # it is asked first, and sends a wheel over the 3D view on to
            # the view, which zooms.
            QtWidgets.QApplication.instance().installEventFilter(self)
        placed: list[tuple[_Box, Any, placement.Rect]] = []
        for name, spin, corners in targets:
            box = self._box(name)
            box.field.bind(spin, label_for(name), obj)
            widget = self._ensure_widget(box, viewport)
            arrow = placement.bounding(
                self._to_widget(view, viewport, c) for c in corners)
            if widget is not None and arrow is not None:
                placed.append((box, widget, arrow))
        if not placed:
            return False
        shown = {id(box) for box, _w, _a in placed}
        self._order = [name for name, _s, _c in targets
                       if id(self._boxes[name]) in shown]
        sizes = [w.sizeHint() for _b, w, _a in placed]
        spots = placement.layout(
            [arrow for _b, _w, arrow in placed],
            [(size.width(), size.height()) for size in sizes],
            placement.Rect(0, 0, viewport.width(), viewport.height()))
        live = set()
        for (box, widget, _arrow), size, spot in zip(placed, sizes, spots):
            live.add(id(box))
            widget.resize(size)
            widget.move(round(spot.x), round(spot.y))
            if not widget.isVisible():
                widget.show()
                widget.raise_()
        for box in self._boxes.values():
            if id(box) not in live and widgets.alive(box.widget) \
                    and box.widget.isVisible():
                box.widget.hide()
        first, first_widget = placed[0][0], placed[0][1]
        session = (gui_doc.Document.Name, obj.Name)
        if session != self._session:
            self._session = session
            self._claim.start(time.monotonic())
        has_focus = any(w.hasFocus() for _b, w, _a in placed)
        if self._claim.wanted(time.monotonic(), has_focus) \
                and not first_widget.hasFocus():
            first.field.focusRequested.emit(True)
        for box, _widget, _arrow in placed:
            if box.field.released:
                box.field.released = False
                viewport.setFocus()
        return True

    @staticmethod
    def _to_widget(view: Any, viewport: Any,
                   point: Any) -> tuple[float, float]:
        """A 3D point in widget coordinates (FreeCAD's are bottom-up)."""
        x, y = view.getPointOnViewport(point)
        ratio = viewport.devicePixelRatioF() or 1.0
        return placement.from_viewport(x, y, viewport.height() * ratio,
                                       ratio)

    def _ensure_widget(self, box: _Box, viewport: Any) -> Any:
        if widgets.alive(box.widget):
            return box.widget
        box.widget = None
        try:
            widget = quick_host.make_view(
                viewport, "FloatingValue.qml",
                {"expressions": expressions.helper(), "field": box.field,
                 "theme": self._theme()},
                floating=True, prepare=self._prepare)
        except quick_host.QmlLoadError as exc:
            App.Console.PrintError("Nxt: %s\n" % exc)
            return None
        box.widget = widget
        return widget

    def _prepare(self, widget: Any) -> None:
        widget.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        widget.installEventFilter(self)

    def _theme(self) -> Any:
        from ..app import services
        theme = services.theme()
        if theme is None:
            from ..ui.theme import Theme
            theme = Theme(self)
        return theme

    @staticmethod
    def _recompute() -> None:
        """Recompute the edited feature; the panel defers it to OK."""
        gui_doc = Gui.ActiveDocument
        edit = gui_doc.getInEdit() if gui_doc is not None else None
        obj = getattr(edit, "Object", None)
        if obj is None:
            return
        try:
            obj.touch()
            obj.Document.recompute()
        except Exception as exc:
            App.Console.PrintError("Nxt: recompute failed: %s\n" % exc)

    @staticmethod
    def _finish_edit() -> None:
        """Close the edit as its task's OK button would, or reset it."""
        ok = task_ok_button()
        if ok is not None:
            ok.click()
            return
        gui_doc = Gui.ActiveDocument
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
            gui_doc.Document.recompute()
            with contextlib.suppress(Exception):
                App.closeActiveTransaction(False)   # keep it, as OK does

    def _texts(self) -> dict[str, str]:
        texts = {}
        for name in self._order:
            field = self._boxes[name].field
            field.sync()
            texts[name] = str(field.text)
        return texts

    def _focus_dragged(self) -> None:
        """After a handle is let go, its box takes the keyboard."""
        before, self._pressed = self._pressed, None
        name = moved_box(before or {}, self._texts())
        if name is not None:
            self._boxes[name].field.focusRequested.emit(True)

    def _watch_drag(self, event: Any) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            self._pressed = self._texts()
        elif self._pressed is not None:
            # FreeCAD finishes the drag after the release reaches it.
            self._drag_end.start()

    def _take_keyboard(self, name: str) -> None:
        box = self._boxes.get(name)
        widget: Any = box.widget if box is not None else None
        if widgets.alive(widget) and widget.isVisible():
            widget.activateWindow()
            widget.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        """Take wheels over a box, shortcuts while focused; watch drags."""
        kind = event.type()
        if kind == QtCore.QEvent.Type.Wheel:
            widget = self._box_at(event.globalPosition().toPoint())
            if widget is None:
                return False
            # Taken here, so the 3D view underneath does not zoom.
            self._send_wheel(widget, event.angleDelta().y(), bool(
                event.modifiers()
                & QtCore.Qt.KeyboardModifier.ControlModifier))
            event.accept()
            return True
        if watched is self._viewport:
            if kind in (QtCore.QEvent.Type.MouseButtonPress,
                        QtCore.QEvent.Type.MouseButtonRelease):
                self._watch_drag(event)
            return False
        if kind not in (QtCore.QEvent.Type.ShortcutOverride,
                        QtCore.QEvent.Type.KeyPress):
            return False
        if not any(watched is box.widget for box in self._boxes.values()):
            return False
        if kind == QtCore.QEvent.Type.ShortcutOverride:
            if watched.hasFocus():
                event.accept()
            return False
        # Qt's focus chain eats Tab before QML sees it; route it ourselves.
        key = event.key()
        if key not in (QtCore.Qt.Key.Key_Tab, QtCore.Qt.Key.Key_Backtab) \
                or event.modifiers() & (
                    QtCore.Qt.KeyboardModifier.ControlModifier
                    | QtCore.Qt.KeyboardModifier.AltModifier):
            return False
        backward = key == QtCore.Qt.Key.Key_Backtab or bool(
            event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)
        self._send_tab(watched, backward)
        return True

    def _box_at(self, point: Any) -> Any:
        """The value box shown under the global `point`, if any."""
        for box in self._boxes.values():
            widget = box.widget
            if widgets.alive(widget) and widget.isVisible() \
                    and widget.rect().contains(widget.mapFromGlobal(point)):
                return widget
        return None

    @staticmethod
    def _send_wheel(widget: Any, angle: int, tenfold: bool) -> None:
        root = widget.rootObject() if hasattr(widget, "rootObject") else None
        if root is not None:
            QtCore.QMetaObject.invokeMethod(
                root, "turn", QtCore.Qt.ConnectionType.DirectConnection,
                QtCore.Q_ARG("QVariant", angle),
                QtCore.Q_ARG("QVariant", tenfold))

    @staticmethod
    def _send_tab(widget: Any, backward: bool) -> None:
        root = widget.rootObject() if hasattr(widget, "rootObject") else None
        if root is not None:
            QtCore.QMetaObject.invokeMethod(
                root, "tab", QtCore.Qt.ConnectionType.DirectConnection,
                QtCore.Q_ARG("QVariant", backward))

    def _hide(self) -> None:
        for box in self._boxes.values():
            if widgets.alive(box.widget) and box.widget.isVisible():
                box.widget.hide()
