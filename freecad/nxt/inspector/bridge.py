"""The QObject the Property Inspector's QML talks to."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..core.qt import QtCore, QtWidgets
from ..tools import task_sync
from . import layout as inspector
from . import templates as inspector_templates
from . import variables

#: Selection and undo counts are polled; both are cheap to read.
POLL_MS = 250


def _in_edit() -> Any:
    """The document object open in a task dialog, if any."""
    try:
        doc = Gui.ActiveDocument
        vp = doc.getInEdit() if doc is not None else None
        return getattr(vp, "Object", None)
    except Exception:
        return None


def _alive(obj: Any) -> bool:
    """Not deleted.

    A closing document takes its objects before its views and panels,
    which may still ask after them.
    """
    try:
        return bool(obj.Name)
    except Exception:
        return False


class InspectorBridge(QtCore.QObject):
    """Serves `inspector.describe` for the selection, and applies edits."""

    changed = QtCore.Signal()
    noticeChanged = QtCore.Signal()
    nativeRequested = QtCore.Signal(str)

    def __init__(self, parent: QtCore.QObject | None = None,
                 task: bool = False,
                 target: Callable[[], Any] | None = None) -> None:
        super().__init__(parent)
        #: In a task of Nxt's own: what it edits, rather than FreeCAD's
        #: object in edit.
        self._target = target
        #: Inside a task dialog (task_layout.py): the object it edits,
        #: never the selection; the Data tab, a template's cards only.
        self._task = task
        self._groups: list[dict[str, Any]] = []
        #: What is wrong with the object, shown above its cards.
        self._notice = ""
        #: Per panel list picking its reference: the item chosen before,
        #: its "Select reference..." item, and what has been picked.
        self._picks: dict[str, dict[str, str]] = {}
        self._title = ""
        self._tab = inspector.DATA
        self._filter = ""
        self._opened: dict[str, bool] = {}
        self._signature: tuple[Any, ...] = ()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._edits: list[Callable[[], None]] = []
        # Edits run on the next event-loop turn: applying one recomputes
        # and rebuilds the cards, which must not destroy the field whose
        # QML handler is still running (QML aborts).
        self._edit_timer = QtCore.QTimer(self)
        self._edit_timer.setSingleShot(True)
        self._edit_timer.setInterval(0)
        self._edit_timer.timeout.connect(self._apply_edits)
        #: While picking for a link: its property and whose it is.
        self._picking = ""
        self._pick_for: list[Any] = []

    # -- lifetime --

    def start(self) -> None:
        self._signature = ()
        self._poll()
        self._timer.start()

    def stop(self) -> None:
        self._end_pick()
        self._timer.stop()

    def _objects(self) -> list[Any]:
        return [o for o in self._wanted() if _alive(o)]

    def _wanted(self) -> list[Any]:
        if self._picking:
            return list(self._pick_for)
        if self._task:
            editing = self._target() if self._target else _in_edit()
            return [] if editing is None else [editing]
        try:
            return list(Gui.Selection.getSelection())
        except Exception:
            return []

    def _poll(self) -> None:
        if self._picking:
            self._take_picks()
        objects = self._objects()
        doc = App.ActiveDocument
        signature = (tuple(o.Name for o in objects),
                     getattr(doc, "UndoCount", 0),
                     getattr(doc, "RedoCount", 0))
        if signature != self._signature:
            self._signature = signature
            self.refresh(objects)
        elif self._task:
            # A task dialog changes the feature without an undo step.
            self.refresh(objects, quiet=True)

    def refresh(self, objects: list[Any] | None = None,
                quiet: bool = False) -> None:
        """Lay the cards out again; `quiet`: only if something changed.

        A rebuild while typing would take the field away.
        """
        objects = self._objects() if objects is None else objects
        before = self._groups
        self._groups = inspector.describe(objects, self._tab, self._filter)
        if self._task:
            self._groups = [g for g in self._groups if g.get("template")]
            if len(objects) == 1:
                lists = task_sync.combos(objects[0])
                self._follow_picks(objects, lists)
                task_sync.as_combo(
                    self._groups, lists,
                    {p: pick["picked"] for p, pick in self._picks.items()})
        self._set_notice(objects)
        for group in self._groups:
            if group["name"] in self._opened and not self._filter:
                group["open"] = self._opened[group["name"]]
        names = [o.Label for o in objects]
        if not names:
            self._title = ""
        elif len(names) == 1:
            self._title = names[0]
        else:
            shown = ", ".join(names[:2])
            self._title = "%s · %d selected" % (shown, len(names))
        if quiet and self._groups == before:
            return
        self.changed.emit()

    # -- what QML reads --

    def _set_notice(self, objects: list[Any]) -> None:
        notice = ""
        if self._picks:
            wrong = task_sync.not_an_axis()
            if wrong:
                notice = ("%s can't give an axis: pick a straight edge, a "
                          "circle, a flat face or an axis." % wrong)
        if not notice and len(objects) == 1:
            obj = objects[0]
            if "Invalid" in (getattr(obj, "State", None) or ()):
                try:
                    notice = str(obj.getStatusString())
                except Exception:
                    notice = "This feature failed to recompute."
        if notice != self._notice:
            self._notice = notice
            self.noticeChanged.emit()

    @QtCore.Property(str, notify=noticeChanged)
    def notice(self) -> str:
        return self._notice

    @QtCore.Property(list, notify=changed)
    def groups(self) -> list[dict[str, Any]]:
        return self._groups

    @QtCore.Property(str, notify=changed)
    def title(self) -> str:
        return self._title

    @QtCore.Property(str, notify=changed)
    def tab(self) -> str:
        return self._tab

    @QtCore.Property(str, notify=changed)
    def owner(self) -> str:
        """Expression owner "Document#Name"; empty on the View tab."""
        objects = self._objects()
        if not objects or self._tab != inspector.DATA:
            return ""
        obj = objects[0]
        return "%s#%s" % (obj.Document.Name, obj.Name)

    @QtCore.Property(str, notify=changed)
    def picking(self) -> str:
        """The link property picks in the tree or 3D view go to, if any."""
        return self._picking

    @QtCore.Property(bool, notify=changed)
    def several(self) -> bool:
        return len(self._objects()) > 1

    # -- what QML does --

    @QtCore.Slot(str)
    def setTab(self, tab: str) -> None:
        self._tab = tab
        self.refresh()

    @QtCore.Slot(str)
    def setFilter(self, text: str) -> None:
        self._filter = text
        self.refresh()

    @QtCore.Slot(str, bool)
    def setGroupOpen(self, name: str, opened: bool) -> None:
        # Keyed by name so a group stays open across selections.
        self._opened[name] = opened

    def _defer(self, edit: Callable[[], None]) -> None:
        self._edits.append(edit)
        self._edit_timer.start()

    def _apply_edits(self) -> None:
        edits, self._edits = self._edits, []
        for edit in edits:
            edit()

    @QtCore.Slot(str, "QVariant", str)
    def setValue(self, prop: str, value: Any, unit: str) -> None:
        self._defer(lambda: self._set_value(prop, value, unit))

    def _set_value(self, prop: str, value: Any, unit: str) -> None:
        objects = self._objects()
        edits: list[tuple[str, Any]] = [(prop, value)]
        if self._tab == inspector.DATA:
            coupled = inspector_templates.coupled(
                inspector_templates.for_objects(objects), objects, prop,
                value)
            if coupled is not None:
                edits = coupled
            if not edits:
                return
            self._remember_pick(objects, prop, value)
            # Open task panels take the edit so previews follow.
            rest = [(p, v) for p, v in edits
                    if not task_sync.set_in_task(
                        objects, p, v, unit if p == prop else "")]
            if not rest:
                self._recompute(objects)
                self.refresh()
                return
            edits = rest
        if inspector.apply_many(
                objects, [(p, v, unit if p == prop else "")
                          for p, v in edits], self._tab):
            self.refresh()

    # -- a VarSet's variables (templates: variables = true) --

    def _refresh_later(self) -> None:
        # Not while QML is still in the call: the rebuild would destroy
        # the field that asked before it could close its form.
        QtCore.QTimer.singleShot(0, self.refresh)

    def _sole(self) -> Any:
        objects = self._objects()
        return objects[0] if len(objects) == 1 else None

    @QtCore.Slot(str, str, str, result=str)
    def editVariable(self, prop: str, name: str, tip: str) -> str:
        """Rename a variable and set its tooltip; "" or why not."""
        obj = self._sole()
        if obj is None:
            return "Select one variable set."
        why = variables.edit(obj, prop, name, tip)
        if not why:
            self._refresh_later()
        return why

    @QtCore.Slot(str, str, str, result=str)
    def addVariable(self, type_id: str, name: str, tip: str) -> str:
        """Add a variable to the selected VarSet; "" or why not."""
        obj = self._sole()
        if obj is None:
            return "Select one variable set."
        why = variables.add(obj, type_id, name, tip)
        if not why:
            self._refresh_later()
        return why

    @QtCore.Slot(result="QVariantList")
    def variableTypes(self) -> list[dict[str, str]]:
        """The types a new variable may have."""
        return [{"id": t, "label": label} for t, label in variables.TYPES]

    @QtCore.Slot(str, int, result=float)
    def wheelStep(self, unit: str, modifiers: int) -> float:  # noqa: N802
        """One wheel notch on a field of `unit`, as the drag handles step."""
        from ..tools import gizmos
        return gizmos.wheel_step(gizmos.read(), unit, modifiers)

    def _remember_pick(self, objects: list[Any], prop: str,
                       value: Any) -> None:
        """Choosing a list's "Select reference...": keep what it was.

        Any other choice ends its picking.
        """
        if len(objects) != 1:
            return
        lists = task_sync.combos(objects[0])
        if prop not in lists:
            return
        items, current = lists[prop]
        select = task_sync.select_item(items)
        if select and str(value) == select:
            if prop not in self._picks:
                self._picks[prop] = {"before": current, "select": select,
                                     "picked": ""}
        else:
            self._picks.pop(prop, None)

    @staticmethod
    def _pick_again(objects: list[Any], prop: str,
                    select: str) -> Callable[[], None]:
        def again() -> None:
            task_sync.set_in_task(objects, prop, select)
        return again

    def _follow_picks(self, objects: list[Any],
                      lists: dict[str, tuple[list[str], str]]) -> None:
        """A pick the panel took: hold it, and pick on until ticked.

        The panel leaves picking once it takes one; it is sent back to
        "Select reference..." so a different pick can replace it.
        """
        for prop, pick in list(self._picks.items()):
            if prop not in lists:
                self._picks.pop(prop)
                continue
            items, current = lists[prop]
            if current == pick["select"]:
                continue
            pick["picked"] = current
            select = task_sync.select_item(items)
            if select:
                pick["select"] = select
                self._defer(self._pick_again(objects, prop, select))

    @staticmethod
    def _recompute(objects: list[Any]) -> None:
        """The feature again, as its panel's own preview does."""
        for obj in objects:
            try:
                doc = obj.Document
                if hasattr(doc, "recomputeFeature"):
                    doc.recomputeFeature(obj)
                else:
                    obj.recompute()
            except Exception:
                pass

    @QtCore.Slot(str, str)
    def openLink(self, prop: str, key: str) -> None:  # noqa: N802
        """A chip double-clicked: a sketch opens for editing."""
        self._defer(lambda: self._open_link(prop, key))

    def _open_link(self, prop: str, key: str) -> None:
        from ..tools import editing
        objects = self._objects()
        if not objects:
            return
        try:
            target = inspector.link_items(
                getattr(objects[0], prop))[int(key)][0]
        except (AttributeError, IndexError, ValueError):
            return
        if editing.is_sketch(target):
            editing.edit_sketch(target)

    @QtCore.Slot(str, str)
    def removeLink(self, prop: str, key: str) -> None:
        if prop.endswith(task_sync.PICKING):
            pick = self._picks.get(prop[:-len(task_sync.PICKING)])
            if pick is not None:
                pick["picked"] = ""
                self.refresh()
            return
        self._defer(lambda: self._remove_link(prop, key))

    def _remove_link(self, prop: str, key: str) -> None:
        if inspector.edit_links(self._objects(), prop, remove=key):
            self.refresh()

    @QtCore.Slot(str)
    def pickLinks(self, prop: str) -> None:
        """Start, or with the same property end, picking for a link.

        A panel list's reference row ends its picking with what it holds,
        or with what the list had before if nothing was picked.
        """
        if prop.endswith(task_sync.PICKING):
            listed = prop[:-len(task_sync.PICKING)]
            pick = self._picks.pop(listed, None)
            objects = self._objects()
            chosen = pick["picked"] or pick["before"] if pick else ""
            if chosen and task_sync.set_in_task(objects, listed, chosen):
                self._recompute(objects)
            self.refresh()
            return
        if self._picking:
            done = self._picking == prop
            self._end_pick()
            if done:
                return
        objects = self._objects()
        if not objects or self._tab != inspector.DATA:
            return
        self._picking, self._pick_for = prop, objects
        Gui.Selection.clearSelection()
        self.changed.emit()

    def _take_picks(self) -> None:
        try:
            picked = list(Gui.Selection.getSelectionEx())
        except Exception:
            return
        if not picked:
            return
        Gui.Selection.clearSelection()
        mine = {o.Name for o in self._pick_for}
        pairs = [(sel.Object, sub) for sel in picked
                 if sel.Object.Name not in mine
                 for sub in (list(sel.SubElementNames) or [""])]
        if pairs and inspector.edit_links(self._pick_for, self._picking,
                                          add=pairs):
            self.refresh()

    def _end_pick(self) -> None:
        if not self._picking:
            return
        objects, self._picking, self._pick_for = self._pick_for, "", []
        try:
            Gui.Selection.clearSelection()
            for obj in objects:
                Gui.Selection.addSelection(obj)
        except Exception:
            pass
        self.changed.emit()

    @QtCore.Slot()
    def endPick(self) -> None:  # noqa: N802 - QML API
        self._end_pick()

    @QtCore.Slot(str, str, str)
    def setPart(self, prop: str, part: str, text: str) -> None:
        self._defer(lambda: self._set_part(prop, part, text))

    def _set_part(self, prop: str, part: str, text: str) -> None:
        if inspector.apply(self._objects(), prop, text, self._tab,
                           part=part):
            self.refresh()

    @QtCore.Slot(str, str)
    def pickColour(self, prop: str, current: str) -> None:
        from ..core.qt import QtGui
        colour = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(current or "#808080"),
            Gui.getMainWindow(), inspector.label_for(prop))
        if colour.isValid():
            self.setValue(prop, colour.name(), "")

    @QtCore.Slot(str)
    def editNative(self, prop: str) -> None:
        """Hand one property to FreeCAD's own editor."""
        self.nativeRequested.emit(prop)
