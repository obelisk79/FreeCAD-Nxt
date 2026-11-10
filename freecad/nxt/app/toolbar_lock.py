"""FreeCAD's "Lock toolbars" (View > Toolbars), kept on Nxt's toolbars.

FreeCAD applies it only to the toolbars it made itself.
"""

from __future__ import annotations

import weakref
from typing import Any

import FreeCAD as App

from ..core.qt import QtWidgets

GROUP = "User parameter:BaseApp/Preferences/General"
KEY = "LockToolBars"

_followed: weakref.WeakSet[QtWidgets.QToolBar] = weakref.WeakSet()


def locked() -> bool:
    return bool(App.ParamGet(GROUP).GetBool(KEY, False))


def _apply() -> None:
    movable = not locked()
    for toolbar in list(_followed):
        toolbar.setMovable(movable)


class _Observer:
    def onChange(self, _group: Any, key: str) -> None:  # noqa: N802
        if key == KEY:
            _apply()


_observer: _Observer | None = None
#: Held: the observer is detached when the group's handle is collected.
_group: Any = None


def follow(toolbar: QtWidgets.QToolBar) -> None:
    """Keep `toolbar` locked while FreeCAD's toolbars are."""
    global _observer, _group
    _followed.add(toolbar)
    toolbar.setMovable(not locked())
    if _observer is None:
        _observer = _Observer()
        _group = App.ParamGet(GROUP)
        _group.Attach(_observer)


def remove() -> None:
    global _observer, _group
    if _observer is not None:
        _group.Detach(_observer)
        _observer = _group = None
    _followed.clear()
