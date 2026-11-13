"""Experimental: Nxt's task panel while a sketch is edited.

Off unless the SketchPanel setting is on. FreeCAD's dialog stays, with
its OK, Cancel and tool parameters. Its solver message goes to a pill at
the top of the 3D view (SketchPill.qml), which also holds the grid, snap
and render order settings; its constraint and element lists are hidden
until asked for. In their place (SketchPanel.qml) the panel shows only
what needs attention: the solver's findings with their fixes, or the one
element or constraint that is selected, with chips that select what it
is tied to.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core import log, settings, widgets
from ..core.qt import QtCore, QtWidgets
from ..core.transaction import transaction
from ..core.view3d import active_viewport
from ..ui.view_notice import TopNotice
from . import sketch_state
from .sketch_contents_model import ContentsModel
from .task_layout import RENEW_MS, TaskLayout, fitted_view, tab_in_order

SETTING = "SketchPanel"
SKETCH = "Sketcher::SketchObject"
#: Set on a box of FreeCAD's that the panel hid, and so may show again.
HIDDEN = "nxtSketchPanelHid"

#: FreeCAD's boxes in the sketch dialog -> the list each one is, if the
#: panel offers to show it; the solver message is never shown.
STOCK: dict[str, str] = {"TaskSketcherMessages": "",
                         "TaskSketcherConstraints": "constraints",
                         "TaskSketcherElements": "elements"}
#: The box the panel's cards take the place of.
LEAD = "TaskSketcherMessages"

_SKETCHER = "User parameter:BaseApp/Preferences/Mod/Sketcher"
_SNAP = _SKETCHER + "/Snap"
#: Switches FreeCAD keeps in parameters: key -> (group, name, default).
PARAMS: dict[str, tuple[str, str, bool]] = {
    "snap": (_SNAP, "Snap", True),
    "snapToGrid": (_SNAP, "SnapToGrid", False),
    "snapToObjects": (_SNAP, "SnapToObjects", True),
}
#: Switches that are properties of the sketch's view provider.
VIEW_PROPS: dict[str, str] = {"grid": "ShowGrid", "gridAuto": "GridAuto",
                              "autoConstraints": "Autoconstraints"}
SNAP_ANGLE = (_SNAP, "SnapAngle", 5.0)
#: Which geometry is drawn, and picked, on top: parameters, top first.
#: Each holds 1 (normal), 2 (construction) or 3 (external).
ORDER_GROUP = _SKETCHER + "/General"
ORDER = ("TopRenderGeometryId", "MidRenderGeometryId",
         "LowRenderGeometryId")

#: FreeCAD's command that selects what a status link is about.
SELECTS: dict[str, str] = {
    sketch_state.FREE: "Sketcher_SelectElementsWithDoFs",
    "ConflictingConstraints": "Sketcher_SelectConflictingConstraints",
    "MalformedConstraints": "Sketcher_SelectMalformedConstraints",
    "RedundantConstraints": "Sketcher_SelectRedundantConstraints",
    "PartiallyRedundantConstraints":
        "Sketcher_SelectPartiallyRedundantConstraints",
}

#: Sketcher's own "Auto-update" switch: recompute after every edit.
AUTO_RECOMPUTE = (_SKETCHER, "AutoRecompute", False)


def _short(widget: Any) -> str:
    return str(widget.metaObject().className()).rsplit("::", 1)[-1]


def edited_sketch() -> Any:
    """The sketch open for editing in the active document, or None."""
    try:
        gui_doc = Gui.ActiveDocument
        editing = gui_doc.getInEdit() if gui_doc is not None else None
        sketch = getattr(editing, "Object", None)
        if sketch is not None and sketch.isDerivedFrom(SKETCH):
            return sketch
    except Exception:  # noqa: BLE001 - a document on its way out
        return None
    return None


def settle(sketch: Any) -> None:
    """Redraw the sketch after an edit, as Sketcher's own commands do.

    Its commands are redrawn as they clear the selection; the panel
    keeps the selection, so the sketch is solved (or, with Auto-update,
    recomputed) instead.
    """
    group, name, default = AUTO_RECOMPUTE
    if App.ParamGet(group).GetBool(name, default):
        sketch.Document.recompute()
    else:
        sketch.solve()


def run_command(name: str) -> None:
    """Run a Sketcher command as its menu would.

    Sketcher's commands are inactive while the sketch is in some other
    mode (dragging, a tool open). FreeCAD then does nothing and says
    nothing, so this says so in the Report view.
    """
    command = Gui.Command.get(name)
    if command is None or not command.isActive():
        App.Console.PrintMessage("Nxt: %s is not available now\n" % name)
        return
    Gui.runCommand(name)


def _vertex_geo(sketch: Any, names: list[str]) -> dict[str, int]:
    """Each selected point's element, by its selection name."""
    found: dict[str, int] = {}
    for name in names:
        number = name[len("Vertex"):]
        if name.startswith("Vertex") and number.isdigit():
            with contextlib.suppress(Exception):  # gone since selected
                found[name] = int(sketch.getGeoVertexIndex(
                    int(number) - 1)[0])
    return found


def selected_names(sketch: Any) -> list[str]:
    """What is selected in `sketch`, as Sketcher names it ("Edge3")."""
    names: list[str] = []
    inside = sketch.Name + "."
    for picked in Gui.Selection.getSelectionEx():
        # Inside a Body the selection may be filed under the Body.
        own = getattr(picked, "ObjectName", "") == sketch.Name
        names.extend(name.rsplit(".", 1)[-1]
                     for name in picked.SubElementNames
                     if own or inside in name)
    return names


def _switches(view: Any) -> dict[str, Any]:
    """Each setting the pill offers that this build has."""
    values: dict[str, Any] = {
        key: bool(getattr(view, prop))
        for key, prop in VIEW_PROPS.items() if hasattr(view, prop)}
    values.update({key: bool(App.ParamGet(group).GetBool(name, default))
                   for key, (group, name, default) in PARAMS.items()})
    spacing = getattr(view, "GridSize", None)
    if spacing is not None:
        values["spacing"] = str(getattr(spacing, "UserString", spacing))
    group, name, default = SNAP_ANGLE
    values["snapAngle"] = "%g" % App.ParamGet(group).GetFloat(name, default)
    order = App.ParamGet(ORDER_GROUP)
    values["order"] = [int(order.GetInt(name, place + 1))
                       for place, name in enumerate(ORDER)]
    return values


class SketchBridge(QtCore.QObject):
    """What SketchPanel.qml and SketchPill.qml show and do."""

    changed = QtCore.Signal()
    #: A stock list was asked for, or sent away.
    browsed = QtCore.Signal()

    _IDLE: tuple[Any, ...] = (False, {}, [], {"kind": ""}, {}, {})

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._state = self._IDLE
        self._shown: set[str] = set()
        self._jobs: list[tuple[str, Callable[[Any], None]]] = []
        # Never inside a QML handler: FreeCAD may spin the event loop
        # while it solves, and a row must not be rebuilt under its click.
        self._work = self._deferral(self._run)
        self._later = self._deferral(self.refresh)
        self._contents = ContentsModel(edited_sketch, self)

    def _deferral(self, slot: Any) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(0)
        timer.timeout.connect(slot)
        return timer

    def stop(self) -> None:
        self._work.stop()
        self._later.stop()
        self._jobs.clear()

    def touch(self, *_args: Any) -> None:
        """Something the panel shows may have changed."""
        self._later.start()

    def edited(self, *_args: Any) -> None:
        """The sketch itself changed: its contents are read again too."""
        self._contents.stale()
        self._later.start()

    def refresh(self) -> None:
        """Read the edited sketch afresh; tell QML only of a change."""
        state = self._IDLE
        sketch = edited_sketch() if settings.get(SETTING) else None
        if sketch is None:
            self._contents.clear()
        else:
            try:
                names = selected_names(sketch)
                self._contents.reselect(names, _vertex_geo(sketch, names))
                state = (True, sketch_state.status(sketch),
                         sketch_state.issues(sketch),
                         sketch_state.selection(sketch, names),
                         _switches(sketch.ViewObject),
                         {"constraints": int(sketch.ConstraintCount),
                          "elements": int(sketch.GeometryCount)})
            except Exception:  # noqa: BLE001 - called from a Qt timer
                log.error("could not read the sketch for its task panel")
        if state != self._state:
            self._state = state
            self.changed.emit()

    # -- what QML shows -- #

    @QtCore.Property(bool, notify=changed)
    def active(self) -> bool:
        return bool(self._state[0])

    # PySide spells QVariantMap as a string; its stubs expect a type.
    @QtCore.Property("QVariantMap", notify=changed)  # type: ignore[arg-type]
    def status(self) -> dict[str, Any]:
        return dict(self._state[1])

    @QtCore.Property(list, notify=changed)
    def issues(self) -> list[dict[str, Any]]:
        return list(self._state[2])

    @QtCore.Property("QVariantMap", notify=changed)  # type: ignore[arg-type]
    def selection(self) -> dict[str, Any]:
        return dict(self._state[3])

    @QtCore.Property("QVariantMap", notify=changed)  # type: ignore[arg-type]
    def switches(self) -> dict[str, Any]:
        return dict(self._state[4])

    @QtCore.Property(QtCore.QObject, constant=True)
    def contents(self) -> ContentsModel:
        return self._contents

    @QtCore.Property("QVariantMap", notify=changed)  # type: ignore[arg-type]
    def counts(self) -> dict[str, Any]:
        return dict(self._state[5])

    @QtCore.Property(list, notify=browsed)
    def browsing(self) -> list[str]:
        return sorted(self._shown)

    def shows(self, stock_list: str) -> bool:
        return stock_list in self._shown

    # -- what QML does -- #

    def _queue(self, name: str, change: Callable[[Any], None]) -> None:
        self._jobs.append((name, change))
        self._work.start()

    def _run(self) -> None:
        jobs, self._jobs = self._jobs, []
        sketch = edited_sketch()
        for name, change in jobs:
            if sketch is None:
                break
            try:
                change(sketch)
            except Exception:  # noqa: BLE001 - called from a Qt timer
                log.error("sketch task panel: could not %s" % name)
        self._later.start()

    def _edit(self, name: str, change: Callable[[Any], None]) -> None:
        """One undo step, named as FreeCAD's undo list shows it."""
        def in_one_step(sketch: Any) -> None:
            with transaction(sketch.Document, name):
                change(sketch)
            settle(sketch)
        self._queue(name, in_one_step)

    @QtCore.Slot(str, bool)
    def browse(self, stock_list: str, on: bool) -> None:
        if on == (stock_list in self._shown):
            return
        (self._shown.add if on else self._shown.discard)(stock_list)
        self.browsed.emit()

    @QtCore.Slot(str)
    def select(self, action: str) -> None:
        """Select what a status link names, as FreeCAD's own link does."""
        command = SELECTS.get(action)
        if command:
            self._queue("select", lambda _sketch: run_command(command))

    @QtCore.Slot(str)
    def pick(self, name: str) -> None:
        """Select one element or constraint of the sketch ("Edge3")."""
        def only(sketch: Any) -> None:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(sketch.Document.Name, sketch.Name,
                                       name)
        self._queue("select", only)

    @QtCore.Slot(str, bool)
    def toggle(self, name: str, on: bool) -> None:
        """Add one element or constraint to the selection, or take it out."""
        def one(sketch: Any) -> None:
            change = Gui.Selection.addSelection if on \
                else Gui.Selection.removeSelection
            change(sketch.Document.Name, sketch.Name, name)
        self._queue("select", one)

    @QtCore.Slot()
    def selectConstraints(self) -> None:  # noqa: N802
        """The constraints on the selected elements, as FreeCAD selects."""
        self._queue("select", lambda _sketch: run_command(
            "Sketcher_SelectConstraints"))

    @QtCore.Slot()
    def deleteSelected(self) -> None:  # noqa: N802
        self._queue("delete", lambda _sketch: run_command("Std_Delete"))

    @QtCore.Slot()
    def constructSelected(self) -> None:  # noqa: N802
        """Selected elements to construction, or all back if all were."""
        def construct(sketch: Any) -> None:
            names = selected_names(sketch)
            geos = sorted(set(_vertex_geo(sketch, names).values()) | {
                int(n[4:]) - 1 for n in names
                if n.startswith("Edge") and n[4:].isdigit()})
            if not geos:
                return
            on = not all(sketch.getConstruction(geo) for geo in geos)
            for geo in geos:
                sketch.setConstruction(geo, on)
        self._edit("Toggle construction geometry", construct)

    @QtCore.Slot(int, str)
    def setValue(self, index: int, text: str) -> None:  # noqa: N802
        """A dimension's value, as typed with its unit."""
        def datum(sketch: Any) -> None:
            sketch.setDatum(index, App.Units.Quantity(text))
        self._edit("Modify sketch constraints", datum)

    @QtCore.Slot()
    def validate(self) -> None:
        self._queue("validate", lambda _sketch: run_command(
            "Sketcher_ValidateSketch"))

    @QtCore.Slot(int)
    def remove(self, index: int) -> None:
        self._edit("Delete constraint",
                   lambda sketch: sketch.delConstraint(index))

    @QtCore.Slot(int, bool)
    def setActive(self, index: int, on: bool) -> None:  # noqa: N802
        self._edit("Activate constraint" if on else "Deactivate constraint",
                   lambda sketch: sketch.setActive(index, on))

    @QtCore.Slot(int, bool)
    def setDriving(self, index: int, on: bool) -> None:  # noqa: N802
        self._edit("Toggle driving constraint",
                   lambda sketch: sketch.setDriving(index, on))

    @QtCore.Slot(int, str)
    def rename(self, index: int, name: str) -> None:
        self._edit("Rename constraint",
                   lambda sketch: sketch.renameConstraint(index,
                                                          name.strip()))

    @QtCore.Slot(int, bool)
    def setConstruction(self, geo: int, on: bool) -> None:  # noqa: N802
        self._edit("Toggle construction geometry",
                   lambda sketch: sketch.setConstruction(geo, on))

    @QtCore.Slot(str, bool)
    def turn(self, key: str, on: bool) -> None:
        """Turn one of the pill's switches, where FreeCAD keeps it."""
        def switch(sketch: Any) -> None:
            if key in VIEW_PROPS:
                setattr(sketch.ViewObject, VIEW_PROPS[key], on)
            elif key in PARAMS:
                group, name, _default = PARAMS[key]
                App.ParamGet(group).SetBool(name, on)
        self._queue("change a sketch setting", switch)

    @QtCore.Slot(str)
    def setSpacing(self, text: str) -> None:  # noqa: N802
        def space(sketch: Any) -> None:
            sketch.ViewObject.GridSize = App.Units.Quantity(text)
        self._queue("set the grid spacing", space)

    @QtCore.Slot(str)
    def setSnapAngle(self, text: str) -> None:  # noqa: N802
        def snap(_sketch: Any) -> None:
            group, name, _default = SNAP_ANGLE
            App.ParamGet(group).SetFloat(
                name, float(text.replace(",", ".").rstrip("° ")))
        self._queue("set the snap angle", snap)

    @QtCore.Slot(int)
    def drawAbove(self, place: int) -> None:  # noqa: N802
        """Swap the geometry at `place` in the order with the one above."""
        def swap(_sketch: Any) -> None:
            if not 0 < place < len(ORDER):
                return
            order = App.ParamGet(ORDER_GROUP)
            ids = [int(order.GetInt(name, at + 1))
                   for at, name in enumerate(ORDER)]
            ids[place - 1], ids[place] = ids[place], ids[place - 1]
            for name, value in zip(ORDER, ids):
                order.SetInt(name, value)
        self._queue("change the render order", swap)


class Pill(TopNotice):
    """Keeps the status pill at the top centre of the sketch's 3D view.

    Under the isolate notice, if there is one; the undo toast goes under
    the pill, so `placed` says when the pill has moved, grown or gone.
    """

    SOURCE = "SketchPill.qml"

    placed = QtCore.Signal()

    def __init__(self, bridge: SketchBridge, theme: Any,
                 above: Callable[[], TopNotice | None],
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(theme, parent)
        self._bridge = bridge
        self._above = above

    def sync(self) -> None:
        self._sync()

    def _context(self) -> dict[str, Any]:
        return {"sketch": self._bridge}

    def _wanted_host(self) -> Any:
        return active_viewport() if self._bridge.active else None

    def _top(self) -> int:
        above = self._above()
        return super()._top() + (above.bottom() if above is not None else 0)

    def _place(self) -> None:
        super()._place()
        self.placed.emit()

    def _ensure(self, host: Any) -> Any:
        fresh = self._widget is None or self._host is not host
        widget = super()._ensure(host)
        if widget is not None and fresh:
            widget.nxt_away = _ClickAway(widget)  # type: ignore[attr-defined]
        return widget

    def _drop(self) -> None:
        super()._drop()
        self.placed.emit()


class _ClickAway(QtCore.QObject):
    """Closes the pill's settings on a press anywhere else, or Escape.

    Watches the whole application only while the settings are open. The
    press goes on to whatever it was on; Escape is kept, or Sketcher
    would also take it and leave the sketch.
    """

    def __init__(self, view: Any) -> None:
        super().__init__(view)
        self._view = view
        self._root = view.rootObject()
        self._watching = False
        if self._root is not None:
            self._root.openChanged.connect(self._follow)

    def _follow(self) -> None:
        on = bool(self._root.property("open"))
        if on == self._watching:
            return
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        (app.installEventFilter if on else app.removeEventFilter)(self)
        self._watching = on

    def _close(self) -> None:
        with contextlib.suppress(RuntimeError):  # the view went first
            self._root.setProperty("open", False)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QtCore.QEvent.Type.KeyPress \
                and event.key() == QtCore.Qt.Key.Key_Escape:
            self._close()
            return True
        # A window passes its presses on to a widget: judge them there.
        if kind == QtCore.QEvent.Type.MouseButtonPress \
                and isinstance(watched, QtWidgets.QWidget) \
                and watched is not self._view \
                and not self._view.isAncestorOf(watched):
            self._close()
        return False


class _Selection:
    def __init__(self, touch: Callable[..., None]) -> None:
        self.addSelection = self.removeSelection = touch
        self.setSelection = self.clearSelection = touch


class _Documents:
    """The App observer: a Gui one must not have slotChangedObject."""

    def __init__(self, touch: Callable[..., None]) -> None:
        self._touch = touch

    def slotChangedObject(self, obj: Any, prop: str) -> None:  # noqa: N802
        if prop in ("Constraints", "Geometry", "ExternalGeo"):
            self._touch()

    def slotRecomputedObject(self, _obj: Any) -> None:  # noqa: N802
        self._touch()


class _Edits:
    def __init__(self, touch: Callable[..., None]) -> None:
        self.slotInEdit = self.slotResetEdit = touch


class SketchPanel(TaskLayout):
    """Swaps the sketch dialog's boxes and shows the pill, when on."""

    def __init__(self, theme: Any, above: Callable[[], TopNotice | None],
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._bridge = SketchBridge(self)
        #: The status pill, for what is stacked under it.
        self.pill = Pill(self._bridge, theme, above, self)
        self._cards: Any = None
        touch = self._bridge.touch
        self._observers = (
            (Gui.Selection.addObserver, Gui.Selection.removeObserver,
             _Selection(touch)),
            (App.addDocumentObserver, App.removeDocumentObserver,
             _Documents(self._bridge.edited)),
            (Gui.addDocumentObserver, Gui.removeDocumentObserver,
             _Edits(self._bridge.edited)))
        self._watching = False
        self._bridge.changed.connect(self.pill.sync)
        self._bridge.browsed.connect(self._later.start)

    def install(self) -> None:
        self.pill.install()
        self.sync()

    def remove(self) -> None:
        self._watch_sketch(False)
        self._bridge.stop()
        self._restore()
        self.pill.remove()
        super().remove()

    def sync(self) -> None:
        """Follow the setting, also while a sketch is open.

        While it is off nothing is watched: FreeCAD's dialog is its own.
        """
        on = bool(settings.get(SETTING))
        self._watch_sketch(on)
        if on:
            super().install()
            self._swap()
        else:
            self._restore()
            super().remove()
            self._bridge.refresh()

    def _watch_sketch(self, on: bool) -> None:
        if on == self._watching:
            return
        for add, drop, observer in self._observers:
            with contextlib.suppress(Exception):  # already (un)registered
                (add if on else drop)(observer)
        self._watching = on

    def _boxes(self) -> dict[str, Any]:
        if not widgets.alive(self._view):
            return {}
        return {_short(widget): widget
                for widget in self._view.findChildren(QtWidgets.QWidget)
                if _short(widget) in STOCK}

    def _swap(self) -> None:
        """FreeCAD's boxes hidden, the cards in the solver message's place."""
        self._busy = True
        try:
            boxes = self._boxes()
            for short, box in boxes.items():
                self._show(box, self._bridge.shows(STOCK[short]))
            if LEAD not in boxes:
                self._discard()
            elif not widgets.alive(self._cards):
                self._insert(boxes[LEAD])
        except Exception:  # noqa: BLE001 - called from a Qt timer
            log.error("could not lay out the sketch task panel")
        finally:
            self._busy = False
        self._bridge.touch()

    @staticmethod
    def _show(box: Any, wanted: bool) -> None:
        """Hide a box of FreeCAD's, or show one this panel hid."""
        if wanted and box.property(HIDDEN):
            box.setProperty(HIDDEN, False)
            box.show()
        elif not wanted and not box.isHidden():
            box.setProperty(HIDDEN, True)
            box.hide()

    def _insert(self, lead: Any) -> None:
        holder = lead.parentWidget()
        layout = holder.layout() if holder is not None else None
        if not isinstance(layout, QtWidgets.QBoxLayout):
            return
        cards = fitted_view(holder, "SketchPanel.qml",
                            {"sketch": self._bridge})
        layout.insertWidget(layout.indexOf(lead), cards)
        self._cards = cards
        for delay in RENEW_MS:
            QtCore.QTimer.singleShot(delay, cards,
                                     lambda: tab_in_order(cards))
        # The box goes with its dialog; what holds it stays for the next.
        lead.destroyed.connect(self._later.start)

    def _discard(self) -> None:
        cards, self._cards = self._cards, None
        if widgets.alive(cards):
            cards.hide()
            cards.setParent(None)
            cards.deleteLater()

    def _restore(self) -> None:
        """FreeCAD's dialog as it was, for a reload or a removal."""
        for box in self._boxes().values():
            self._show(box, True)
        self._discard()
