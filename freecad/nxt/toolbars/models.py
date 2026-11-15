"""The strip's rows: one per entry, described for QML.

A new entry list resets the model only when it differs from the last
(a workbench switch); otherwise each row updates in place when its
action changes, so the view keeps its delegates.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Callable
from typing import Any

from ..core.qt import QtCore, QtWidgets
from . import icons
from .source import Entry, Kind

#: How a command's dropdown opens: by its arrow, or by any click.
SPLIT = "split"
INSTANT = "instant"

ROLES: dict[str, Any] = {
    "kind": "", "text": "", "tip": "", "enabled": True,
    "checkable": False, "checked": False, "icon": "", "dropdown": "",
    "choices": [], "current": -1,
}
_ROLE_IDS = {QtCore.Qt.ItemDataRole.UserRole.value + i: name
             for i, name in enumerate(ROLES)}

_POPUP_MODE = QtWidgets.QToolButton.ToolButtonPopupMode


def plain(text: str) -> str:
    """A label without its mnemonic ampersands."""
    return text.replace("&&", "\0").replace("&", "").replace("\0", "&")


def _dropdown(button: Any) -> str:
    if button is None:
        return ""
    return (SPLIT if button.popupMode() == _POPUP_MODE.MenuButtonPopup
            else INSTANT)


def _command(entry: Entry, size: int) -> dict[str, Any]:
    action = entry.action
    if action is None:
        return {}
    return {"text": plain(action.text()), "tip": action.toolTip(),
            "enabled": action.isEnabled(),
            "checkable": action.isCheckable(),
            "checked": action.isChecked(),
            "icon": icons.url(action.icon(), size),
            "dropdown": _dropdown(entry.widget)}


def _button(entry: Entry, size: int) -> dict[str, Any]:
    button = entry.widget
    has_menu = getattr(button, "menu", lambda: None)() is not None
    return {"text": plain(button.text()), "tip": button.toolTip(),
            "enabled": button.isEnabled(),
            "checkable": button.isCheckable(),
            "checked": button.isChecked(),
            "icon": icons.url(button.icon(), size),
            "dropdown": INSTANT if has_menu else ""}


def _choice(entry: Entry, size: int) -> dict[str, Any]:
    chooser = entry.widget
    if isinstance(chooser, QtWidgets.QTabBar):
        count, text, icon = (chooser.count(), chooser.tabText,
                             chooser.tabIcon)
    else:
        count, text, icon = (chooser.count(), chooser.itemText,
                             chooser.itemIcon)
    return {"enabled": chooser.isEnabled(),
            "choices": [{"text": plain(text(i)),
                         "icon": icons.url(icon(i), size)}
                        for i in range(count)],
            "current": chooser.currentIndex()}


_DESCRIBE: dict[Kind, Callable[[Entry, int], dict[str, Any]]] = {
    Kind.COMMAND: _command, Kind.BUTTON: _button, Kind.CHOICE: _choice,
}


def describe(entry: Entry, icon_size: int) -> dict[str, Any]:
    """Every role's value for `entry`."""
    row = dict(ROLES, kind=entry.kind.value)
    if entry.kind in _DESCRIBE:
        row.update(_DESCRIBE[entry.kind](entry, icon_size))
    return row


def _signature(entries: list[Entry]) -> list[tuple[Kind, int, int]]:
    return [(e.kind, id(e.action), id(e.widget)) for e in entries]


class ToolModel(QtCore.QAbstractListModel):
    """The strip's entries as a flat list model."""

    def __init__(self, icon_size: Callable[[], int],
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._icon_size = icon_size
        self._entries: list[Entry] = []
        self._rows: list[dict[str, Any]] = []
        self._watched: list[tuple[Any, Callable[..., None]]] = []

    def entry(self, row: int) -> Entry | None:
        return self._entries[row] if 0 <= row < len(self._entries) else None

    def entries(self) -> list[Entry]:
        return list(self._entries)

    def has(self, kind: Kind) -> bool:
        return any(e.kind is kind for e in self._entries)

    def set_entries(self, entries: list[Entry]) -> None:
        """Show `entries`; a reset only if they are not the ones shown."""
        if _signature(entries) == _signature(self._entries):
            self.refresh_all()
            return
        self._unwatch()
        self.beginResetModel()
        self._entries = list(entries)
        size = self._icon_size()
        self._rows = [describe(e, size) for e in self._entries]
        self.endResetModel()
        self._watch()

    def move(self, row: int, to: int) -> bool:
        """Move row `row` to index `to`, as a drag passes over items."""
        count = len(self._entries)
        if row == to or not (0 <= row < count and 0 <= to < count):
            return False
        # Qt's destination counts the row being moved while it is above.
        self.beginMoveRows(QtCore.QModelIndex(), row, row,
                           QtCore.QModelIndex(), to + 1 if to > row else to)
        self._entries.insert(to, self._entries.pop(row))
        self._rows.insert(to, self._rows.pop(row))
        self.endMoveRows()
        return True

    def remove(self, row: int) -> bool:
        if self.entry(row) is None:
            return False
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        del self._entries[row], self._rows[row]
        self.endRemoveRows()
        return True

    def refresh(self, row: int, *_args: Any) -> None:
        """Announce row `row` if what it shows has changed."""
        entry = self.entry(row)
        if entry is None:
            return
        fresh = describe(entry, self._icon_size())
        if fresh == self._rows[row]:
            return
        self._rows[row] = fresh
        index = self.index(row)
        self.dataChanged.emit(index, index)

    def refresh_all(self, kind: Kind | None = None) -> None:
        for row, entry in enumerate(self._entries):
            if kind is None or entry.kind is kind:
                self.refresh(row)

    def _refresh_entry(self, entry: Entry, *_args: Any) -> None:
        # By identity: rows move while editing; a removed entry is gone.
        for row, shown in enumerate(self._entries):
            if shown is entry:
                self.refresh(row)
                return

    def _watch(self) -> None:
        for entry in self._entries:
            slot = functools.partial(self._refresh_entry, entry)
            if entry.kind is Kind.COMMAND and entry.action is not None:
                signal = entry.action.changed
            elif entry.kind is Kind.CHOICE:
                signal = entry.widget.currentIndexChanged \
                    if isinstance(entry.widget, QtWidgets.QComboBox) \
                    else entry.widget.currentChanged
            else:
                continue
            signal.connect(slot)
            self._watched.append((signal, slot))

    def _unwatch(self) -> None:
        for signal, slot in self._watched:
            with contextlib.suppress(RuntimeError, TypeError):
                signal.disconnect(slot)
        self._watched = []

    def clear(self) -> None:
        self.set_entries([])

    # -- QAbstractListModel -- #

    def rowCount(self, parent: Any = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() \
            else len(self._rows)

    def data(self, index: Any, role: int = 0) -> Any:
        name = _ROLE_IDS.get(role)
        if name is None or not index.isValid():
            return None
        return self._rows[index.row()][name]

    def roleNames(self) -> dict[int, QtCore.QByteArray]:  # noqa: N802
        return {role: QtCore.QByteArray(name.encode())
                for role, name in _ROLE_IDS.items()}
