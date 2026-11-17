"""FreeCAD's toolbars, covered while the tool strip stands in for them.

Each toolbar is squeezed to nothing rather than hidden: FreeCAD still
sees it as shown, so it records nothing in user.cfg and its own
toolbar menu keeps working. Without Nxt, everything is as before.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable
from typing import Any

from ..core.qt import QtCore, QtWidgets

#: Qt's QWIDGETSIZE_MAX: a widget with no maximum size.
UNLIMITED = 16777215

#: Toolbar events after which the strip's contents may differ.
_RESHAPED = frozenset({QtCore.QEvent.Type.Show,
                       QtCore.QEvent.Type.Hide,
                       QtCore.QEvent.Type.ActionAdded,
                       QtCore.QEvent.Type.ActionRemoved})


class ToolbarHider(QtCore.QObject):
    """Covers every toolbar of the main window except Nxt's own."""

    #: A toolbar appeared, was shown or hidden, or changed its actions.
    toolbarsChanged = QtCore.Signal()  # noqa: N815 - Qt API

    def __init__(self, main: QtWidgets.QMainWindow, own: Iterable[str],
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._main = main
        self._own = frozenset(own)
        self._covered: dict[QtWidgets.QToolBar, QtCore.QSize] = {}
        self._sweep_timer = QtCore.QTimer(self)
        self._sweep_timer.setSingleShot(True)
        self._sweep_timer.setInterval(0)
        self._sweep_timer.timeout.connect(self.sweep)

    def install(self) -> None:
        self._main.installEventFilter(self)
        self.sweep()

    def remove(self) -> None:
        self._sweep_timer.stop()
        with contextlib.suppress(RuntimeError):
            self._main.removeEventFilter(self)
        for bar, size in self._covered.items():
            with contextlib.suppress(RuntimeError):     # deleted by FreeCAD
                bar.removeEventFilter(self)
                bar.setMaximumSize(size)
        self._covered.clear()

    def sweep(self) -> None:
        """Cover any toolbar not covered yet, and announce it."""
        new = [bar for bar in self._main.findChildren(QtWidgets.QToolBar)
               if bar.objectName() not in self._own
               and bar not in self._covered]
        for bar in new:
            self._cover(bar)
        if new:
            self.toolbarsChanged.emit()

    def _cover(self, bar: QtWidgets.QToolBar) -> None:
        self._covered[bar] = bar.maximumSize()
        bar.installEventFilter(self)
        bar.setMaximumSize(0, 0)
        bar.destroyed.connect(self._forget)

    def _forget(self, gone: Any) -> None:
        for bar in [b for b in self._covered if b is gone]:
            del self._covered[bar]

    def eventFilter(self, watched: QtCore.QObject,  # noqa: N802
                    event: QtCore.QEvent) -> bool:
        kind = event.type()
        if watched is self._main:
            # Sent from the child's constructor, before it is a QToolBar
            # (and before it is named): look again a turn later.
            if kind == QtCore.QEvent.Type.ChildAdded:
                self._sweep_timer.start()
        elif kind in _RESHAPED:
            self.toolbarsChanged.emit()
        return False
