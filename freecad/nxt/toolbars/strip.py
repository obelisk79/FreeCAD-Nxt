"""The tool strips in the main window: their toolbars, views and covers.

One Nxt toolbar per area (top, left, right), fixed in place, holds a QML
strip; every other toolbar is covered by the hider. A side strip shows
only while it holds something, or in edit mode, to be dropped on.
FreeCAD hides toolbars it does not list as workbenches switch, so the
strips' own are shown again.
"""

from __future__ import annotations

import contextlib
import math
from typing import Any

import FreeCADGui as Gui

from ..app.i18n import translate
from ..core.qt import QtCore, QtGui, QtWidgets
from ..ui import quick_host
from . import layouts, state
from .bridge import ToolStripBridge
from .hider import ToolbarHider

TOOLBAR = "NxtToolStrip"
QML = "Nxt/Toolbar/ToolStrip.qml"
_AREA = QtCore.Qt.ToolBarArea
#: Each strip's toolbar name and where it docks.
PLACES = {state.TOP: (TOOLBAR, _AREA.TopToolBarArea),
          state.LEFT: (TOOLBAR + "Left", _AREA.LeftToolBarArea),
          state.RIGHT: (TOOLBAR + "Right", _AREA.RightToolBarArea)}
#: Toolbars that are the strips' own and never covered.
OWN = tuple(name for name, _dock in PLACES.values())


def _see_through(view: Any) -> None:
    view.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop)
    view.setClearColor(QtGui.QColor(0, 0, 0, 0))


class _Host(QtCore.QObject):
    """One area's toolbar and QML view."""

    def __init__(self, main: Any, area: str, theme: Any,
                 bridge: ToolStripBridge,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.area = area
        self.wanted = area == state.TOP
        name, dock = PLACES[area]
        self.toolbar = QtWidgets.QToolBar(translate("Nxt", "Tool strip"),
                                          main)
        self.toolbar.setObjectName(name)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        # Off the toolbars' own menu: hiding it would leave no toolbar.
        self.toolbar.toggleViewAction().setVisible(False)
        self.view = quick_host.make_view(
            self.toolbar, QML,
            {"theme": theme, "strip": bridge, "area": area},
            prepare=_see_through)
        # A QWidget refuses system drops unless told: items dragged here
        # from another strip got the "no" cursor.
        self.view.setAcceptDrops(True)
        across = area == state.TOP
        policy = QtWidgets.QSizePolicy.Policy
        self.view.setSizePolicy(
            policy.Expanding if across else policy.Fixed,
            policy.Fixed if across else policy.Expanding)
        # implicitHeight changes while QML lays out a frame; resizing the
        # view inside that frame starts another and both are dropped
        # ("beginFrame() must be followed by ... endFrame()"): blank strip.
        self._fit_timer = _zero_timer(self, self._fit)
        self._reshow_timer = _zero_timer(self, self._reshow)
        root = self.view.rootObject()
        (root.implicitHeightChanged if across
         else root.implicitWidthChanged).connect(self._fit_timer.start)
        self._fit_timer.start()
        self.toolbar.addWidget(self.view)
        main.addToolBar(dock, self.toolbar)
        self.toolbar.installEventFilter(self)
        self.toolbar.setVisible(self.wanted)

    def _fit(self) -> None:
        root = self.view.rootObject()
        if self.area == state.TOP:
            self.view.setFixedHeight(
                math.ceil(root.property("implicitHeight") or 0))
        else:
            self.view.setFixedWidth(
                math.ceil(root.property("implicitWidth") or 0))

    def want(self, shown: bool) -> None:
        self.wanted = shown
        self.toolbar.setVisible(shown)

    def _reshow(self) -> None:
        if self.wanted and self.toolbar.isHidden():
            self.toolbar.show()

    def eventFilter(self, watched: QtCore.QObject,  # noqa: N802
                    event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.Hide:
            self._reshow_timer.start()
        return False

    def remove(self, main: Any) -> None:
        self._fit_timer.stop()
        self._reshow_timer.stop()
        self.toolbar.removeEventFilter(self)
        main.removeToolBar(self.toolbar)
        # The view goes with its toolbar; its context is never nulled.
        self.toolbar.deleteLater()


def _zero_timer(owner: QtCore.QObject, slot: Any) -> QtCore.QTimer:
    timer = QtCore.QTimer(owner)
    timer.setSingleShot(True)
    timer.setInterval(0)
    timer.timeout.connect(slot)
    return timer


class ToolStrip(QtCore.QObject):
    """Nxt's QML toolbars standing in for all of FreeCAD's."""

    def __init__(self, theme: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        #: FreeCAD's main window, with its workbenchActivated signal.
        self._main: Any = None
        self._hosts: dict[str, _Host] = {}
        self._hider: ToolbarHider | None = None
        self.bridge: ToolStripBridge | None = None

    def install(self) -> None:
        main = Gui.getMainWindow()
        self._main = main
        _remove_left_over(main)
        self.bridge = ToolStripBridge(main, OWN, self._to_global,
                                      _layout_name, self,
                                      locate=self._locate)
        for area in state.AREAS:
            self._hosts[area] = _Host(main, area, self._theme, self.bridge,
                                      self)
        self.bridge.areasChanged.connect(self._show_sides)
        self.bridge.editingChanged.connect(self._show_sides)
        self._hider = ToolbarHider(main, OWN, self)
        self._hider.toolbarsChanged.connect(self.bridge.schedule)
        self._hider.install()
        main.workbenchActivated.connect(self.bridge.schedule)
        self.bridge.rebuild()

    def _show_sides(self) -> None:
        if self.bridge is None:
            return
        editing = bool(self.bridge.property("editing"))
        for area in (state.LEFT, state.RIGHT):
            self._hosts[area].want(editing or self.bridge.holds(area))

    def remove(self) -> None:
        main = self._main
        if self.bridge is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                main.workbenchActivated.disconnect(self.bridge.schedule)
            self.bridge.stop()
        if self._hider is not None:
            self._hider.remove()
            self._hider = None
        for host in self._hosts.values():
            host.remove(main)
        self._hosts.clear()
        self.bridge = None

    def _to_global(self, area: str, point: QtCore.QPoint) -> QtCore.QPoint:
        host = self._hosts.get(area) or self._hosts[state.TOP]
        return host.view.mapToGlobal(point)

    def _locate(self, point: QtCore.QPoint
                ) -> tuple[str, QtCore.QPointF] | None:
        """The shown strip at screen `point`, and where in its view."""
        for area, host in self._hosts.items():
            if not host.view.isVisible():
                continue
            local = host.view.mapFromGlobal(point)
            if host.view.rect().contains(local):
                return area, QtCore.QPointF(local)
        return None


SKETCH = "Sketcher::SketchObject"


def _layout_name() -> str:
    """The workbench's name, or the sketch-edit layout's while editing one."""
    document = Gui.ActiveDocument
    in_edit = document.getInEdit() if document is not None else None
    edited = getattr(in_edit, "Object", None)
    if getattr(edited, "TypeId", "") == SKETCH:
        return layouts.SKETCH_EDIT
    workbench = Gui.activeWorkbench()
    return workbench.name() if workbench is not None else ""


def _remove_left_over(main: QtWidgets.QMainWindow) -> None:
    """Drop strips left by a reload of Nxt."""
    for name in OWN:
        old = main.findChild(QtWidgets.QToolBar, name)
        if old is not None:
            main.removeToolBar(old)
            old.deleteLater()
