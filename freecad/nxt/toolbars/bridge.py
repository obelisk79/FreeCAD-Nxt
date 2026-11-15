"""The object the tool strip's QML calls: its model and its actions.

Rebuilds are deferred and coalesced: FreeCAD lays out a workbench's
toolbars over several events after `workbenchActivated`. In edit mode
items are reordered and removed instead of run; each finished drag or
removal saves the workbench's layout once. The drawer's catalog is read
the first time edit mode opens, a turn after it is drawn.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import FreeCAD as App

from ..app.i18n import translate
from ..core import log
from ..core.qt import QtCore, QtGui, QtWidgets
from . import catalog, groups, icons, layouts, source
from .models import CatalogModel, ToolModel, last_member
from .source import Kind

#: Wait after the last toolbar change before reading them all again.
REBUILD_MS = 50
#: Proxied buttons emit nothing when their text or state changes
#: (Draft Tray shows the current layer): read again this often.
BUTTON_POLL_MS = 500
LAYOUT_FILE = "toolbar-layouts.json"
LAYOUT_FILTER = "JSON (*.json)"


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
    drawerChanged = QtCore.Signal()  # noqa: N815 - Qt API
    groupChanged = QtCore.Signal()  # noqa: N815 - Qt API

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
        self._missing: list[str] = []
        #: The group open in the editor row, by identity: rows move.
        self._edited: source.Entry | None = None
        self._menu: QtWidgets.QMenu | None = None
        #: Group key -> the member key last used, kept across rebuilds.
        self._last_used: dict[str, str] = {}
        self._editing = False
        self._dragging = False
        self._icon_size = self._main_icon_size()
        self._model = ToolModel(lambda: self._icon_size, self)
        self._reported: set[str] = set()
        self._rebuild_timer = self._timer(REBUILD_MS, self.rebuild)
        self._rebuild_timer.setSingleShot(True)
        self._poll_timer = self._timer(
            BUTTON_POLL_MS, lambda: self._model.refresh_all(Kind.BUTTON))
        self._stand_ins = catalog.StandIns(self)
        self._commands: list[catalog.Command] | None = None
        self._filters: list[dict[str, str]] = []
        self._filter = catalog.ALL
        self._query = ""
        self._catalog = CatalogModel(lambda: self._icon_size, catalog.icon,
                                     self)
        self._catalog_timer = self._timer(0, self._load_catalog)
        self._catalog_timer.setSingleShot(True)
        self._file_action: Callable[[], None] = self._export
        self._file_timer = self._timer(0, lambda: self._file_action())
        self._file_timer.setSingleShot(True)
        for signal in (self._model.modelReset, self._model.rowsInserted,
                       self._model.rowsRemoved):
            signal.connect(self._mark_placed)

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
        arranged, self._missing = layouts.arrange(
            entries, layouts.load(self._workbench()), self._resolve)
        for entry in arranged:
            used = self._last_used.get(entry.key)
            member = next((m for m in entry.members if m.key == used), None)
            if member is not None:
                groups.use(entry, member)
        self._model.set_entries(arranged)
        if self._model.has(Kind.BUTTON):
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    def _report(self, unsupported: list[str]) -> None:
        for name in set(unsupported) - self._reported:
            App.Console.PrintLog(
                "Nxt: tool strip cannot show a toolbar widget %s\n" % name)
        self._reported.update(unsupported)

    def _resolve(self, key: str) -> source.Entry | None:
        group = groups.freecad_group(key)
        if group is not None:
            return group
        action = self._stand_ins.action(key)
        return None if action is None else source.Entry(
            Kind.COMMAND, action, None, key)

    def _load_catalog(self) -> None:
        try:
            self._commands, groups = catalog.read()
        except Exception:  # noqa: BLE001 - FreeCAD's command list
            log.error("could not read FreeCAD's commands")
            self._commands, groups = [], []
        self._filters = [{"id": key, "label": label}
                         for key, label in groups]
        self._show_catalog()
        self.drawerChanged.emit()

    def _show_catalog(self) -> None:
        self._catalog.set_commands(catalog.search(
            self._commands or [], self._query, self._filter))
        self._mark_placed()

    def _mark_placed(self, *_args: Any) -> None:
        self._catalog.set_placed(self._model.keys())

    def _save(self) -> None:
        workbench = self._workbench()
        layouts.save(workbench, layouts.capture(
            self._model.entries(), self._live, layouts.load(workbench),
            self._missing))

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
            if not on:
                self._close_editing()
            self.editingChanged.emit()
            self.drawerChanged.emit()
            if on and self._commands is None:
                self._catalog_timer.start()

    def _get_catalog(self) -> QtCore.QObject:
        return self._catalog

    catalogModel = QtCore.Property(  # noqa: N815 - QML API
        QtCore.QObject, _get_catalog, constant=True)

    def _get_filters(self) -> list[dict[str, str]]:
        return self._filters

    filters = QtCore.Property(list, _get_filters, notify=drawerChanged)

    def _get_filter(self) -> str:
        return self._filter

    filter = QtCore.Property(str, _get_filter, notify=drawerChanged)

    def _get_loading(self) -> bool:
        return self._editing and self._commands is None

    loading = QtCore.Property(bool, _get_loading, notify=drawerChanged)

    @QtCore.Slot(str)
    def setQuery(self, text: str) -> None:  # noqa: N802
        self._query = text
        self._show_catalog()

    @QtCore.Slot(str)
    def setFilter(self, group: str) -> None:  # noqa: N802
        self._filter = group
        self._show_catalog()
        self.drawerChanged.emit()

    @QtCore.Slot(str, int, result=int)
    def insertCommand(self, key: str, at: int) -> int:  # noqa: N802
        """Put a command at `at` while it is dragged in; its row, or -1."""
        entry = None if key in self._model.keys() else self._resolve(key)
        return -1 if entry is None else self._model.insert(at, entry)

    @QtCore.Slot(int, result=int)
    def insertSeparator(self, at: int) -> int:  # noqa: N802
        return self._model.insert(at, source.SEPARATOR)

    @QtCore.Slot(str)
    def appendCommand(self, key: str) -> None:  # noqa: N802
        if self.insertCommand(key, -1) >= 0:
            self._save()

    @QtCore.Slot()
    def appendSeparator(self) -> None:  # noqa: N802
        self.insertSeparator(-1)
        self._save()

    def _close_editing(self) -> None:
        self.editGroup(-1)
        empty = [row for row, e in enumerate(self._model.entries())
                 if groups.is_empty(e)]
        for row in reversed(empty):
            self._model.remove(row)
        if empty:
            self._save()

    # -- groups -- #

    def _row_of(self, entry: source.Entry | None) -> int:
        for row, shown in enumerate(self._model.entries()):
            if shown is entry:
                return row
        return -1

    def _group_at(self, row: int) -> source.Entry | None:
        entry = self._model.entry(row)
        return entry if groups.editable(entry) else None

    def _show_group(self, row: int, group: source.Entry) -> None:
        """Put the changed `group` at `row`.

        A group left with one member becomes that command only as the
        editor closes, so removing members never moves the editor away.
        """
        if self._edited is self._model.entry(row):
            self._edited = group
        self._model.replace(row, group)
        self.groupChanged.emit()
        self._save()

    @QtCore.Slot(int, result=int)
    def insertGroup(self, at: int) -> int:  # noqa: N802
        """A new empty group at `at`, while the New group tile is dragged."""
        return self._model.insert(at, groups.new(translate("Nxt", "Group")))

    @QtCore.Slot(str, int, result=bool)
    def addToGroup(self, key: str, row: int) -> bool:  # noqa: N802
        """Put a command from the drawer into the group at `row`."""
        group = self._group_at(row)
        member = None if group is None or key in self._model.keys() \
            else self._resolve(key)
        if group is None or member is None or member.kind is not Kind.COMMAND:
            return False
        self._show_group(row, groups.added(group, member))
        return True

    @QtCore.Slot(int, int)
    def dropIntoGroup(self, row: int, group_row: int) -> None:  # noqa: N802
        """End a drag by moving the strip's command at `row` into a group."""
        self._dragging = False
        entry, group = self._model.entry(row), self._group_at(group_row)
        if entry is None or group is None or entry.kind is not Kind.COMMAND:
            self._save()
            return
        self._model.remove(row)
        group_row -= 1 if row < group_row else 0
        self._show_group(group_row, groups.added(group, entry))

    @QtCore.Slot(int)
    def editGroup(self, row: int) -> None:  # noqa: N802
        """Open the group at `row` in the editor row; -1 closes it."""
        group = self._group_at(row)
        closing = self._edited
        self._edited = group
        self.groupChanged.emit()
        closed_row = self._row_of(closing)
        if closing is not None and closing is not group and closed_row >= 0:
            lone = groups.lone_member(closing)
            if lone is not None:
                self._model.replace(closed_row, lone)
                self._save()

    def _edited_row(self) -> int:
        return self._row_of(self._edited)

    @QtCore.Slot(list)
    def setMemberOrder(self, keys: list[str]) -> None:  # noqa: N802
        """The edited group's members in the order the editor shows."""
        row = self._edited_row()
        if row >= 0 and self._edited is not None:
            self._show_group(row, groups.reordered(self._edited, keys))

    @QtCore.Slot(int)
    def removeMember(self, index: int) -> None:  # noqa: N802
        row = self._edited_row()
        if row >= 0 and self._edited is not None:
            self._show_group(row, groups.without(self._edited, index))

    @QtCore.Slot(str)
    def renameGroup(self, name: str) -> None:  # noqa: N802
        row = self._edited_row()
        if row >= 0 and self._edited is not None \
                and self._edited.group is not None:
            self._edited.group.name = name.strip()
            self._model.refresh(row)
            self._save()

    @QtCore.Slot()
    def ungroup(self) -> None:
        """Put the edited group's commands on the strip in its place."""
        row, group = self._edited_row(), self._edited
        if row < 0 or group is None:
            return
        self._edited = None
        self._model.remove(row)
        for offset, member in enumerate(group.members):
            self._model.insert(row + offset, member)
        self.groupChanged.emit()
        self._save()

    def _get_edited_row(self) -> int:
        return self._edited_row()

    editedGroup = QtCore.Property(  # noqa: N815 - QML API
        int, _get_edited_row, notify=groupChanged)

    def _get_group_name(self) -> str:
        state = None if self._edited is None else self._edited.group
        return "" if state is None else state.name

    groupName = QtCore.Property(  # noqa: N815 - QML API
        str, _get_group_name, notify=groupChanged)

    def _get_group_members(self) -> list[dict[str, str]]:
        members = () if self._edited is None else self._edited.members
        return [{"key": m.key,
                 "text": "" if m.action is None else m.action.text(),
                 "icon": "" if m.action is None
                 else icons.url(m.action.icon(), self._icon_size)}
                for m in members]

    groupMembers = QtCore.Property(  # noqa: N815 - QML API
        list, _get_group_members, notify=groupChanged)

    @QtCore.Slot()
    def beginDrag(self) -> None:  # noqa: N802
        self._dragging = True

    @QtCore.Slot()
    def cancelDrag(self) -> None:  # noqa: N802
        """A drag from the drawer let go before reaching the strip."""
        self._dragging = False

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
        self._missing = []
        self._model.set_entries(self._live)

    @QtCore.Slot()
    def exportLayouts(self) -> None:  # noqa: N802
        self._later(self._export)

    @QtCore.Slot()
    def importLayouts(self) -> None:  # noqa: N802
        self._later(self._import)

    def _later(self, action: Callable[[], None]) -> None:
        # A file dialog spins its own event loop, which must not run
        # inside the QML click that asked for it.
        self._file_action = action
        self._file_timer.start()

    def _export(self) -> None:
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self._main, translate("Nxt", "Export toolbar layouts"),
            LAYOUT_FILE, LAYOUT_FILTER)
        if not path:
            return
        try:
            Path(path).write_text(layouts.export_text(), encoding="utf-8")
        except OSError as exc:
            App.Console.PrintError("Nxt: could not write %s: %s\n"
                                   % (path, exc))

    def _import(self) -> None:
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self._main, translate("Nxt", "Import toolbar layouts"), "",
            LAYOUT_FILTER)
        if not path:
            return
        try:
            layouts.import_text(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            App.Console.PrintError("Nxt: could not import %s: %s\n"
                                   % (path, exc))
            return
        self.rebuild()

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
            if entry.kind is Kind.GROUP:
                member = last_member(entry)
                if member is not None and member.action is not None \
                        and member.action.isEnabled():
                    member.action.trigger()
            elif entry.kind is Kind.COMMAND and entry.action is not None \
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
        if entry is not None and entry.kind is Kind.GROUP:
            self._group_menu(entry).popup(self._global(x, y))
            return
        menu = None if entry is None or entry.widget is None \
            else getattr(entry.widget, "menu", lambda: None)()
        if menu is not None:
            menu.popup(self._global(x, y))

    def _group_menu(self, group: source.Entry) -> QtWidgets.QMenu:
        """A menu of the group's members; the one picked becomes its face."""
        if self._menu is not None:
            self._menu.deleteLater()
        menu = QtWidgets.QMenu(self._main)
        for member in group.members:
            if member.action is not None:
                menu.addAction(member.action)

        def picked(action: QtGui.QAction) -> None:
            member = next((m for m in group.members if m.action is action),
                          None)
            if member is None:
                return
            self._last_used[group.key] = member.key
            if groups.use(group, member):
                self._model.refresh(self._row_of(group))

        menu.triggered.connect(picked)
        self._menu = menu
        return menu

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
