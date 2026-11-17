"""What FreeCAD's toolbars hold, as rows of entries in each area.

Toolbars of earlier workbenches linger as hidden children of the main
window: only those FreeCAD has not hidden count. Rows follow FreeCAD's
own (state.py); each toolbar boundary within a row becomes a separator.
Read straight from Qt, so the strips show exactly what FreeCAD would,
addons and workbench manipulators included.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ..core.qt import QtCore, QtGui, QtWidgets
from . import state

#: Toolbar areas in the order the strip reads them.
_AREA_ORDER = (QtCore.Qt.ToolBarArea.TopToolBarArea,
               QtCore.Qt.ToolBarArea.LeftToolBarArea,
               QtCore.Qt.ToolBarArea.RightToolBarArea,
               QtCore.Qt.ToolBarArea.BottomToolBarArea)


class Kind(enum.Enum):
    """What an entry is drawn as."""

    COMMAND = "command"
    SEPARATOR = "separator"
    #: A push or tool button FreeCAD placed as a widget (BIM, Draft Tray).
    BUTTON = "button"
    #: A tab bar or combo box of choices (the workbench selector).
    CHOICE = "choice"
    #: Several commands behind one button: the user's, or FreeCAD's own
    #: group added from the drawer.
    GROUP = "group"
    #: The end of a row: what follows starts the next.
    BREAK = "break"


@dataclass(eq=False)
class GroupState:
    """What changes about a group: its name, members and last one used."""

    name: str
    #: Every member's key in order, found or not (workbench not loaded).
    keys: list[str]
    #: Index into the found members of the one the button runs.
    last: int = 0
    #: False for FreeCAD's own groups, which FreeCAD defines.
    editable: bool = True


@dataclass(frozen=True, eq=False)
class Entry:
    """One item of the strip and the Qt object it stands for."""

    kind: Kind
    action: QtGui.QAction | None = None
    #: The proxied button, tab bar or combo box, or a command's dropdown.
    widget: Any = None
    #: Names it in a saved layout: the command's name, or for a widget
    #: its toolbar and place there ("Draft tray#2").
    key: str = ""
    #: A group's commands that are found, in order.
    members: tuple[Entry, ...] = ()
    group: GroupState | None = None


SEPARATOR = Entry(Kind.SEPARATOR)
BREAK = Entry(Kind.BREAK)

#: Entries of each area (state.AREAS), rows split by BREAK.
Areas = dict[str, list[Entry]]


def shown_toolbars(main: QtWidgets.QMainWindow,
                   own: Iterable[str]) -> list[QtWidgets.QToolBar]:
    """The toolbars FreeCAD shows now, in reading order, less `own`."""
    skip = frozenset(own)
    bars = [bar for bar in main.findChildren(QtWidgets.QToolBar)
            if bar.objectName() not in skip and not bar.isHidden()]

    def place(bar: QtWidgets.QToolBar) -> tuple[int, int, int]:
        area = main.toolBarArea(bar)
        rank = (_AREA_ORDER.index(area) if area in _AREA_ORDER
                else len(_AREA_ORDER))
        return rank, bar.y(), bar.x()

    # Stable: covered toolbars share a position, so creation order decides.
    return sorted(bars, key=place)


def _choices_in(widget: QtWidgets.QWidget) -> Any:
    """The tab bar or combo box a selector widget offers, or None."""
    if isinstance(widget, (QtWidgets.QTabBar, QtWidgets.QComboBox)):
        return widget
    return (widget.findChild(QtWidgets.QTabBar)
            or widget.findChild(QtWidgets.QComboBox))


def entry_for(bar: QtWidgets.QToolBar, action: QtGui.QAction,
              place: int = 0) -> Entry | None:
    """The strip's entry for one toolbar action, or None if unsupported.

    `place` is the action's position in its toolbar, naming a widget.
    """
    if action.isSeparator():
        return SEPARATOR
    widget = bar.widgetForAction(action)
    if not isinstance(action, QtWidgets.QWidgetAction):
        dropdown = (widget if isinstance(widget, QtWidgets.QToolButton)
                    and widget.menu() is not None else None)
        return Entry(Kind.COMMAND, action, dropdown,
                     action.objectName() or action.text())
    key = "%s#%d" % (bar.objectName(), place)
    if isinstance(widget, QtWidgets.QAbstractButton):
        return Entry(Kind.BUTTON, action, widget, key)
    choices = _choices_in(widget) if widget is not None else None
    if choices is not None:
        return Entry(Kind.CHOICE, action, choices, key)
    return None


_DIVIDERS = (Kind.SEPARATOR, Kind.BREAK)


def tidy(entries: list[Entry]) -> list[Entry]:
    """Without empty rows, or separators at a row's ends or repeated."""
    tidied: list[Entry] = []
    for entry in entries:
        if entry.kind in _DIVIDERS:
            if not tidied or tidied[-1].kind is Kind.BREAK:
                continue
            if tidied[-1].kind is Kind.SEPARATOR:
                if entry.kind is Kind.SEPARATOR:
                    continue
                tidied.pop()
        tidied.append(entry)
    while tidied and tidied[-1].kind in _DIVIDERS:
        tidied.pop()
    return tidied


def rows_of(entries: list[Entry]) -> list[list[Entry]]:
    """`entries` split at each BREAK."""
    rows: list[list[Entry]] = [[]]
    for entry in entries:
        if entry.kind is Kind.BREAK:
            rows.append([])
        else:
            rows[-1].append(entry)
    return rows


def toolbar_rows(main: QtWidgets.QMainWindow, own: Iterable[str]
                 ) -> dict[str, list[list[QtWidgets.QToolBar]]]:
    """The shown toolbars in FreeCAD's rows, by area.

    Toolbars Qt's record does not place (added since) join the last row
    of the top, in screen order.
    """
    shown = shown_toolbars(main, own)
    by_name = {bar.objectName(): bar for bar in shown}
    areas: dict[str, list[list[QtWidgets.QToolBar]]] = {
        area: [] for area in state.AREAS}
    placed: set[str] = set()
    for area, names in state.rows(bytes(main.saveState().data())) or []:
        row = [by_name[n] for n in names if n in by_name and n not in placed]
        placed.update(bar.objectName() for bar in row)
        if row:
            areas[area].append(row)
    rest = [bar for bar in shown if bar.objectName() not in placed]
    if rest:
        if areas[state.TOP]:
            areas[state.TOP][-1].extend(rest)
        else:
            areas[state.TOP].append(rest)
    return areas


def read(main: QtWidgets.QMainWindow, own: Iterable[str]
         ) -> tuple[Areas, list[str]]:
    """Each area's entries, and class names of widgets that cannot show."""
    unsupported: list[str] = []
    areas: Areas = {}
    for area, rows in toolbar_rows(main, own).items():
        entries: list[Entry] = []
        for row in rows:
            entries.append(BREAK)
            for bar in row:
                entries.append(SEPARATOR)
                entries += _entries_of(bar, unsupported)
        areas[area] = tidy(entries)
    return areas, unsupported


def _entries_of(bar: QtWidgets.QToolBar,
                unsupported: list[str]) -> list[Entry]:
    entries: list[Entry] = []
    for place, action in enumerate(bar.actions()):
        if not action.isVisible():
            continue
        entry = entry_for(bar, action, place)
        if entry is None:
            widget = bar.widgetForAction(action)
            unsupported.append(widget.metaObject().className()
                               if widget is not None else "?")
        else:
            entries.append(entry)
    return entries
