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


#: The most of the window's height the top strip may take: a first layout
#: at a sliver of its width (FreeCAD 1.1 lays toolbars out before the
#: window has its size) wraps every item onto its own row, and a strip
#: fixed at that height was never widened again.
MOST_OF_WINDOW = 1 / 3
#: While the toolbars are edited: the drawer pushes the 3D view down,
#: rather than the rows' growth pushing it out of view (overloaded
#: workbenches fill many rows), but never past the window.
EDITING_SHARE = 0.85


#: The least share of the window's width the top strip takes when docked
#: as it should be; narrower, FreeCAD's restored layout squeezed it.
LEAST_OF_WIDTH = 1 / 2
#: How long after FreeCAD rearranges its toolbars (a restored layout, a
#: workbench change) the strips' docking is checked.
DOCK_CHECK_MS = 100


def squeezed(strip_width: int, window_width: int) -> bool:
    """Whether the top strip is narrower than its line would make it."""
    return strip_width < window_width * LEAST_OF_WIDTH


def fitted_height(wanted: float, window_height: int,
                  share: float = MOST_OF_WINDOW) -> int:
    """The top strip's height: what QML wants, within a `share` of the window.

    MOST_OF_WINDOW normally, EDITING_SHARE in edit mode.
    """
    return min(math.ceil(wanted), max(1, int(window_height * share)))


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
        self._main = main
        self._bridge = bridge
        self._dock = dock
        self._place()
        self.toolbar.installEventFilter(self)
        # A new width lays QML out again: fit to what it then wants.
        self.view.installEventFilter(self)
        self.toolbar.setVisible(self.wanted)

    def _place(self) -> None:
        # A line of its own: sharing one, it was given only a sliver.
        if self.area == state.TOP:
            self._main.addToolBarBreak(self._dock)
        self._main.addToolBar(self._dock, self.toolbar)

    def check_dock(self) -> None:
        """Dock again where FreeCAD's restored layout moved or squeezed it.

        FreeCAD 1.1 restores its saved toolbar layout after the strips
        are placed; the top strip then sat in a sliver of its line.
        """
        if not self.wanted or not self._main.isVisible():
            return
        moved = self._main.toolBarArea(self.toolbar) != self._dock
        if not moved and not (self.area == state.TOP and squeezed(
                self.toolbar.width(), self._main.width())):
            return
        _drop(self._main, self.toolbar)
        self._place()
        self.toolbar.setVisible(True)
        self._fit_timer.start()

    def _fit(self) -> None:
        root = self.view.rootObject()
        if self.area == state.TOP:
            editing = bool(self._bridge.property("editing"))
            self.view.setFixedHeight(fitted_height(
                root.property("implicitHeight") or 0, self._main.height(),
                EDITING_SHARE if editing else MOST_OF_WINDOW))
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
        kind = event.type()
        if watched is self.toolbar and kind == QtCore.QEvent.Type.Hide:
            self._reshow_timer.start()
        elif watched is self.view and kind == QtCore.QEvent.Type.Resize:
            self._fit_timer.start()
        return False

    def remove(self, main: Any) -> None:
        self._fit_timer.stop()
        self._reshow_timer.stop()
        self.toolbar.removeEventFilter(self)
        self.view.removeEventFilter(self)
        _drop(main, self.toolbar)
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
        self._dock_timer = QtCore.QTimer(self)
        self._dock_timer.setSingleShot(True)
        self._dock_timer.setInterval(DOCK_CHECK_MS)
        self._dock_timer.timeout.connect(self._check_docks)

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
        self._hider.toolbarsChanged.connect(self._dock_timer.start)
        self._hider.install()
        main.workbenchActivated.connect(self.bridge.schedule)
        main.workbenchActivated.connect(self._dock_timer.start)
        # At startup the window shows after FreeCAD restores its layout.
        main.installEventFilter(self)
        self.bridge.rebuild()
        self._dock_timer.start()

    def eventFilter(self, watched: QtCore.QObject,  # noqa: N802
                    event: QtCore.QEvent) -> bool:
        if watched is self._main and event.type() == QtCore.QEvent.Type.Show:
            self._dock_timer.start()
        return False

    def _check_docks(self) -> None:
        for host in self._hosts.values():
            host.check_dock()

    def _show_sides(self) -> None:
        if self.bridge is None:
            return
        editing = bool(self.bridge.property("editing"))
        for area in (state.LEFT, state.RIGHT):
            self._hosts[area].want(editing or self.bridge.holds(area))

    def remove(self) -> None:
        main = self._main
        self._dock_timer.stop()
        if main is not None:
            main.removeEventFilter(self)
        if self.bridge is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                main.workbenchActivated.disconnect(self.bridge.schedule)
            with contextlib.suppress(RuntimeError, TypeError):
                main.workbenchActivated.disconnect(self._dock_timer.start)
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
            _drop(main, old)
            old.deleteLater()


def _drop(main: QtWidgets.QMainWindow, toolbar: QtWidgets.QToolBar) -> None:
    """Take `toolbar` out of the window, with the line break before it."""
    if main.toolBarBreak(toolbar):
        main.removeToolBarBreak(toolbar)
    main.removeToolBar(toolbar)
