"""EXPERIMENTAL: the panel drawn inside the 3D view, clicks passing through.

Nxt's own overlay, as an alternative to FreeCAD's (the "OverlayMode"
setting chooses). The panel's QQuickWidget is taken out of its dock and
made a child of the active 3D view's GL widget, see-through and stacked
on top, down the view's left edge.

Clicks reach the model by propagation, not by a mask: a QQuickWidget
marks a mouse or wheel event accepted only if something in the scene
accepted it, and Qt passes an ignored event on to the parent widget -
here, the 3D view. So a press on a row goes to the row, and a press on
the transparent space between and below the rows goes to the model,
with no geometry kept in sync. For that the QML stands aside wherever it
draws nothing (see `host.viewOverlay` in NxtTree.qml and TreeRow.qml).

The dock is hidden while the panel is in the view and gets its widget
back when it leaves.
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..qt import QtCore, QtWidgets

#: The panel's width in the view when the dock had none worth keeping.
DEFAULT_WIDTH = 300


def _alive(obj: Any) -> bool:
    if obj is None:
        return False
    try:
        import shiboken6
        return bool(shiboken6.isValid(obj))
    except ImportError:
        return True


def _area() -> Any:
    main = Gui.getMainWindow()
    return main.findChild(QtWidgets.QMdiArea) if main is not None else None


def active_viewport() -> Any:
    """The GL widget of the active MDI window's 3D view, or None."""
    area = _area()
    sub = area.activeSubWindow() if area is not None else None
    holder = sub.widget() if sub is not None else None
    if holder is None \
            or holder.metaObject().className() != "Gui::View3DInventor":
        return None
    for child in holder.findChildren(QtWidgets.QWidget):
        if "GL" in child.metaObject().className() and child.isVisible():
            return child
    return None


class ViewOverlay(QtCore.QObject):
    """Moves the panel's view into the active 3D view and back."""

    def __init__(self, dock: Any) -> None:
        super().__init__(dock)
        self._dock = dock
        self._host: Any = None
        self._width = DEFAULT_WIDTH
        self._attached = False

    def attached(self) -> bool:
        return self._attached

    def attach(self) -> bool:
        """Into the active 3D view. False if there is none."""
        view = self._dock._view
        host = active_viewport()
        if view is None or host is None:
            return False
        if self._dock.width() > 80:
            self._width = self._dock.width()
        self._attached = True
        self._dock.setWidget(QtWidgets.QWidget())   # the view leaves it
        self._move_to(host)
        self._dock.hide()
        area = _area()
        if area is not None:
            area.subWindowActivated.connect(self._follow)
        return True

    def detach(self) -> None:
        """Back into the dock."""
        if not self._attached:
            return
        self._attached = False
        area = _area()
        if area is not None:
            try:
                area.subWindowActivated.disconnect(self._follow)
            except (RuntimeError, TypeError):
                pass
        if _alive(self._host):
            self._host.removeEventFilter(self)
        self._host = None
        view = self._dock._view
        if view is not None:
            view.setParent(None)
            self._dock.setWidget(view)
            view.show()
        self._dock.show()
        self._dock._release_timer.start()

    # ------------------------------------------------------------------ #

    def _follow(self, *_args: Any) -> None:
        """Another MDI window became active: go with it, if it is 3D."""
        if not self._attached:
            return
        host = active_viewport()
        if host is not None and host is not self._host:
            self._move_to(host)

    def _move_to(self, host: Any) -> None:
        view = self._dock._view
        if _alive(self._host):
            self._host.removeEventFilter(self)
        self._host = host
        view.setParent(host)
        view.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop,
                          True)
        host.installEventFilter(self)
        self._place()
        view.show()
        view.raise_()
        self._dock._release_timer.start()

    def _place(self) -> None:
        view = self._dock._view
        if view is None or not _alive(self._host):
            return
        width = min(self._width, max(120, self._host.width() - 40))
        view.setGeometry(0, 0, width, self._host.height())

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        if watched is self._host \
                and event.type() == QtCore.QEvent.Type.Resize:
            try:
                self._place()
            except Exception as exc:
                App.Console.PrintLog("Nxt view overlay: %s\n" % exc)
        return False
