"""Experimental: Nxt's attachment task panel.

Off unless the AttachPanel setting is on; then Nxt's "Edit attachment"
opens this in place of FreeCAD's attachment editor. AttachTask.qml shows
a card per step: what the object is attached to, the way, the offset.
Picks in the 3D view or the tree fill the next reference. Each change is
written to the object at once, which is the preview, inside one undo
step that OK keeps and Cancel takes back.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..app.i18n import translate
from ..core import log, units
from ..core.qt import QtCore, QtWidgets
from ..ui import quick_host
from . import attach_ways
from .attach_ways import DETACHED, MOST_REFERENCES
from .editing import DATUMS

SETTING = "AttachPanel"
#: Offset fields in panel order: move X Y Z, then turn about X Y Z.
MOVES = 3
ANGLE = "°"
LENGTH = "mm"


def attachable(obj: Any) -> bool:
    return obj is not None and hasattr(obj, "Attacher") \
        and hasattr(obj, "AttachmentSupport")


def reference(doc: Any, name: str, sub: str,
              own: Any) -> tuple[Any, str] | None:
    """A pick as an attachment reference: (object, element) or None.

    A pick inside a Body or Part names its container first; the element
    belongs to the feature under it. Datums are referenced whole.
    """
    top = doc.getObject(name)
    if top is None:
        return None
    target, element = top, ""
    if sub:
        try:
            target, _mapped, element = top.resolveSubElement(sub)
        except Exception:  # noqa: BLE001 - a pick on something gone
            return None
        element = (element or "").lstrip("?")
    if target is None or target is own:
        return None
    if any(target.isDerivedFrom(kind) for kind in DATUMS):
        element = ""
    return target, element


def _quantity(value: float, unit: str) -> str:
    try:
        return str(App.Units.Quantity("%.12g %s" % (value, unit)).UserString)
    except Exception:  # noqa: BLE001 - a build without units
        return "%g %s" % (value, unit)


class AttachTask:
    """FreeCAD's task dialog for one object's attachment."""

    def __init__(self, obj: Any) -> None:
        self.obj = obj
        self.doc = obj.Document
        self.engine = obj.Attacher
        self.engine.readParametersFromFeature(obj)
        self.suggestion: dict[str, Any] = {}
        #: A way chosen before the picks it needs: its mode.
        self.wanted = ""
        self.error = ""
        self.attached = False
        self.picking = not self.engine.References
        self.bridge = AttachBridge(self)
        from ..app import services
        from ..ui.theme import Theme
        theme = services.theme() or Theme(None)
        self.form = quick_host.make_view(
            None, "AttachTask.qml", {"theme": theme, "attach": self.bridge})
        self.form.setWindowTitle(translate("Nxt", "Attachment"))
        self.bridge.setParent(self.form)
        root = self.form.rootObject()
        # Resized later, never inside the frame that changed the height.
        root.implicitHeightChanged.connect(
            lambda: QtCore.QTimer.singleShot(0, self._fit_height))
        QtCore.QTimer.singleShot(0, self._fit_height)
        self.doc.openTransaction(translate("Nxt", "Edit attachment"))
        self._selectable = self._set_selectable(False)
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)
        self._apply(suggest=True)

    # -- FreeCAD task dialog --

    def getStandardButtons(self) -> int:  # noqa: N802 - FreeCAD API
        buttons = QtWidgets.QDialogButtonBox.StandardButton
        return int((buttons.Ok | buttons.Cancel).value)

    def accept(self) -> bool:
        if self.error:
            return False    # the notice says what to fix
        self._finish()
        self.doc.recompute()
        self.doc.commitTransaction()
        Gui.Control.closeDialog()
        return True

    def reject(self) -> bool:
        self._finish()
        self.doc.abortTransaction()
        self.doc.recompute()
        Gui.Control.closeDialog()
        return True

    # -- picks --

    def addSelection(self, doc: str, name: str, sub: str,  # noqa: N802
                     _point: Any = None) -> None:
        if not self.picking or doc != self.doc.Name:
            return
        picked = reference(self.doc, name, sub, self.obj)
        if picked is None:
            return
        self.bridge.later(lambda: self.add(picked))
        QtCore.QTimer.singleShot(0, Gui.Selection.clearSelection)

    def add(self, picked: tuple[Any, str]) -> None:
        references = list(self.engine.References)
        if picked in references:
            return
        self.engine.References = references + [picked]
        self._apply(suggest=True)
        # As FreeCAD's editor: on to the next while more would fit.
        self.picking = bool(self.suggestion.get("nextRefTypeHint")) \
            and len(references) + 1 < MOST_REFERENCES
        self.bridge.changed.emit()

    def stop_picking(self) -> None:
        self.picking = False
        self.wanted = ""
        self.bridge.changed.emit()

    def remove(self, index: int) -> None:
        references = list(self.engine.References)
        if 0 <= index < len(references):
            del references[index]
            self.engine.References = references
            self.picking = not references or self.picking
            self._apply(suggest=True)

    # -- the way --

    def choose_mode(self, mode: str) -> None:
        if mode in (self.suggestion.get("allApplicableModes") or ()):
            self.wanted = ""
            self.engine.Mode = mode
        else:
            # Its picks come next; until then the attachment stays.
            self.wanted = mode
            self.picking = True
        self._apply()

    def choose_way(self, key: str) -> None:
        way = next((attach_ways.way_of(mode)
                    for mode in self.engine.ImplementedModes
                    if attach_ways.way_of(mode).key == key), None)
        if way is not None:
            self.choose_mode(attach_ways.mode_for_way(
                way, self.engine.Mode,
                self.suggestion.get("allApplicableModes") or ()))

    def detach(self) -> None:
        self.engine.References = []
        self.engine.Mode = DETACHED
        self.wanted = ""
        self.picking = True
        self._apply()

    # -- offset and the rest --

    def set_flipped(self, on: bool) -> None:
        self.engine.Reverse = on
        self._apply()

    def set_path(self, text: str) -> bool:
        value = units.internal_value(text)
        if value is None:
            return False
        self.engine.Parameter = value
        self._apply()
        return True

    def offset(self) -> list[float]:
        placement = self.engine.AttachmentOffset
        yaw, pitch, roll = placement.Rotation.toEuler()
        base = placement.Base
        return [base.x, base.y, base.z, roll, pitch, yaw]

    def set_offset(self, index: int, text: str) -> bool:
        value = units.internal_value(
            text, LENGTH if index < MOVES else ANGLE)
        if value is None:
            return False
        values = self.offset()
        values[index] = value
        self._write_offset(values)
        return True

    def reset_offset(self) -> None:
        self._write_offset([0.0] * (2 * MOVES))

    def _write_offset(self, values: list[float]) -> None:
        x, y, z, roll, pitch, yaw = values
        self.engine.AttachmentOffset = App.Placement(
            App.Vector(x, y, z), App.Rotation(yaw, pitch, roll))
        self._apply()

    # -- applying --

    def _apply(self, suggest: bool = False) -> None:
        """Write the engine to the object, place it, and say how it went."""
        try:
            self.suggestion = dict(self.engine.suggestModes())
        except Exception:  # noqa: BLE001 - a reference that is gone
            self.suggestion = {}
        if suggest:
            self.engine.Mode = attach_ways.mode_after_picks(
                self.engine.Mode, self.wanted, self.suggestion)
            if self.engine.Mode == self.wanted:
                self.wanted = ""
        self.error = ""
        try:
            self.engine.writeParametersToFeature(self.obj)
            self.attached = bool(self.obj.positionBySupport())
        except Exception as err:  # noqa: BLE001 - FreeCAD says why
            self.error = str(err) or type(err).__name__
            self.attached = False
        self.bridge.changed.emit()

    def _finish(self) -> None:
        with contextlib.suppress(Exception):
            Gui.Selection.removeObserver(self)
        self._set_selectable(self._selectable)

    def _set_selectable(self, on: bool) -> bool:
        """The object itself can't be picked as its own reference."""
        view = getattr(self.obj, "ViewObject", None)
        before = bool(getattr(view, "Selectable", True))
        with contextlib.suppress(Exception):
            view.Selectable = on
        return before

    def _fit_height(self) -> None:
        try:
            root = self.form.rootObject()
        except RuntimeError:    # the panel closed before this ran
            return
        if root is not None:
            height = int(root.property("implicitHeight"))
            if height != self.form.minimumHeight():
                self.form.setMinimumHeight(height)


class AttachBridge(QtCore.QObject):
    """What AttachTask.qml shows and does.

    QML's calls are queued: a change may rebuild the very row clicked.
    """

    changed = QtCore.Signal()

    def __init__(self, task: AttachTask) -> None:
        super().__init__()
        self._task = task
        self._jobs: list[Callable[[], Any]] = []
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._run)

    def later(self, job: Callable[[], Any]) -> None:
        self._jobs.append(job)
        self._timer.start()

    def _run(self) -> None:
        jobs, self._jobs = self._jobs, []
        for job in jobs:
            try:
                job()
            except Exception:  # noqa: BLE001 - from a Qt timer
                log.error("could not change the attachment")

    # -- what is shown --

    @QtCore.Property(bool, notify=changed)
    def attached(self) -> bool:
        return self._task.attached

    @QtCore.Property(bool, notify=changed)
    def picking(self) -> bool:
        return self._task.picking

    @QtCore.Property(str, notify=changed)
    def hint(self) -> str:
        """What the next pick would add, if anything."""
        task = self._task
        if task.wanted:
            reachable = task.suggestion.get("reachableModes") or {}
            needs = (reachable.get(task.wanted) or [[]])[0]
        else:
            needs = list(task.suggestion.get("nextRefTypeHint") or ())[:1]
        if not needs:
            return ""
        return translate("Nxt", "Next: %1").replace(
            "%1", attach_ways.needs_text(needs, self._word))

    @QtCore.Property(list, notify=changed)
    def references(self) -> list[dict[str, Any]]:
        task = self._task
        types = list(task.suggestion.get("references_Types") or ())
        rows = []
        for index, (obj, element) in enumerate(task.engine.References):
            kind = types[index] if index < len(types) else "Object"
            name = getattr(obj, "Label", "?")
            rows.append({
                "word": self._word(attach_ways.pick_word(kind)),
                "shape": attach_ways.pick_shape(kind),
                "text": "%s · %s" % (name, element) if element else name,
                "faulty": bool(task.error) and
                index == len(task.engine.References) - 1})
        return rows

    @QtCore.Property(str, notify=changed)
    def problem(self) -> str:
        return self._word(attach_ways.problem(self._task.error)[0]) \
            if self._task.error else ""

    @QtCore.Property(str, notify=changed)
    def fix(self) -> str:
        return self._word(attach_ways.problem(self._task.error)[1]) \
            if self._task.error else ""

    @QtCore.Property(str, notify=changed)
    def wayLabel(self) -> str:  # noqa: N802 - QML API
        mode = self._task.wanted or self._task.engine.Mode
        if mode == DETACHED:
            return ""
        return self._word(self._mode_way(mode).label)

    @QtCore.Property(str, notify=changed)
    def choice(self) -> str:
        return self._word(self._way().choice)

    @QtCore.Property(list, notify=changed)
    def variants(self) -> list[dict[str, str]]:
        found = attach_ways.variants(self._way(),
                                     self._task.engine.ImplementedModes)
        if len(found) < 2:
            return []
        return [{"value": v["value"], "label": self._word(v["label"])}
                for v in found]

    @QtCore.Property(str, notify=changed)
    def variant(self) -> str:
        return self._task.wanted or str(self._task.engine.Mode)

    @QtCore.Property(bool, notify=changed)
    def flipped(self) -> bool:
        return bool(self._task.engine.Reverse)

    @QtCore.Property(bool, notify=changed)
    def alongPath(self) -> bool:  # noqa: N802 - QML API
        return self._task.attached and self._way().along_path

    @QtCore.Property(str, notify=changed)
    def pathText(self) -> str:  # noqa: N802 - QML API
        return "%g" % float(self._task.engine.Parameter)

    @QtCore.Property(list, notify=changed)
    def offset(self) -> list[str]:
        return [_quantity(value, LENGTH if index < MOVES else ANGLE)
                for index, value in enumerate(self._task.offset())]

    @QtCore.Property(bool, notify=changed)
    def offsetUsed(self) -> bool:  # noqa: N802 - QML API
        return any(abs(v) > 1e-9 for v in self._task.offset())

    @QtCore.Property(bool, notify=changed)
    def turns(self) -> bool:
        """The way sets the orientation, so a turn has an effect."""
        return self._task.engine.Mode != "Translate"

    # -- what may be done --

    @QtCore.Slot()
    def pick(self) -> None:
        def start() -> None:
            self._task.picking = True
            self.changed.emit()
        self.later(start)

    @QtCore.Slot()
    def stopPicking(self) -> None:  # noqa: N802 - QML API
        self.later(self._task.stop_picking)

    @QtCore.Slot(int)
    def removeReference(self, index: int) -> None:  # noqa: N802
        self.later(lambda: self._task.remove(index))

    @QtCore.Slot(str)
    def chooseVariant(self, mode: str) -> None:  # noqa: N802 - QML API
        self.later(lambda: self._task.choose_mode(mode))

    @QtCore.Slot(bool)
    def setFlipped(self, on: bool) -> None:  # noqa: N802 - QML API
        self.later(lambda: self._task.set_flipped(on))

    @QtCore.Slot(str, result=bool)
    def setPath(self, text: str) -> bool:  # noqa: N802 - QML API
        if units.internal_value(text) is None:
            return False
        self.later(lambda: self._task.set_path(text))
        return True

    @QtCore.Slot(int, str, result=bool)
    def setOffset(self, index: int, text: str) -> bool:  # noqa: N802
        unit = LENGTH if index < MOVES else ANGLE
        if units.internal_value(text, unit) is None:
            return False
        self.later(lambda: self._task.set_offset(index, text))
        return True

    @QtCore.Slot()
    def resetOffset(self) -> None:  # noqa: N802 - QML API
        self.later(self._task.reset_offset)

    @QtCore.Slot()
    def detach(self) -> None:
        self.later(self._task.detach)

    @QtCore.Slot(float, float, float)
    def openWays(self, x: float, y: float, width: float) -> None:  # noqa: N802
        """The ways as a menu under the field: it may reach past the panel.

        Shown on a later turn: QML's handler must have returned first.
        """
        self.later(lambda: self._menu(x, y, width))

    def _menu(self, x: float, y: float, width: float) -> None:
        task = self._task
        view = task.form
        menu = QtWidgets.QMenu(view)
        menu.setMinimumWidth(int(width))
        chosen: dict[Any, str] = {}
        rows = attach_ways.ways(task.engine.ImplementedModes,
                                task.suggestion, task.engine.Mode)
        heading = ""
        for row in rows:
            section = translate("Nxt", "Fits your picks") if row["fits"] \
                else translate("Nxt", "Needs other picks")
            if task.engine.References and section != heading:
                menu.addSection(section)
                heading = section
            label = self._word(row["label"])
            if row["needs"]:
                label = "%s    (%s)" % (label, translate("Nxt", "add %1")
                                        .replace("%1", attach_ways.needs_text(
                                            row["needs"], self._word)))
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(row["current"])
            chosen[action] = row["key"]
        picked = menu.exec(view.mapToGlobal(QtCore.QPoint(int(x), int(y))))
        menu.deleteLater()
        key = chosen.get(picked, "")
        if key:
            task.choose_way(key)

    # -- helpers --

    @staticmethod
    def _word(text: str) -> str:
        return translate("Nxt", text) if text else ""

    @staticmethod
    def _mode_way(mode: str) -> attach_ways.Way:
        return attach_ways.way_of(mode)

    def _way(self) -> attach_ways.Way:
        return self._mode_way(self._task.wanted or self._task.engine.Mode)


def open_for(obj: Any) -> bool:
    """Show the panel for `obj`; False if another task is open or fails."""
    if not attachable(obj) or Gui.Control.activeDialog():
        return False
    try:
        task = AttachTask(obj)
    except Exception:  # noqa: BLE001 - FreeCAD's editor is the fallback
        log.error("could not open the attachment panel")
        with contextlib.suppress(Exception):
            obj.Document.abortTransaction()
        return False
    Gui.Control.showDialog(task)
    return True
