"""The object the tool strips' QML calls: their models and actions.

One bridge serves every strip (top, left, right); each has its own
model, and its view passes its area to the slots. Rebuilds are deferred
and coalesced: FreeCAD lays out a workbench's toolbars over several
events after `workbenchActivated`. In edit mode items are reordered,
moved between rows and areas, and removed instead of run; each finished
change saves the workbench's layout once. The drawer's catalog is read
the first time edit mode opens, a turn after it is drawn.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable, Iterator
from typing import Any

import FreeCAD as App

from ..app.i18n import translate
from ..core import log, settings
from ..core.qt import QtCore, QtGui, QtWidgets
from . import catalog, groups, icons, layouts, models, source, state
from .models import CatalogModel, ToolModel, last_member
from .source import Kind

#: Wait after the last toolbar change before reading them all again.
REBUILD_MS = 50
#: Proxied buttons emit nothing when their text or state changes
#: (Draft Tray shows the current layer): read again this often.
BUTTON_POLL_MS = 500
#: FreeCAD's toolbar icon sizes, offered in edit mode.
ICON_SIZES = (16, 20, 24, 28, 32, 40, 48)
ICON_SETTING = "ToolStripIconSize"
OTHER_ICON_SETTING = "ToolStripOtherIconSize"
LOCK_SETTING = "ToolStripLocked"
TOP = state.TOP
#: Where on screen a strip's view is: its area and the point in it.
Locate = Callable[[QtCore.QPoint], tuple[str, QtCore.QPointF] | None]
#: The drawer's separator and New group tiles, as their drags carry them.
SEPARATOR_KEY = "|"
GROUP_KEY = "+group"
#: dropCarried's "not on a new-row zone".
NOT_NEW_ROW = -2


def widget_name(entry: source.Entry) -> str:
    """What the drawer calls a toolbar widget.

    Its text or tip, else the toolbar it is on ("Workbench" for the
    workbench selector).
    """
    widget = entry.widget
    for text in (entry.action.text() if entry.action else "",
                 widget.toolTip() if widget is not None else ""):
        if text.strip():
            return models.plain(text)
    return entry.key.split("#")[0]


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
    """FreeCAD's toolbars as the strips' models, and their click handlers."""

    iconSizeChanged = QtCore.Signal()  # noqa: N815 - Qt API
    editingChanged = QtCore.Signal()  # noqa: N815 - Qt API
    drawerChanged = QtCore.Signal()  # noqa: N815 - Qt API
    groupChanged = QtCore.Signal()  # noqa: N815 - Qt API
    #: The areas holding something changed (a side strip shows or goes).
    areasChanged = QtCore.Signal()  # noqa: N815 - Qt API
    lockChanged = QtCore.Signal()  # noqa: N815 - Qt API
    carriedChanged = QtCore.Signal()  # noqa: N815 - Qt API
    #: The carried item is over `area`'s strip at x, y; "" over none.
    carriedOver = QtCore.Signal(str, float, float)  # noqa: N815 - Qt API
    #: The carried item was let go over `area`'s strip at x, y.
    carriedDropped = QtCore.Signal(str, float, float)  # noqa: N815

    def __init__(self, main: QtWidgets.QMainWindow, own: Iterable[str],
                 to_global: Callable[[str, QtCore.QPoint], QtCore.QPoint],
                 workbench: Callable[[], str],
                 parent: QtCore.QObject | None = None, *,
                 locate: Locate = lambda _point: None) -> None:
        super().__init__(parent)
        self._locate = locate
        self._main = main
        self._own = tuple(own)
        self._to_global = to_global
        self._workbench = workbench
        self._live: source.Areas = {}
        self._missing: list[str] = []
        #: The group open in the editor row, by identity: rows move.
        self._edited: source.Entry | None = None
        self._menu: QtWidgets.QMenu | None = None
        #: Group key -> the member key last used, kept across rebuilds.
        self._last_used: dict[str, str] = {}
        self._editing = False
        self._dragging = False
        self._icon_size = self._wanted_icon_size(ICON_SETTING)
        self._other_icon_size = self._wanted_icon_size(OTHER_ICON_SETTING)
        self._locked = {a for a in str(settings.get(LOCK_SETTING)).split(",")
                        if a in layouts.LOCKABLE}
        self._models = {area: ToolModel(self._size_for(area), self)
                        for area in state.AREAS}
        self._reported: set[str] = set()
        self._rebuild_timer = self._timer(REBUILD_MS, self.rebuild)
        self._rebuild_timer.setSingleShot(True)
        self._poll_timer = self._timer(BUTTON_POLL_MS, self._poll_buttons)
        self._stand_ins = catalog.StandIns(self)
        self._commands: list[catalog.Command] | None = None
        self._filters: list[dict[str, str]] = []
        self._filter = catalog.ALL
        self._query = ""
        self._catalog = CatalogModel(lambda: self._icon_size, catalog.icon,
                                     self)
        self._catalog_timer = self._timer(0, self._load_catalog)
        self._catalog_timer.setSingleShot(True)
        #: The item dragged out of its view: (area, row) or a drawer key.
        self._carried: tuple[str, int] | str | None = None
        self._carried_look = ("", "")
        self._carry_target: tuple[str, QtCore.QPointF] | None = None
        for model in self._models.values():
            for signal in (model.modelReset, model.rowsInserted,
                           model.rowsRemoved):
                signal.connect(self._changed_areas)

    def _timer(self, interval: int, slot: Callable[[], None]
               ) -> QtCore.QTimer:
        timer = QtCore.QTimer(self)
        timer.setInterval(interval)
        timer.timeout.connect(slot)
        return timer

    def _wanted_icon_size(self, setting: str) -> int:
        chosen = int(settings.get(setting) or 0)
        return chosen or self._main.iconSize().width()

    def _size_for(self, area: str) -> Callable[[], int]:
        # The top strip's icons serve both of its row sizes.
        if area == TOP:
            return lambda: max(self._icon_size, self._other_icon_size)
        return lambda: self._other_icon_size

    def _m(self, area: str) -> ToolModel:
        return self._models.get(area, self._models[TOP])

    def _poll_buttons(self) -> None:
        for model in self._models.values():
            model.refresh_all(Kind.BUTTON)

    def schedule(self, *_args: Any) -> None:
        """Read the toolbars again once they settle."""
        self._rebuild_timer.start()

    def rebuild(self) -> None:
        if self._dragging:
            self.schedule()
            return
        sizes = (self._wanted_icon_size(ICON_SETTING),
                 self._wanted_icon_size(OTHER_ICON_SETTING))
        if sizes != (self._icon_size, self._other_icon_size):
            self._icon_size, self._other_icon_size = sizes
            self._catalog.forget_icons()
            self.iconSizeChanged.emit()
        try:
            live, unsupported = source.read(self._main, self._own)
        except Exception:  # noqa: BLE001 - a toolbar torn down mid-read
            log.error("could not read FreeCAD's toolbars")
            return
        self._report(unsupported)
        self._live = live
        if self._commands is not None:
            self._show_catalog()
        arranged, self._missing = layouts.arrange(
            live, layouts.load_for(self._workbench(), self._locked),
            self._resolve, self._locked)
        for entries in arranged.values():
            for entry in entries:
                used = self._last_used.get(entry.key)
                member = next((m for m in entry.members if m.key == used),
                              None)
                if member is not None:
                    groups.use(entry, member)
        self._show(arranged)

    def _show(self, areas: source.Areas) -> None:
        for area, model in self._models.items():
            model.set_entries(areas.get(area, []))
        if any(m.has(Kind.BUTTON) for m in self._models.values()):
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    def _report(self, unsupported: list[str]) -> None:
        for name in set(unsupported) - self._reported:
            App.Console.PrintLog(
                "Nxt: tool strip cannot show a toolbar widget %s\n" % name)
        self._reported.update(unsupported)

    def _resolve(self, key: str) -> source.Entry | None:
        widget = self._live_widget(key)
        if widget is not None:
            return widget
        group = groups.freecad_group(key)
        if group is not None:
            return group
        action = self._stand_ins.action(key)
        return None if action is None else source.Entry(
            Kind.COMMAND, action, None, key)

    def _load_catalog(self) -> None:
        try:
            self._commands, found = catalog.read()
        except Exception:  # noqa: BLE001 - FreeCAD's command list
            log.error("could not read FreeCAD's commands")
            self._commands, found = [], []
        self._filters = [{"id": key, "label": label} for key, label in found]
        self._show_catalog()
        self.drawerChanged.emit()

    def _show_catalog(self) -> None:
        offered = [*(self._commands or []), *self._widget_commands()]
        self._catalog.set_commands(catalog.search(
            offered, self._query, self._filter))
        self._mark_placed()

    def _live_widgets(self) -> list[source.Entry]:
        """FreeCAD's toolbar widgets (a workbench selector, a tray)."""
        return [e for entries in self._live.values() for e in entries
                if e.kind in (Kind.CHOICE, Kind.BUTTON)]

    def _live_widget(self, key: str) -> source.Entry | None:
        return next((e for e in self._live_widgets() if e.key == key), None)

    def _widget_commands(self) -> list[catalog.Command]:
        """The drawer's tiles for FreeCAD's toolbar widgets.

        Not commands: once removed from a strip, only these bring them
        back.
        """
        return [catalog.Command(
            e.key, widget_name(e), "", "", frozenset({catalog.GLOBAL}))
            for e in self._live_widgets()]

    def _keys(self) -> set[str]:
        return set().union(*(m.keys() for m in self._models.values()))

    def _mark_placed(self, *_args: Any) -> None:
        self._catalog.set_placed(self._keys())

    def _changed_areas(self, *_args: Any) -> None:
        self._mark_placed()
        self.areasChanged.emit()

    def _shown(self) -> source.Areas:
        return {area: m.entries() for area, m in self._models.items()}

    def _save(self) -> None:
        workbench = self._workbench()
        layout = layouts.capture(
            self._shown(), self._live,
            layouts.load_for(workbench, self._locked), self._missing)
        layouts.save_for(workbench, layout, self._locked, self._live)

    def stop(self) -> None:
        self._rebuild_timer.stop()
        self._poll_timer.stop()
        for model in self._models.values():
            model.clear()

    # -- QML API -- #

    def _get_model(self) -> QtCore.QObject:
        return self._models[TOP]

    model = QtCore.Property(QtCore.QObject, _get_model, constant=True)

    @QtCore.Slot(str, result=QtCore.QObject)
    def modelOf(self, area: str) -> QtCore.QObject:  # noqa: N802
        return self._m(area)

    @QtCore.Slot(str, result=bool)
    def holds(self, area: str) -> bool:
        """Whether the strip of `area` has anything to show."""
        return self._m(area).rowCount() > 0

    def _get_icon_size(self) -> int:
        return self._icon_size

    iconSize = QtCore.Property(  # noqa: N815 - QML API
        int, _get_icon_size, notify=iconSizeChanged)

    def _get_other_icon_size(self) -> int:
        return self._other_icon_size

    otherIconSize = QtCore.Property(  # noqa: N815 - QML API
        int, _get_other_icon_size, notify=iconSizeChanged)

    def _get_icon_sizes(self) -> list[int]:
        return sorted(set(ICON_SIZES)
                      | {self._icon_size, self._other_icon_size})

    iconSizes = QtCore.Property(  # noqa: N815 - QML API
        list, _get_icon_sizes, notify=iconSizeChanged)

    @QtCore.Slot(int)
    def setIconSize(self, size: int) -> None:  # noqa: N802
        """Draw the first row's icons at `size` pixels, as Nxt's own."""
        settings.put(ICON_SETTING, size)
        self._icon_size = size
        self._catalog.forget_icons()
        self._models[TOP].refresh_all()
        self.iconSizeChanged.emit()

    @QtCore.Slot(int)
    def setOtherIconSize(self, size: int) -> None:  # noqa: N802
        """Draw every other row's icons at `size` pixels, as Nxt's own."""
        settings.put(OTHER_ICON_SETTING, size)
        self._other_icon_size = size
        for model in self._models.values():
            model.refresh_all()
        self.iconSizeChanged.emit()

    def _get_locked(self) -> list[str]:
        return sorted(self._locked)

    lockedUnits = QtCore.Property(  # noqa: N815 - QML API
        list, _get_locked, notify=lockChanged)

    @QtCore.Slot(str, bool)
    def setLocked(self, unit: str, on: bool) -> None:  # noqa: N802
        """Make the first row or a side strip the same in every workbench.

        Locking shares what `unit` holds now; unlocking keeps it as
        this workbench's, while other workbenches go back to theirs.
        """
        if unit not in layouts.LOCKABLE or (unit in self._locked) == on:
            return
        self._locked = self._locked | {unit} if on else self._locked - {unit}
        settings.put(LOCK_SETTING, ",".join(sorted(self._locked)))
        self._save()
        self.lockChanged.emit()

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

    @QtCore.Slot(str, int, str, result=int)
    def insertCommand(self, key: str, at: int,  # noqa: N802
                      area: str = TOP) -> int:
        """Put a command at `at` while it is dragged in; its row, or -1."""
        entry = None if key in self._keys() else self._resolve(key)
        return -1 if entry is None else self._m(area).insert(at, entry)

    @QtCore.Slot(int, str, result=int)
    def insertSeparator(self, at: int,  # noqa: N802
                        area: str = TOP) -> int:
        return self._m(area).insert(at, source.SEPARATOR)

    @QtCore.Slot(int, str, result=int)
    def insertRow(self, at: int, area: str = TOP) -> int:  # noqa: N802
        """End the row before `at`: what follows starts a new one."""
        return self._m(area).insert(at, source.BREAK)

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
        changed = False
        for model in self._models.values():
            empty = [row for row, e in enumerate(model.entries())
                     if groups.is_empty(e)]
            for row in reversed(empty):
                model.remove(row)
            changed |= self._tidy(model) or bool(empty)
        if changed:
            self._save()

    def _tidy(self, model: ToolModel) -> bool:
        """Drop empty rows and stray separators an edit left; any dropped."""
        kept = source.tidy(model.entries())
        if [id(e) for e in kept] == [id(e) for e in model.entries()]:
            return False
        model.set_entries(kept)
        return True

    # -- groups -- #

    def _place_of(self, entry: source.Entry | None) -> tuple[str, int]:
        for area, model in self._models.items():
            for row, shown in enumerate(model.entries()):
                if shown is entry:
                    return area, row
        return TOP, -1

    def _group_at(self, row: int, area: str) -> source.Entry | None:
        entry = self._m(area).entry(row)
        return entry if groups.editable(entry) else None

    def _show_group(self, area: str, row: int, group: source.Entry) -> None:
        """Put the changed `group` at `row`.

        A group left with one member becomes that command only as the
        editor closes, so removing members never moves the editor away.
        """
        if self._edited is self._m(area).entry(row):
            self._edited = group
        self._m(area).replace(row, group)
        self.groupChanged.emit()
        self._save()

    @QtCore.Slot(int, str, result=int)
    def insertGroup(self, at: int, area: str = TOP) -> int:  # noqa: N802
        """A new empty group at `at`, while the New group tile is dragged."""
        return self._m(area).insert(
            at, groups.new(translate("Nxt", "Group")))

    @QtCore.Slot(str, int, str, result=bool)
    def addToGroup(self, key: str, row: int,  # noqa: N802
                   area: str = TOP) -> bool:
        """Put a command from the drawer into the group at `row`."""
        group = self._group_at(row, area)
        member = None if group is None or key in self._keys() \
            else self._resolve(key)
        if group is None or member is None or member.kind is not Kind.COMMAND:
            return False
        self._show_group(area, row, groups.added(group, member))
        return True

    @QtCore.Slot(int, int, str)
    def dropIntoGroup(self, row: int, group_row: int,  # noqa: N802
                      area: str = TOP) -> None:
        """End a drag by moving the strip's command at `row` into a group."""
        self._dragging = False
        model = self._m(area)
        entry, group = model.entry(row), self._group_at(group_row, area)
        if entry is None or group is None or entry.kind is not Kind.COMMAND:
            self._save()
            return
        model.remove(row)
        group_row -= 1 if row < group_row else 0
        self._show_group(area, group_row, groups.added(group, entry))

    @QtCore.Slot(int, str)
    def editGroup(self, row: int, area: str = TOP) -> None:  # noqa: N802
        """Open the group at `row` in the editor row; -1 closes it."""
        group = self._group_at(row, area)
        closing = self._edited
        self._edited = group
        self.groupChanged.emit()
        closed_area, closed_row = self._place_of(closing)
        if closing is not None and closing is not group and closed_row >= 0:
            lone = groups.lone_member(closing)
            if lone is not None:
                self._m(closed_area).replace(closed_row, lone)
                self._save()

    @QtCore.Slot(list)
    def setMemberOrder(self, keys: list[str]) -> None:  # noqa: N802
        """The edited group's members in the order the editor shows."""
        area, row = self._place_of(self._edited)
        if row >= 0 and self._edited is not None:
            self._show_group(area, row,
                             groups.reordered(self._edited, keys))

    @QtCore.Slot(int)
    def removeMember(self, index: int) -> None:  # noqa: N802
        area, row = self._place_of(self._edited)
        if row >= 0 and self._edited is not None:
            self._show_group(area, row, groups.without(self._edited, index))

    @QtCore.Slot(str)
    def renameGroup(self, name: str) -> None:  # noqa: N802
        area, row = self._place_of(self._edited)
        if row >= 0 and self._edited is not None \
                and self._edited.group is not None:
            self._edited.group.name = name.strip()
            self._m(area).refresh(row)
            self._save()

    @QtCore.Slot()
    def ungroup(self) -> None:
        """Put the edited group's commands on the strip in its place."""
        (area, row), group = self._place_of(self._edited), self._edited
        if row < 0 or group is None:
            return
        self._edited = None
        model = self._m(area)
        model.remove(row)
        for offset, member in enumerate(group.members):
            model.insert(row + offset, member)
        self.groupChanged.emit()
        self._save()

    def _get_edited_row(self) -> int:
        return self._place_of(self._edited)[1]

    editedGroup = QtCore.Property(  # noqa: N815 - QML API
        int, _get_edited_row, notify=groupChanged)

    def _get_edited_area(self) -> str:
        return self._place_of(self._edited)[0]

    editedArea = QtCore.Property(  # noqa: N815 - QML API
        str, _get_edited_area, notify=groupChanged)

    def _get_group_name(self) -> str:
        group = None if self._edited is None else self._edited.group
        return "" if group is None else group.name

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

    # -- dragging -- #

    @QtCore.Slot()
    def beginDrag(self) -> None:  # noqa: N802
        self._dragging = True

    @QtCore.Slot()
    def cancelDrag(self) -> None:  # noqa: N802
        """A drag from the drawer let go before reaching a strip."""
        self._dragging = False

    @QtCore.Slot(int, int, str)
    def move(self, row: int, to: int, area: str = TOP) -> None:
        """Move an item while it is dragged; saved when the drag ends."""
        self._m(area).move(row, to)

    @QtCore.Slot(str, int, str, int, result=int)
    def moveAcross(self, from_area: str, row: int,  # noqa: N802
                   to_area: str, at: int) -> int:
        """Move an item to another strip, as it is dropped there; its row."""
        entry = self._m(from_area).entry(row)
        if entry is None or from_area == to_area:
            return -1
        self._m(from_area).remove(row)
        placed = self._m(to_area).insert(at, entry)
        self._tidy(self._m(from_area))
        self._save()
        return placed

    def _new_row_place(self, model: ToolModel, after: int) -> int:
        """Where a new row's first item goes.

        After the row ending at the BREAK at `after`; -1: after the last.
        """
        if after < 0 or model.entry(after) is None:
            if model.rowCount():
                model.insert(-1, source.BREAK)
            return model.rowCount()
        return after + 1

    def _finish_new_row(self, model: ToolModel, row: int) -> None:
        if model.entry(row + 1) is not None:
            model.insert(row + 1, source.BREAK)
        self._tidy(model)
        self._save()

    @QtCore.Slot(int, int, str)
    def moveToNewRow(self, row: int, after: int,  # noqa: N802
                     area: str = TOP) -> None:
        """End a drag by starting a row, after the row ending at `after`."""
        self._dragging = False
        model = self._m(area)
        entry = model.entry(row)
        if entry is None:
            return
        model.remove(row)
        if 0 <= after and row < after:
            after -= 1
        placed = model.insert(self._new_row_place(model, after), entry)
        self._finish_new_row(model, placed)

    @QtCore.Slot(str, int, str, result=bool)
    def addInNewRow(self, key: str, after: int,  # noqa: N802
                    area: str = TOP) -> bool:
        """A drawer item dropped on a new-row zone starts that row."""
        self._dragging = False
        entry = self._drawer_entry(key)
        if entry is None:
            return False
        model = self._m(area)
        placed = model.insert(self._new_row_place(model, after), entry)
        self._finish_new_row(model, placed)
        return True

    def _drawer_entry(self, key: str) -> source.Entry | None:
        if key == SEPARATOR_KEY:
            return source.SEPARATOR
        if key == GROUP_KEY:
            return groups.new(translate("Nxt", "Group"))
        return None if key in self._keys() else self._resolve(key)

    # -- dragging between strips -- #

    def _get_carried_icon(self) -> str:
        return self._carried_look[0]

    carriedIcon = QtCore.Property(  # noqa: N815 - QML API
        str, _get_carried_icon, notify=carriedChanged)

    def _get_carried_text(self) -> str:
        return self._carried_look[1]

    carriedText = QtCore.Property(  # noqa: N815 - QML API
        str, _get_carried_text, notify=carriedChanged)

    @QtCore.Slot(str, int, str, str)
    def carryRow(self, area: str, row: int,  # noqa: N802
                 icon: str = "", text: str = "") -> None:
        """A strip item dragged out of its view, drawn as `icon`, `text`."""
        self._carry((area, row), icon, text)

    @QtCore.Slot(str, str, str)
    def carryKey(self, key: str,  # noqa: N802
                 icon: str = "", text: str = "") -> None:
        """A drawer item dragged out of the drawer's view."""
        self._carry(key, icon, text)

    def _carry(self, carried: tuple[str, int] | str,
               icon: str, text: str) -> None:
        self._carried = carried
        self._carried_look = (icon, text)
        self._dragging = True
        self.carriedChanged.emit()

    @QtCore.Slot(str, float, float)
    def carryTo(self, area: str, x: float, y: float) -> None:  # noqa: N802
        """The carried item is at `x`, `y` in `area`'s view.

        The view it is dragged from keeps the pointer; the strip under it,
        told by carriedOver, shows where it would land.
        """
        found = self._locate(self._to_global(
            area, QtCore.QPoint(round(x), round(y))))
        self._carry_target = found
        target, at = found or ("", QtCore.QPointF())
        self.carriedOver.emit(target, at.x(), at.y())

    @QtCore.Slot()
    def carryEnd(self) -> None:  # noqa: N802
        """Let go of the carried item: the strip under it places it."""
        found, self._carry_target = self._carry_target, None
        self._dragging = False
        self.carriedOver.emit("", 0.0, 0.0)
        if found is None:
            self._carried = None
            return
        target, at = found
        self.carriedDropped.emit(target, at.x(), at.y())

    @QtCore.Slot()
    def removeCarried(self) -> None:  # noqa: N802
        """A strip item carried onto the drawer leaves its strip."""
        carried, self._carried = self._carried, None
        if isinstance(carried, tuple):
            self.removeItem(carried[1], carried[0])

    @QtCore.Slot(str, int, int, result=bool)
    def dropCarried(self, area: str, at: int,  # noqa: N802
                    new_row_after: int = NOT_NEW_ROW) -> bool:
        """Place the carried item in `area`; whether it went.

        At row `at`, or starting a new row after the row ending at
        `new_row_after` (-1: after the last).
        """
        carried, self._carried = self._carried, None
        if carried is None:
            return False
        if isinstance(carried, str):
            if new_row_after != NOT_NEW_ROW:
                return self.addInNewRow(carried, new_row_after, area)
            entry = self._drawer_entry(carried)
            if entry is None:
                return False
            self._m(area).insert(at, entry)
            self._save()
            return True
        from_area, row = carried
        if new_row_after != NOT_NEW_ROW:
            moved = self.moveAcross(from_area, row, area, -1) \
                if from_area != area else row
            if moved < 0:
                return False
            self.moveToNewRow(moved, new_row_after, area)
            return True
        if from_area == area:
            self._m(area).move(row, min(at, self._m(area).rowCount() - 1))
            self._save()
            return True
        return self.moveAcross(from_area, row, area, at) >= 0

    @QtCore.Slot(int, bool, str)
    def endDrag(self, row: int, remove: bool,  # noqa: N802
                area: str = TOP) -> None:
        """Finish a drag at `row`, removing the item if dropped outside."""
        self._dragging = False
        if remove:
            self._m(area).remove(row)
        self._tidy(self._m(area))
        self._save()

    @QtCore.Slot(int, str)
    def removeItem(self, row: int, area: str = TOP) -> None:  # noqa: N802
        if self._m(area).remove(row):
            self._tidy(self._m(area))
            self._save()

    @QtCore.Slot()
    def resetLayout(self) -> None:  # noqa: N802
        """Back to FreeCAD's own toolbars for this workbench."""
        layouts.save(self._workbench(), None)
        self._missing = []
        self.rebuild()

    # -- running -- #

    @QtCore.Slot(int, float, float, str)
    def activate(self, row: int, x: float, y: float,
                 area: str = TOP) -> None:
        """Run the command, or click the button, at `row`.

        (x, y) is below the item in the strip's view: where any menu the
        click opens is placed.
        """
        entry = self._m(area).entry(row)
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
                with menus_opened_at(self._global(x, y, area)):
                    entry.widget.click()
        except Exception:  # noqa: BLE001 - must not reach Qt's event loop
            log.error("tool strip command failed")

    @QtCore.Slot(int, float, float, str)
    def openMenu(self, row: int, x: float, y: float,  # noqa: N802
                 area: str = TOP) -> None:
        """Open the dropdown of `row` at (x, y) in the strip's view."""
        entry = self._m(area).entry(row)
        at = self._global(x, y, area)
        if entry is None:
            return
        if entry.kind is Kind.GROUP:
            self._group_menu(area, entry).popup(at)
        elif entry.kind is Kind.CHOICE:
            self._choice_menu(area, row, entry).popup(at)
        else:
            menu = None if entry.widget is None \
                else getattr(entry.widget, "menu", lambda: None)()
            if menu is not None:
                menu.popup(at)

    @QtCore.Slot(int, float, float, str)
    def openMore(self, row: int, x: float, y: float,  # noqa: N802
                 area: str = TOP) -> None:
        """Press the selector's own + button (workbenches not on tabs)."""
        entry = self._m(area).entry(row)
        more = None if entry is None else models.more_button(entry)
        if more is None:
            return
        menu = more.menu()
        if menu is not None:
            menu.popup(self._global(x, y, area))
            return
        with menus_opened_at(self._global(x, y, area)):
            more.click()

    def _fresh_menu(self) -> QtWidgets.QMenu:
        if self._menu is not None:
            self._menu.deleteLater()
        self._menu = QtWidgets.QMenu(self._main)
        return self._menu

    def _group_menu(self, area: str, group: source.Entry) -> QtWidgets.QMenu:
        """A menu of the group's members; the one picked becomes its face."""
        menu = self._fresh_menu()
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
                self._m(area).refresh(self._place_of(group)[1])

        menu.triggered.connect(picked)
        return menu

    def _choice_menu(self, area: str, row: int,
                     entry: source.Entry) -> QtWidgets.QMenu:
        """The selector's choices as a menu: the combo box style."""
        menu = self._fresh_menu()
        chooser = entry.widget
        for index in range(chooser.count()):
            icon, text = models.choice_at(chooser, index)
            item = menu.addAction(icon, text)
            item.setCheckable(True)
            item.setChecked(index == chooser.currentIndex())
            item.triggered.connect(
                lambda _on=False, i=index: self.choose(row, i, area))
        return menu

    def _global(self, x: float, y: float, area: str) -> QtCore.QPoint:
        return self._to_global(area, QtCore.QPoint(round(x), round(y)))

    @QtCore.Slot(int, int, str)
    def choose(self, row: int, index: int, area: str = TOP) -> None:
        """Pick choice `index` of the selector at `row`."""
        entry = self._m(area).entry(row)
        if entry is None or entry.kind is not Kind.CHOICE:
            return
        chooser = entry.widget
        try:
            chooser.setCurrentIndex(index)
            if isinstance(chooser, QtWidgets.QComboBox):
                chooser.activated.emit(index)
        except Exception:  # noqa: BLE001 - must not reach Qt's event loop
            log.error("tool strip could not switch the selector")
