"""The QObject the Property Inspector's QML talks to."""

from __future__ import annotations

from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..qt import QtCore, QtWidgets
from . import inspector

#: Selection and the undo stack are polled: together they change whenever
#: what the inspector shows could have, and reading them is cheap.
POLL_MS = 250


class InspectorBridge(QtCore.QObject):
    """Serves `inspector.describe` for the selection, and applies edits."""

    changed = QtCore.Signal()
    nativeRequested = QtCore.Signal(str)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._groups: list[dict[str, Any]] = []
        self._title = ""
        self._tab = inspector.DATA
        self._filter = ""
        self._opened: dict[str, bool] = {}
        self._signature: tuple[Any, ...] = ()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

    # -- lifetime --------------------------------------------------------- #

    def start(self) -> None:
        self._signature = ()
        self._poll()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _objects(self) -> list[Any]:
        try:
            return list(Gui.Selection.getSelection())
        except Exception:
            return []

    def _poll(self) -> None:
        objects = self._objects()
        doc = App.ActiveDocument
        signature = (tuple(o.Name for o in objects),
                     getattr(doc, "UndoCount", 0),
                     getattr(doc, "RedoCount", 0))
        if signature != self._signature:
            self._signature = signature
            self.refresh(objects)

    def refresh(self, objects: list[Any] | None = None) -> None:
        objects = self._objects() if objects is None else objects
        self._groups = inspector.describe(objects, self._tab, self._filter)
        for group in self._groups:
            if group["name"] in self._opened and not self._filter:
                group["open"] = self._opened[group["name"]]
        names = [o.Label for o in objects]
        if not names:
            self._title = ""   # QML says so, in its own words
        elif len(names) == 1:
            self._title = names[0]
        else:
            shown = ", ".join(names[:2])
            self._title = "%s · %d selected" % (shown, len(names))
        self.changed.emit()

    # -- what QML reads ----------------------------------------------------- #

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
        """The object expressions are written for: "Document#Name".

        The first selected object's, on the Data tab, where expressions
        bind; none on the View tab, whose properties are the view
        provider's.
        """
        objects = self._objects()
        if not objects or self._tab != inspector.DATA:
            return ""
        obj = objects[0]
        return "%s#%s" % (obj.Document.Name, obj.Name)

    @QtCore.Property(bool, notify=changed)
    def several(self) -> bool:
        return len(self._objects()) > 1

    # -- what QML does ------------------------------------------------------ #

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
        # Remembered per group name, so a group you opened stays open as
        # the selection moves between objects that share it.
        self._opened[name] = opened

    @QtCore.Slot(str, "QVariant", str)
    def setValue(self, prop: str, value: Any, unit: str) -> None:
        if inspector.apply(self._objects(), prop, value, self._tab, unit):
            self.refresh()

    @QtCore.Slot(str, str, str)
    def setPart(self, prop: str, part: str, text: str) -> None:
        if inspector.apply(self._objects(), prop, text, self._tab,
                           part=part):
            self.refresh()

    @QtCore.Slot(str, str)
    def pickColour(self, prop: str, current: str) -> None:
        from ..qt import QtGui
        colour = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(current or "#808080"),
            Gui.getMainWindow(), inspector.label_for(prop))
        if colour.isValid():
            self.setValue(prop, colour.name(), "")

    @QtCore.Slot(str)
    def editNative(self, prop: str) -> None:
        """Hand one property to FreeCAD's own editor."""
        self.nativeRequested.emit(prop)
