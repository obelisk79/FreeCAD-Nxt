"""EXPERIMENTAL: the panel drawn inside the 3D view, clicks passing through.

Nxt's own overlay, as an alternative to FreeCAD's (the "OverlayMode"
setting chooses). The panel's QQuickWidget is taken out of its dock and
made a child of the active 3D view's GL widget, see-through and stacked
on top, down the view's left edge.

Clicks reach the model without a mask. Every press on the panel is
first put to the QML - does it draw anything there (NxtTree.qml
`wantsPoint`)? If so the panel gets it, and it goes no further; if not,
the press is handed to the 3D view, with the moves and release that
follow it. Wheel events and hover still pass by plain propagation: the
panel's scene leaves them unaccepted where it draws nothing (see
`host.viewOverlay` in NxtTree.qml and TreeRow.qml).

Whether the scene accepted a press was the first test, and it is not a
safe one: a tap handler - the chips', the eye's - takes part in a press
without accepting it, so the press went on to the model and the tap was
lost.

A handed-on press needs its moves and release handed on too: Qt sends
them to the widget that first received the press - the panel's - so
until the button comes up they are passed straight on to the 3D view.

The dock is hidden while the panel is in the view and gets its widget
back when it leaves.
"""

from __future__ import annotations

from typing import Any

import FreeCAD as App
import FreeCADGui as Gui

from ..qt import QtCore, QtGui, QtWidgets
from ..qtquick import modules as _quick_modules

#: The panel's width in the view when the dock had none worth keeping.
DEFAULT_WIDTH = 300

_PRESSES = (QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.MouseButtonDblClick)
_FOLLOWERS = (QtCore.QEvent.Type.MouseMove,
              QtCore.QEvent.Type.MouseButtonRelease)
#: What a 3D view window does on its way to being destroyed.
_GOING = (QtCore.QEvent.Type.Close, QtCore.QEvent.Type.DeferredDelete,
          QtCore.QEvent.Type.Hide)


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
        #: A press the panel passed on is in progress: its moves and its
        #: release go to the 3D view too.
        self._passing = False
        #: A press the panel kept is in progress: its moves and release
        #: stay with the panel, whether or not anything accepts them.
        self._owning = False
        #: The 3D view window (View3DInventor) around `_host`, watched for
        #: closing; and whether the panel is parked out of every view.
        self._holder: Any = None
        self._parked = False
        self._retrying = False
        #: Where the panel waits while no 3D view is showing: a widget
        #: hidden explicitly, so it stays hidden - with the panel in it -
        #: even when a workbench switch shows the dock it belongs to.
        self._shelf = QtWidgets.QWidget(dock)
        self._shelf.hide()

    def attached(self) -> bool:
        return self._attached

    def attach(self) -> bool:
        """Into the active 3D view, or out of sight until there is one."""
        view = self._dock._view
        if not _alive(view):
            return False
        if self._dock.width() > 80:
            self._width = self._dock.width()
        self._attached = True
        self._dock.setWidget(QtWidgets.QWidget())   # the view leaves it
        host = active_viewport()
        if host is not None:
            self._move_to(host)
        else:
            self._park()        # no 3D view yet: into the first one
        self._dock.hide()
        self._dock.installEventFilter(self)
        area = _area()
        if area is not None:
            area.subWindowActivated.connect(self._follow)
        return True

    def detach(self) -> None:
        """Back into the dock."""
        if not self._attached:
            return
        self._attached = False
        self._dock.removeEventFilter(self)
        area = _area()
        if area is not None:
            try:
                area.subWindowActivated.disconnect(self._follow)
            except (RuntimeError, TypeError):
                pass
        for old in (self._host, self._holder):
            if _alive(old):
                old.removeEventFilter(self)
        self._host = self._holder = None
        self._passing = False
        self._owning = False
        self._parked = False
        view = self._dock._view
        if _alive(view):
            view.removeEventFilter(self)
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
        if host is None:
            self._park()                # Start page, a drawing, nothing
            # A 3D view that has just been activated may not have shown
            # its GL widget yet - on opening a file, especially. Look
            # again once it has had the chance.
            if not self._retrying:
                self._retrying = True
                for delay in (0, 150, 600):
                    QtCore.QTimer.singleShot(delay, self._retry)
        elif host is not self._host or self._parked:
            self._move_to(host)

    def _retry(self) -> None:
        self._retrying = False
        if not self._attached or not self._parked:
            return
        host = active_viewport()
        if host is not None:
            self._move_to(host)

    def _park(self) -> None:
        """Take the panel out of view: its 3D view is going, or not shown.

        A child widget dies with its parent, so a 3D view closed with the
        panel in it took the panel with it - and the next document had
        none. The view hides before it is destroyed; at that point the
        panel moves back under the (hidden) dock, out of sight, until
        another 3D view is active or this one shows again.
        """
        view = self._dock._view
        if self._parked or not _alive(view):
            return
        self._parked = True
        self._passing = False
        self._owning = False
        view.hide()
        view.setParent(self._shelf)

    def _move_to(self, host: Any) -> None:
        view = self._dock._view
        if not _alive(view):
            return
        for old in (self._host, self._holder):
            if _alive(old):
                old.removeEventFilter(self)
        self._host = host
        self._holder = self._holder_of(host)
        if self._holder is not None:
            self._holder.installEventFilter(self)
        self._parked = False
        view.setParent(host)
        view.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop,
                          True)
        host.installEventFilter(self)
        view.installEventFilter(self)
        self._passing = False
        self._owning = False
        self._place()
        view.show()
        view.raise_()
        self._dock._release_timer.start()

    def _keep_dock_hidden(self) -> None:
        if self._attached and _alive(self._dock):
            self._dock.hide()

    @staticmethod
    def _holder_of(widget: Any) -> Any:
        while widget is not None:
            if widget.metaObject().className() == "Gui::View3DInventor":
                return widget
            widget = widget.parentWidget()
        return None

    def _place(self) -> None:
        view = self._dock._view
        if not _alive(view) or not _alive(self._host) or self._parked:
            return
        width = min(self._width, max(120, self._host.width() - 40))
        view.setGeometry(0, 0, width, self._host.height())

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        kind = event.type()
        try:
            if watched is self._dock:
                if kind == QtCore.QEvent.Type.Show:
                    # A workbench switch restores docks it remembers as
                    # open; this one stays hidden while the panel is in
                    # the 3D view.
                    QtCore.QTimer.singleShot(0, self._keep_dock_hidden)
                return False
            if watched is self._holder and kind in _GOING:
                self._park()
                return False
            if watched is self._host:
                if kind == QtCore.QEvent.Type.MouseButtonRelease:
                    # The 3D view got a release itself: whatever press was
                    # being passed on is over, however it ended.
                    self._passing = False
                    self._owning = False
                if kind == QtCore.QEvent.Type.Hide:
                    self._park()
                elif kind == QtCore.QEvent.Type.Show and self._parked \
                        and self._host is active_viewport():
                    self._move_to(self._host)
                elif kind == QtCore.QEvent.Type.Resize:
                    self._place()
                elif kind in _PRESSES and self._from_panel(event):
                    self._passing = True
                return False
            if watched is self._dock._view and kind in _PRESSES:
                # Decided before delivery, by asking the panel whether it
                # draws anything at the point (NxtTree.qml wantsPoint).
                # Its own: delivered to the panel and kept from the 3D
                # view, accepted or not. Not its own: handed to the 3D view,
                # and with it every move and the release that follow.
                if self._wants(event):
                    self._passing = False
                    self._owning = True
                    self._deliver(event)
                    return True
                self._owning = False
                self._passing = True
                self._pass_on(event)
                return True
            if watched is self._dock._view and self._owning \
                    and kind in _FOLLOWERS:
                # The panel's own press: its moves and release stay with
                # it too. Left to Qt, a release nothing in the scene
                # accepted - a chip's tap, the eye's - went on to the 3D
                # view, which took it for a click on the model and changed
                # the selection the chip had just made.
                self._deliver(event)
                if kind == QtCore.QEvent.Type.MouseButtonRelease \
                        and not event.buttons():
                    self._owning = False
                return True
            if watched is self._dock._view and self._passing \
                    and kind in _FOLLOWERS:
                self._pass_on(event)
                if kind == QtCore.QEvent.Type.MouseButtonRelease \
                        and not event.buttons():
                    self._passing = False
                    self._owning = False
                return True
        except Exception as exc:
            App.Console.PrintLog("Nxt view overlay: %s\n" % exc)
            self._passing = False
            self._owning = False
        return False

    def _deliver(self, event: Any) -> None:
        """Give a mouse event to the panel only, never past it."""
        quick_widget = _quick_modules()[2].QQuickWidget
        quick_widget.event(self._dock._view, event)
        event.accept()

    def _wants(self, event: Any) -> bool:
        """Does the panel draw anything where this press is?"""
        view = self._dock._view
        root = view.rootObject() if _alive(view) else None
        if root is None:
            return True
        point = event.position()
        try:
            return bool(QtCore.QMetaObject.invokeMethod(
                root, "wantsPoint",
                QtCore.Qt.ConnectionType.DirectConnection,
                QtCore.Q_RETURN_ARG("QVariant"),
                QtCore.Q_ARG("QVariant", point.x()),
                QtCore.Q_ARG("QVariant", point.y())))
        except Exception:
            return True             # when unsure, the panel keeps it

    def _from_panel(self, event: Any) -> bool:
        """Did this press reach the 3D view by passing through the panel?"""
        view = self._dock._view
        if view is None or not view.isVisible():
            return False
        return view.geometry().contains(event.position().toPoint())

    def _pass_on(self, event: Any) -> None:
        """Send the panel's mouse event to the 3D view, in its coordinates."""
        view, host = self._dock._view, self._host
        local = QtCore.QPointF(view.mapTo(host, event.position().toPoint()))
        forwarded = QtGui.QMouseEvent(
            event.type(), local, event.globalPosition(), event.button(),
            event.buttons(), event.modifiers())
        QtWidgets.QApplication.sendEvent(host, forwarded)
