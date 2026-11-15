"""What FreeCAD's toolbars hold, flattened into one row of entries.

Toolbars of earlier workbenches linger as hidden children of the main
window: only those FreeCAD has not hidden count. Each toolbar boundary
becomes a separator. Read straight from Qt, so the strip shows exactly
what FreeCAD would, addons and workbench manipulators included.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ..core.qt import QtCore, QtGui, QtWidgets

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


def tidy(entries: list[Entry]) -> list[Entry]:
    """Without leading, trailing or repeated separators."""
    tidied: list[Entry] = []
    for entry in entries:
        if entry.kind is Kind.SEPARATOR and (
                not tidied or tidied[-1].kind is Kind.SEPARATOR):
            continue
        tidied.append(entry)
    if tidied and tidied[-1].kind is Kind.SEPARATOR:
        tidied.pop()
    return tidied


def read(main: QtWidgets.QMainWindow, own: Iterable[str]
         ) -> tuple[list[Entry], list[str]]:
    """The strip's entries, and the class names of widgets it cannot show."""
    entries: list[Entry] = []
    unsupported: list[str] = []
    for bar in shown_toolbars(main, own):
        entries.append(SEPARATOR)
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
    return tidy(entries), unsupported
