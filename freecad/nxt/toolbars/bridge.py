"""The object the tool strip's QML calls: its model and its actions.

Rebuilds are deferred and coalesced: FreeCAD lays out a workbench's
toolbars over several events after `workbenchActivated`. In edit mode
items are reordered and removed instead of run; each finished drag or
removal saves the workbench's layout once.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable, Iterator
from typing import Any

import FreeCAD as App

from ..core import log
from ..core.qt import QtCore, QtWidgets
from . import layouts, source
from .models import ToolModel
from .source import Kind

#: Wait after the last toolbar change before reading them all again.
REBUILD_MS = 50
#: Proxied buttons emit nothing when their text or state changes
#: (Draft Tray shows the current layer): read again this often.
BUTTON_POLL_MS = 500


class _MenuPlacer(QtCore.QObject):
    """Moves a menu to `at` as it is shown."""

    def __init__(self, at: QtCore.QPoint) -> None:
        super().__init__()
        self._at = at

    def eventFilter(self, watched: QtCore.QObject,  # noqa: N802
                    event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.Show \
                and isinstance(watched, QtWidgets.QMenu):
            watched.move(self._at)
        return False


@contextlib.contextmanager
def menus_opened_at(at: QtCore.QPoint) -> Iterator[None]:
    """Menus shown meanwhile open at `at`, not by the covered widget.

    A proxied button may open its own menu beside itself (Draft's
    auto-group), and the real button sits covered in a corner.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        yield
        return
    placer = _MenuPlacer(at)
    app.installEventFilter(placer)
    try:
        yield
    finally:
        app.removeEventFilter(placer)


class ToolStripBridge(QtCore.QObject):
    """FreeCAD's toolbars as the strip's model, and its click handlers."""

    iconSizeChanged = QtCore.Signal()  # noqa: N815 - Qt API
    editingChanged = QtCore.Signal()  # noqa: N815 - Qt API

    def __init__(self, main: QtWidgets.QMainWindow, own: Iterable[str],
                 to_global: Callable[[QtCore.QPoint], QtCore.QPoint],
                 workbench: Callable[[], str],
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._main = main
        self._own = tuple(own)
        self._to_global = to_global
        self._workbench = workbench
        self._live: list[source.Entry] = []
        self._editing = False
        self._dragging = False
        self._icon_size = self._main_icon_size()
        self._model = ToolModel(lambda: self._icon_size, self)
        self._reported: set[str] = set()
        self._rebuild_timer = self._timer(REBUILD_MS, self.rebuild)
        self._rebuild_timer.setSingleShot(True)
        self._poll_timer = self._timer(
            BUTTON_POLL_MS, lambda: self._model.refresh_all(Kind.BUTTON))

    def _timer(self, interval: int, slot: Callable[[], None]
               ) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setInterval(interval)
        timer.timeout.connect(slot)
        return timer

    def _main_icon_size(self) -> int:
        return self._main.iconSize().width()

    def schedule(self, *_args: Any) -> None:
        """Read the toolbars again once they settle."""
        self._rebuild_timer.start()

    def rebuild(self) -> None:
        if self._dragging:
            self.schedule()
            return
        size = self._main_icon_size()
        if size != self._icon_size:
            self._icon_size = size
            self.iconSizeChanged.emit()
        try:
            entries, unsupported = source.read(self._main, self._own)
        except Exception:  # noqa: BLE001 - a toolbar torn down mid-read
            log.error("could not read FreeCAD's toolbars")
            return
        self._report(unsupported)
        self._live = entries
        self._model.set_entries(layouts.arrange(
            entries, layouts.load(self._workbench())))
        if self._model.has(Kind.BUTTON):
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    def _report(self, unsupported: list[str]) -> None:
        for name in set(unsupported) - self._reported:
            App.Console.PrintLog(
                "Nxt: tool strip cannot show a toolbar widget %s\n" % name)
        self._reported.update(unsupported)

    def _save(self) -> None:
        workbench = self._workbench()
        layouts.save(workbench, layouts.capture(
            self._model.entries(), self._live, layouts.load(workbench)))

    def stop(self) -> None:
        self._rebuild_timer.stop()
        self._poll_timer.stop()
        self._model.clear()

    # -- QML API -- #

    def _get_model(self) -> QtCore.QObject:
        return self._model

    model = QtCore.Property(QtCore.QObject, _get_model, constant=True)

    def _get_icon_size(self) -> int:
        return self._icon_size

    iconSize = QtCore.Property(  # noqa: N815 - QML API
        int, _get_icon_size, notify=iconSizeChanged)

    def _get_editing(self) -> bool:
        return self._editing

    editing = QtCore.Property(bool, _get_editing, notify=editingChanged)

    @QtCore.Slot(bool)
    def setEditing(self, on: bool) -> None:  # noqa: N802
        """Enter or leave edit mode, where items move instead of run."""
        if on != self._editing:
            self._editing = on
            self.editingChanged.emit()

    @QtCore.Slot()
    def beginDrag(self) -> None:  # noqa: N802
        self._dragging = True

    @QtCore.Slot(int, int)
    def move(self, row: int, to: int) -> None:
        """Move an item while it is dragged; saved when the drag ends."""
        self._model.move(row, to)

    @QtCore.Slot(int, bool)
    def endDrag(self, row: int, remove: bool) -> None:  # noqa: N802
        """Finish a drag at `row`, removing the item if dropped outside."""
        self._dragging = False
        if remove:
            self._model.remove(row)
        self._save()

    @QtCore.Slot(int)
    def removeItem(self, row: int) -> None:  # noqa: N802
        if self._model.remove(row):
            self._save()

    @QtCore.Slot()
    def resetLayout(self) -> None:  # noqa: N802
        """Back to FreeCAD's own toolbars for this workbench."""
        layouts.save(self._workbench(), None)
        self._model.set_entries(self._live)

    @QtCore.Slot(int, float, float)
    def activate(self, row: int, x: float, y: float) -> None:
        """Run the command, or click the button, at `row`.

        (x, y) is below the item in the strip's view: where any menu the
        click opens is placed.
        """
        entry = self._model.entry(row)
        try:
            if entry is None or self._editing:
                return
            if entry.kind is Kind.COMMAND and entry.action is not None \
                    and entry.action.isEnabled():
                entry.action.trigger()
            elif entry.kind is Kind.BUTTON and entry.widget.isEnabled():
                with menus_opened_at(self._global(x, y)):
                    entry.widget.click()
        except Exception:  # noqa: BLE001 - must not reach Qt's event loop
            log.error("tool strip command failed")

    @QtCore.Slot(int, float, float)
    def openMenu(self, row: int, x: float, y: float) -> None:  # noqa: N802
        """Open the dropdown of `row` at (x, y) in the strip's view."""
        entry = self._model.entry(row)
        menu = None if entry is None or entry.widget is None \
            else getattr(entry.widget, "menu", lambda: None)()
        if menu is not None:
            menu.popup(self._global(x, y))

    def _global(self, x: float, y: float) -> QtCore.QPoint:
        return self._to_global(QtCore.QPoint(round(x), round(y)))

    @QtCore.Slot(int, int)
    def choose(self, row: int, index: int) -> None:
        """Pick choice `index` of the selector at `row`."""
        entry = self._model.entry(row)
        if entry is None or entry.kind is not Kind.CHOICE:
            return
        chooser = entry.widget
        try:
            chooser.setCurrentIndex(index)
            if isinstance(chooser, QtWidgets.QComboBox):
                chooser.activated.emit(index)
        except Exception:  # noqa: BLE001 - must not reach Qt's event loop
            log.error("tool strip could not switch the selector")
