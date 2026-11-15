"""The tool strip in the main window: its toolbar, view and covers.

One Nxt toolbar, fixed in place, holds the QML strip; every other
toolbar is covered by the hider. FreeCAD hides toolbars it does not
list as workbenches switch, so the strip's own is shown again.
"""

from __future__ import annotations

import contextlib
import math
from typing import Any

import FreeCADGui as Gui

from ..app.i18n import translate
from ..core.qt import QtCore, QtGui, QtWidgets
from ..ui import quick_host
from . import layouts
from .bridge import ToolStripBridge
from .hider import ToolbarHider

TOOLBAR = "NxtToolStrip"
QML = "Nxt/Toolbar/ToolStrip.qml"
#: Toolbars that are the strip's own and never covered.
OWN = (TOOLBAR,)


def _see_through(view: Any) -> None:
    view.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop)
    view.setClearColor(QtGui.QColor(0, 0, 0, 0))


class ToolStrip(QtCore.QObject):
    """Nxt's QML toolbar standing in for all of FreeCAD's."""

    def __init__(self, theme: Any,
                 parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        #: FreeCAD's main window, with its workbenchActivated signal.
        self._main: Any = None
        self._toolbar: QtWidgets.QToolBar | None = None
        self._view: Any = None
        self._hider: ToolbarHider | None = None
        self.bridge: ToolStripBridge | None = None
        self._reshow_timer = QtCore.QTimer(self)
        self._reshow_timer.setSingleShot(True)
        self._reshow_timer.setInterval(0)
        self._reshow_timer.timeout.connect(self._reshow)
        # implicitHeight changes while QML lays out a frame; resizing the
        # view inside that frame starts another and both are dropped
        # ("beginFrame() must be followed by ... endFrame()"): blank strip.
        self._fit_timer = QtCore.QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(0)
        self._fit_timer.timeout.connect(self._fit)

    def install(self) -> None:
        main = Gui.getMainWindow()
        self._main = main
        _remove_left_over(main)
        toolbar = QtWidgets.QToolBar(translate("Nxt", "Tool strip"), main)
        toolbar.setObjectName(TOOLBAR)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        # Off the toolbars' own menu: hiding it would leave no toolbar.
        toolbar.toggleViewAction().setVisible(False)
        self._toolbar = toolbar
        self.bridge = ToolStripBridge(main, OWN, self._to_global,
                                      _layout_name, self)
        self._view = quick_host.make_view(
            toolbar, QML, {"theme": self._theme, "strip": self.bridge},
            prepare=_see_through)
        self._view.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                 QtWidgets.QSizePolicy.Policy.Fixed)
        root = self._view.rootObject()
        root.implicitHeightChanged.connect(self._fit_timer.start)
        self._fit_timer.start()
        toolbar.addWidget(self._view)
        main.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, toolbar)
        toolbar.installEventFilter(self)
        self._hider = ToolbarHider(main, OWN, self)
        self._hider.toolbarsChanged.connect(self.bridge.schedule)
        self._hider.install()
        main.workbenchActivated.connect(self.bridge.schedule)
        self.bridge.rebuild()

    def remove(self) -> None:
        self._reshow_timer.stop()
        self._fit_timer.stop()
        main = self._main
        if self.bridge is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                main.workbenchActivated.disconnect(self.bridge.schedule)
            self.bridge.stop()
        if self._hider is not None:
            self._hider.remove()
            self._hider = None
        if self._toolbar is not None:
            self._toolbar.removeEventFilter(self)
            main.removeToolBar(self._toolbar)
            # The view goes with its toolbar; its context is never nulled.
            self._toolbar.deleteLater()
            self._toolbar = self._view = None
        self.bridge = None

    def _fit(self) -> None:
        if self._view is None:
            return
        height = self._view.rootObject().property("implicitHeight")
        self._view.setFixedHeight(math.ceil(height or 0))

    def _to_global(self, point: QtCore.QPoint) -> QtCore.QPoint:
        return self._view.mapToGlobal(point)

    def _reshow(self) -> None:
        if self._toolbar is not None and self._toolbar.isHidden():
            self._toolbar.show()

    def eventFilter(self, watched: QtCore.QObject,  # noqa: N802
                    event: QtCore.QEvent) -> bool:
        if watched is self._toolbar \
                and event.type() == QtCore.QEvent.Type.Hide:
            self._reshow_timer.start()
        return False


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
    """Drop a strip left by a reload of Nxt."""
    old = main.findChild(QtWidgets.QToolBar, TOOLBAR)
    if old is not None:
        main.removeToolBar(old)
        old.deleteLater()
