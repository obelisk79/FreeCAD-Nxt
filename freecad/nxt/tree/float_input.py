"""A value field in the 3D view, beside a feature's drag arrow.

FreeCAD 26.3 draws arrows ("gizmos") for Pad, Pocket and the like, to
drag a length in the 3D view; the value itself is only in the task panel.
This floats a small Nxt field next to the arrow while it is showing, so
the length can be read and typed where you are looking.

It holds no value of its own. It mirrors the task panel's field (a
Gui::QuantitySpinBox, `lengthEdit` for a Pad) and sets it, so the panel,
the arrow and the model stay one thing.

Setting it: putting text into the spin box's line edit only changes what
it shows - the value, and the feature's property, stayed as they were
even through OK. So the text is parsed as a FreeCAD quantity ("75",
"2 in", "25 mm * 2") and given to the spin box as its raw value, which
is what its own arrows and wheel do: the task panel hears valueChanged
and sets the property. If the property still does not follow, it is set
directly as well.

Where the arrow is comes from the scene: the visible arrow's container
node (SoLinearDraggerContainer, found with probe.draggers()). Its drawn
geometry is measured - Coin's bounding box action, in world space - and
the eight corners projected to the view, which gives the arrow's
rectangle on screen as it is drawn, mid-drag included. Nothing is read
from the dragger's own fields: its container does not move during a
drag, and which way along its axis the arrow goes could not be read
reliably, which put the box on the wrong side. placement.py decides
where the box goes from that rectangle.

Keyboard: clicking the box gives it the keyboard; double-clicking selects
the whole value, ready to overwrite with a number or an expression. While
it has the keyboard, FreeCAD's single-key shortcuts are held off, so
typing "v" or Escape reaches the field, not a command. Enter or Escape
hand the keyboard back to the 3D view. Tab moves to the next box and
Shift+Tab to the one before, round and round, keeping what was typed and
selecting the next value to type over. The drag's step keys (Shift, Ctrl)
are read from the mouse as it drags, not from whichever widget has the
keyboard, so they work either way.

Several handles: a Pad with two lengths has two arrows, and a taper
adds a rotation handle for each side. Each gets a box of its own, tied
to its own task field. Which handle drags which field is not something
the scene says, so it is taken from the order FreeCAD makes them in
(HANDLES): the first arrow is the first length, the second the second.
A handle is given a box only while both it and its task field are
showing. When that pairing finds nothing - another feature type, or a
scene laid out some other way - the one visible arrow gets the one
box, as before.

Polled rather than signalled: FreeCAD announces neither the start of an
edit nor a gizmo appearing. Slow (4 Hz) while nothing is being edited,
30 Hz while an arrow is up.
"""

from __future__ import annotations

import time
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from .. import qtquick, resources
from ..i18n import translate
from ..qt import QtCore, QtGui, QtWidgets
from . import placement, settings

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

IDLE_MS = 250
ACTIVE_MS = 33


def _task_field(type_id: str) -> Any:
    """The visible task panel field the arrow drags, or None."""
    main = Gui.getMainWindow()
    wanted = FIELDS.get(type_id)
    fallback = None
    for widget in main.findChildren(QtWidgets.QAbstractSpinBox):
        if not widget.isVisible():
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
        if widget.isVisible() and widget.objectName() \
                and "QuantitySpinBox" in widget.metaObject().className():
            found.setdefault(widget.objectName(), widget)
    return found


def _handle_boxes(view: Any, kind: str = LINEAR) -> list[Any]:
    """Each handle of this kind in the scene, in the scene's order.

    A handle that is showing gives its 3D bounding box corners; one that
    is hidden gives None, and keeps its place in the list - the place is
    what says which task field it drags.
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
        except Exception:
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
    """Which handle gets a box for which task field.

    `showing` says, per kind of handle, whether each one in the scene is
    visible; `fields` holds the names of the task fields on screen. The
    answer is (kind, place among its kind, field name) for every handle
    that is showing and whose field is too.
    """
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


def parse_quantity(text: str) -> float | None:
    """`text` as a number in FreeCAD's internal units, or None.

    FreeCAD's own quantity parser: "75", "75 mm", "2 in", "25 mm * 2",
    "30 deg". A bare number is taken in the internal unit (mm, degrees),
    which is what the field shows.
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(App.Units.Quantity(text).Value)
    except Exception:
        try:
            return float(text)
        except ValueError:
            return None


class FocusClaim:
    """The keyboard, claimed for the box when an edit begins.

    Asking once was not enough: the edit's own start-up - the task panel
    focusing its first field, the double-click's last release landing in
    the 3D view - could take the keyboard straight back, and the box was
    left without it now and then. So the claim is repeated until the box
    has the keyboard, for a short while at most. Once it has had it, the
    claim is over: a click elsewhere then takes the keyboard for good.
    """

    #: How long to keep asking, in seconds.
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


def _task_ok_button() -> Any:
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


def _alive(obj: Any) -> bool:
    """Whether a Qt object still exists on the C++ side."""
    if obj is None:
        return False
    try:
        import shiboken6
        return bool(shiboken6.isValid(obj))
    except ImportError:
        return True


def _viewport(view: Any) -> Any:
    """The widget the active document's 3D view draws into, or None.

    The active one only: the MDI area's active window. The first visible
    3D view was used before, and with two documents open that could be
    the other document's - the box then lived in the wrong view, and
    giving it the keyboard activated that view, switching the document
    under the edit and back again on every claim.
    """
    main = Gui.getMainWindow()
    area = main.findChild(QtWidgets.QMdiArea)
    sub = area.activeSubWindow() if area is not None else None
    holder = sub.widget() if sub is not None else None
    if holder is None \
            or holder.metaObject().className() != "Gui::View3DInventor":
        return None
    for child in holder.findChildren(QtWidgets.QWidget):
        if "GL" in child.metaObject().className() and child.isVisible():
            return child
    return None


class Field(QtCore.QObject):
    """What the QML box sees: the task field's text, and a way to set it."""

    textChanged = QtCore.Signal()
    labelChanged = QtCore.Signal()
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
        self.released = False

    def bind(self, spin: Any, label: str, obj: Any = None) -> None:
        self._spin = spin
        self._obj = obj
        self._closing = False
        if label != self._label:
            self._label = label
            self.labelChanged.emit()
        self.sync()

    def _live_spin(self) -> Any:
        """The task field, or None once the task has closed and deleted it.

        Enter presses OK, which closes the task and deletes its widgets;
        the box losing the keyboard afterwards must find nothing to set,
        not a deleted widget.
        """
        spin = self._spin
        if spin is None:
            return None
        try:
            import shiboken6
            if not shiboken6.isValid(spin):
                self._spin = None
                return None
        except ImportError:
            pass
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

    def _type(self, text: str) -> bool:
        """Set the task field, and through it the feature, from `text`.

        False when the text is not a quantity FreeCAD can read.
        """
        spin = self._live_spin()
        if spin is None or self._closing:
            return False
        value = parse_quantity(text)
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
        """Enter: keep the value and close the edit, as OK does.

        Nothing is set after this: the task is closing, and the box losing
        the keyboard as it goes is not a new value.
        """
        self._type(text)
        self.sync()
        self._closing = True
        self.finished.emit()

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
    """The box Tab moves to from `name`: the next one shown, wrapping.

    With one box, or a box no longer shown, that is the box itself or
    the first: Tab never leaves the boxes for the 3D view.
    """
    if not order:
        return name
    if name not in order:
        return order[0]
    step = -1 if backward else 1
    return order[(order.index(name) + step) % len(order)]


class _Box:
    """One floating box: its field, and the widget once it is built."""

    def __init__(self, parent: QtCore.QObject) -> None:
        self.field = Field(parent)
        self.widget: Any = None


class FloatingInput(QtCore.QObject):
    """Shows a box for each handle that is up, and keeps it beside it."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        #: A box per task field name, made as its handle first shows.
        self._boxes: dict[str, _Box] = {}
        #: The boxes showing, in the order Tab goes through them.
        self._order: list[str] = []
        self._viewport: Any = None
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        # The edit the first box last took the keyboard for: it does so
        # once per edit, when the edit begins.
        self._session: tuple[str, str] | None = None
        self._claim = FocusClaim()

    def install(self) -> None:
        self._timer.start(IDLE_MS)

    def remove(self) -> None:
        self._timer.stop()
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
            # Queued: the OK button closes the task dialog, which must
            # not happen from inside the key event that asked for it.
            field.finished.connect(
                self._finish_edit,
                QtCore.Qt.ConnectionType.QueuedConnection)
        return box

    def _tab_from(self, name: str, backward: bool) -> None:
        target = self._boxes.get(next_box(self._order, name, backward))
        if target is not None:
            target.field.focusRequested.emit(True)

    def _drop_widgets(self) -> None:
        for box in self._boxes.values():
            if _alive(box.widget):
                box.widget.hide()
                box.widget.deleteLater()
            box.widget = None
        self._viewport = None

    # ------------------------------------------------------------------

    def _tick(self) -> None:
        # Nothing here may raise out of the timer: an error each tick is
        # an error four to thirty times a second in the Report view.
        try:
            for box in self._boxes.values():
                if not _alive(box.widget):
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
        # Nothing paired: the one visible arrow and the one field.
        corners = _arrow_box(view)
        spin = _task_field(type_id) if corners is not None else None
        if spin is None:
            return []
        return [(spin.objectName() or "value", spin, corners)]

    def _update(self) -> bool:
        if not settings.get("FloatingValues"):
            return False
        gui_doc = Gui.ActiveDocument
        edit = gui_doc.getInEdit() if gui_doc is not None else None
        obj = getattr(edit, "Object", None)
        if obj is None:
            self._session = None        # the edit is over
            self._claim.stop()
            return False
        view = gui_doc.ActiveView
        targets = self._targets(view, str(obj.TypeId))
        if not targets:
            return False
        viewport = _viewport(view)
        if viewport is None:
            return False
        if self._viewport is not viewport:
            self._drop_widgets()
            self._viewport = viewport
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
            if id(box) not in live and _alive(box.widget) \
                    and box.widget.isVisible():
                box.widget.hide()
        first, first_widget = placed[0][0], placed[0][1]
        session = (gui_doc.Document.Name, obj.Name)
        if session != self._session:
            # A new edit: the first value is ready to type over, until a
            # click elsewhere takes the keyboard away.
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
        """A 3D point in the viewport widget's coordinates.

        See placement.from_viewport: FreeCAD's answer is bottom-up.
        """
        x, y = view.getPointOnViewport(point)
        ratio = viewport.devicePixelRatioF() or 1.0
        return placement.from_viewport(x, y, viewport.height() * ratio,
                                       ratio)

    def _ensure_widget(self, box: _Box, viewport: Any) -> Any:
        if _alive(box.widget):
            return box.widget
        box.widget = None
        qtquick.use_shared_graphics_api()
        _QtQml, _QtQuick, QtQuickWidgets = qtquick.modules()  # noqa: N806
        widget = QtQuickWidgets.QQuickWidget(viewport)
        widget.setResizeMode(
            QtQuickWidgets.QQuickWidget.ResizeMode.SizeViewToRootObject)
        widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop)
        widget.setFocusPolicy(QtCore.Qt.FocusPolicy.ClickFocus)
        widget.installEventFilter(self)
        widget.setClearColor(QtGui.QColor(0, 0, 0, 0))
        context = widget.rootContext()
        context.setContextProperty("field", box.field)
        context.setContextProperty("theme", self._theme())
        widget.setSource(QtCore.QUrl.fromLocalFile(
            str(resources.qml("FloatingValue.qml"))))
        if widget.status() == QtQuickWidgets.QQuickWidget.Status.Error:
            detail = "; ".join(str(e.toString()) for e in widget.errors())
            App.Console.PrintError("Nxt: floating value failed: %s\n"
                                   % detail)
            widget.deleteLater()
            return None
        box.widget = widget
        return widget

    def _theme(self) -> Any:
        from .. import services
        theme = services.theme()
        if theme is None:
            from .theme import Theme
            theme = Theme(self)
        return theme

    @staticmethod
    def _recompute() -> None:
        """Recompute the feature being edited, so the model shows the value.

        The task panel updates the feature's property as its field
        changes, but leaves the recompute to its "Update view" setting and
        to OK; a value typed in the 3D view is meant to be seen there.
        """
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
        ok = _task_ok_button()
        if ok is not None:
            ok.click()
            return
        gui_doc = Gui.ActiveDocument
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
            gui_doc.Document.recompute()
            try:
                App.closeActiveTransaction(False)   # keep it, as OK does
            except Exception:
                pass

    def _take_keyboard(self, name: str) -> None:
        box = self._boxes.get(name)
        widget: Any = box.widget if box is not None else None
        if _alive(widget) and widget.isVisible():
            widget.activateWindow()
            widget.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        """Hold FreeCAD's shortcuts off while a box has the keyboard.

        A shortcut is offered to the focused widget first, as a
        ShortcutOverride; accepting it keeps the key for the widget. Only
        the boxes' own widgets are watched, and only while one has focus.
        """
        kind = event.type()
        if kind not in (QtCore.QEvent.Type.ShortcutOverride,
                        QtCore.QEvent.Type.KeyPress):
            return False
        if not any(watched is box.widget for box in self._boxes.values()):
            return False
        if kind == QtCore.QEvent.Type.ShortcutOverride:
            if watched.hasFocus():
                event.accept()
            return False
        # Tab: a widget hands it to Qt's focus chain before its content
        # sees it, which took the keyboard out of the boxes altogether.
        # Taken here instead and given to the box, which keeps what was
        # typed and passes the keyboard to the next box.
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

    @staticmethod
    def _send_tab(widget: Any, backward: bool) -> None:
        root = widget.rootObject() if hasattr(widget, "rootObject") else None
        if root is not None:
            QtCore.QMetaObject.invokeMethod(
                root, "tab", QtCore.Qt.ConnectionType.DirectConnection,
                QtCore.Q_ARG("QVariant", backward))

    def _hide(self) -> None:
        for box in self._boxes.values():
            if _alive(box.widget) and box.widget.isVisible():
                box.widget.hide()
