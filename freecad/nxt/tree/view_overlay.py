"""The tree panel drawn inside the 3D view, clicks passing through.

Each press asks the QML whether it draws at that point (`wantsPoint`);
if not, the press and its moves and release go to the 3D view.
"""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCAD as App

from ..core import view3d, widgets
from ..core.qt import QtCore, QtGui, QtWidgets
from ..core.qtquick import modules as _quick_modules

_PRESSES = (QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.MouseButtonDblClick)
_FOLLOWERS = (QtCore.QEvent.Type.MouseMove,
              QtCore.QEvent.Type.MouseButtonRelease)
#: What FreeCAD's overlay panels do that moves their edge.
_OVERLAY_MOVES = (QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Hide,
                  QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Move)
#: Height of the strip docked under the toolbars while the panel is in
#: the 3D view: a dragged toolbar reaching it opens a new toolbar row, as
#: it does over a docked panel's header (the 3D view never offers one).
DROP_STRIP_HEIGHT = 10
#: How often to look again while a close's save prompt is open.
CLOSE_POLL_MS = 100
#: The class of FreeCAD's overlay panels (docks drawn over the 3D view).
_OVERLAY_CLASS = "OverlayTabWidget"
#: What a 3D view window does on its way to being destroyed.
_GOING = (QtCore.QEvent.Type.Close, QtCore.QEvent.Type.DeferredDelete,
          QtCore.QEvent.Type.Hide)


class ViewOverlay(QtCore.QObject):
    """Moves the panel's view into the active 3D view and back."""

    def __init__(self, dock: Any) -> None:
        super().__init__(dock)
        self._dock = dock
        self._host: Any = None
        self._attached = False
        self._passing = False
        self._through = False
        self._owning = False
        #: The View3DInventor around `_host`, watched for closing.
        self._holder: Any = None
        self._parked = False
        self._retrying = False
        #: Whether the user has the panel showing; the dock itself stays
        #: hidden, so its menu entry is kept in step by hand.
        self._shown = True
        #: Explicitly hidden parent for the panel while no 3D view shows,
        #: so a workbench switch showing the dock cannot reveal it.
        self._shelf = QtWidgets.QWidget(dock)
        self._shelf.hide()
        self._strip: Any = None
        #: FreeCAD's overlay panels, watched so the panel keeps clear.
        self._overlays: list[Any] = []
        self._replace = QtCore.QTimer(self)
        self._replace.setSingleShot(True)
        self._replace.setInterval(0)
        self._replace.timeout.connect(self._place)
        self._rehide = QtCore.QTimer(self)
        self._rehide.setSingleShot(True)
        self._rehide.setInterval(0)
        self._rehide.timeout.connect(self._keep_dock_hidden)
        #: After a 3D view was asked to close: back in, if it stayed.
        self._recheck = QtCore.QTimer(self)
        self._recheck.setSingleShot(True)
        self._recheck.setInterval(0)
        self._recheck.timeout.connect(self._after_close)

    def attached(self) -> bool:
        return self._attached

    def shown(self) -> bool:
        return self._attached and self._shown

    def attach(self) -> bool:
        """Into the active 3D view, or out of sight until there is one."""
        view = self._dock._view
        if not widgets.alive(view):
            return False
        self._attached = True
        self._shown = True
        self._dock.setWidget(QtWidgets.QWidget())   # the view leaves it
        host = view3d.active_viewport()
        if host is not None:
            self._move_to(host)
        else:
            self._park()        # no 3D view yet: into the first one
        self._dock.hide()
        self._dock.installEventFilter(self)
        self._dock.toggleViewAction().triggered.connect(self._toggled)
        self._sync_action()
        self._add_strip()
        area = view3d.mdi_area()
        if area is not None:
            area.subWindowActivated.connect(self._follow)
        return True

    def detach(self) -> None:
        """Back into the dock."""
        if not self._attached:
            return
        self._attached = False
        self._recheck.stop()
        self._dock.removeEventFilter(self)
        with contextlib.suppress(RuntimeError, TypeError):
            self._dock.toggleViewAction().triggered.disconnect(self._toggled)
        self._remove_strip()
        area = view3d.mdi_area()
        if area is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                area.subWindowActivated.disconnect(self._follow)
        for old in (self._host, self._holder, *self._overlays):
            if widgets.alive(old):
                old.removeEventFilter(self)
        self._overlays = []
        self._host = self._holder = None
        self._passing = False
        self._owning = False
        self._parked = False
        view = self._dock._view
        if widgets.alive(view):
            self._set_through(False)
            view.removeEventFilter(self)
            view.setParent(None)
            self._dock.setWidget(view)
            view.show()
        self._dock.show()
        self._dock._release_timer.start()

    def _add_strip(self) -> None:
        """Dock an empty, header-high strip along the top, under the toolbars.

        Qt opens a new toolbar row for a toolbar dragged onto a docked
        widget there, which the 3D view does not do.
        """
        main = self._dock.parentWidget()
        if not isinstance(main, QtWidgets.QMainWindow) \
                or widgets.alive(self._strip):
            return
        strip = QtWidgets.QDockWidget(main)
        strip.setObjectName("NxtToolbarDropStrip")
        strip.setWindowTitle("Nxt")
        strip.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        # Not a panel to the user: kept out of View > Panels and the
        # toolbar area's menu.
        strip.toggleViewAction().setVisible(False)
        bar = QtWidgets.QWidget(strip)
        bar.setFixedHeight(DROP_STRIP_HEIGHT)
        strip.setTitleBarWidget(bar)
        body = QtWidgets.QWidget(strip)
        body.setFixedHeight(0)
        strip.setWidget(body)
        # Nothing drawn: the window shows through, as if no dock were there.
        for part in (strip, bar, body):
            part.setAutoFillBackground(False)
        strip.setStyleSheet("background: transparent; border: none;")
        main.addDockWidget(QtCore.Qt.DockWidgetArea.TopDockWidgetArea,
                           strip)
        strip.show()
        self._strip = strip

    def _remove_strip(self) -> None:
        strip, self._strip = self._strip, None
        if not widgets.alive(strip):
            return
        main = strip.parentWidget()
        if isinstance(main, QtWidgets.QMainWindow):
            main.removeDockWidget(strip)
        strip.deleteLater()

    def _after_close(self) -> None:
        """Back into the 3D view if its close was cancelled.

        Not while the save prompt is open: the view may still go.
        """
        if QtWidgets.QApplication.activeModalWidget() is not None:
            self._recheck.start(CLOSE_POLL_MS)
            return
        self._recheck.setInterval(0)
        self._follow()

    def _follow(self, *_args: Any) -> None:
        """Another MDI window became active: go with it, if it is 3D."""
        if not self._attached:
            return
        host = view3d.active_viewport()
        if host is None:
            self._park()
            # A just-activated 3D view may not have its GL widget yet.
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
        host = view3d.active_viewport()
        if host is not None:
            self._move_to(host)

    def _park(self) -> None:
        """Reparent the panel off a hiding 3D view so it is not destroyed."""
        view = self._dock._view
        if self._parked or not widgets.alive(view):
            return
        self._parked = True
        self._passing = False
        self._owning = False
        self._set_through(False)
        view.hide()
        view.setParent(self._shelf)

    def _move_to(self, host: Any) -> None:
        view = self._dock._view
        if not widgets.alive(view):
            return
        for old in (self._host, self._holder):
            if widgets.alive(old):
                old.removeEventFilter(self)
        self._host = host
        self._holder = view3d.view3d_holding(host)
        if self._holder is not None:
            self._holder.installEventFilter(self)
        self._parked = False
        self._set_through(False)
        # Host moves tell us the pointer is back over a pill while
        # the panel is mouse-transparent.
        host.setMouseTracking(True)
        view.setParent(host)
        view.setAttribute(QtCore.Qt.WidgetAttribute.WA_AlwaysStackOnTop,
                          True)
        host.installEventFilter(self)
        view.installEventFilter(self)
        self._watch_overlays()
        self._passing = False
        self._owning = False
        self._place()
        view.setVisible(self._shown)
        view.raise_()
        self._dock._release_timer.start()

    def _keep_dock_hidden(self) -> None:
        if self._attached and widgets.alive(self._dock):
            self._dock.hide()
            self._sync_action()

    def _sync_action(self) -> None:
        """Tick the dock's menu entry by the panel, not the hidden dock."""
        if self._attached and widgets.alive(self._dock):
            self._dock.toggleViewAction().setChecked(self._shown)

    def _toggled(self, on: bool) -> None:
        """The panel's menu entry was chosen: show or hide the panel."""
        if not self._attached:
            return
        self._shown = on
        view = self._dock._view
        if widgets.alive(view) and not self._parked:
            view.setVisible(on)
            if on:
                view.raise_()
        # Qt shows or hides the dock for the entry too: undone next turn.
        self._rehide.start()
        self._dock.save_state()

    def _place(self) -> None:
        view = self._dock._view
        if (not widgets.alive(view) or not widgets.alive(self._host)
                or self._parked):
            return
        view.setGeometry(self._clear_of_overlays())

    def _watch_overlays(self) -> None:
        """Watch FreeCAD's overlay panels: their edges bound the panel."""
        for old in self._overlays:
            if widgets.alive(old):
                old.removeEventFilter(self)
        self._overlays = [
            w for w in QtWidgets.QApplication.allWidgets()
            if _OVERLAY_CLASS in w.metaObject().className()]
        for overlay in self._overlays:
            overlay.installEventFilter(self)

    def _clear_of_overlays(self) -> QtCore.QRect:
        """The 3D view's area less the overlay panels along its sides."""
        host = self._host
        left, top = 0, 0
        right, bottom = host.width(), host.height()
        whole = QtCore.QRect(0, 0, right, bottom)
        for overlay in self._overlays:
            if not widgets.alive(overlay) or not overlay.isVisible():
                continue
            corner = host.mapFromGlobal(
                overlay.mapToGlobal(QtCore.QPoint(0, 0)))
            box = QtCore.QRect(corner, overlay.size()).intersected(whole)
            if box.isEmpty():
                continue
            side = _side_of(overlay, box, whole)
            if side == "left":
                left = max(left, box.right() + 1)
            elif side == "right":
                right = min(right, box.left())
            elif side == "top":
                top = max(top, box.bottom() + 1)
            elif side == "bottom":
                bottom = min(bottom, box.top())
        if right - left < 1 or bottom - top < 1:
            return whole
        return QtCore.QRect(left, top, right - left, bottom - top)

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        kind = event.type()
        try:
            if watched is self._dock:
                if kind in (QtCore.QEvent.Type.Show,
                            QtCore.QEvent.Type.Hide):
                    # Workbench switches re-show remembered docks; a hide
                    # unticks the dock's menu entry.
                    self._rehide.start()
                return False
            if watched in self._overlays:
                if kind in _OVERLAY_MOVES:
                    self._replace.start()
                return False
            if watched is self._holder and kind in _GOING:
                self._park()
                # Closing asks to save first, and may be cancelled.
                self._recheck.start()
                return False
            if watched is self._host:
                if kind == QtCore.QEvent.Type.MouseButtonRelease:
                    self._passing = False
                    self._owning = False
                if kind == QtCore.QEvent.Type.Hide:
                    self._park()
                elif kind == QtCore.QEvent.Type.Show and self._parked \
                        and self._host is view3d.active_viewport():
                    self._move_to(self._host)
                elif kind == QtCore.QEvent.Type.Resize:
                    self._place()
                elif kind in _PRESSES and not self._through \
                        and self._from_panel(event):
                    self._passing = True
                elif kind == QtCore.QEvent.Type.MouseMove \
                        and self._through and not event.buttons() \
                        and self._wants_at(self._in_view(event)):
                    self._set_through(False)
                return False
            if watched is self._dock._view \
                    and kind == QtCore.QEvent.Type.MouseMove \
                    and not event.buttons():
                # Clear flags whose release went elsewhere (e.g. to a
                # dialog the click opened).
                self._passing = self._owning = False
            if watched is self._dock._view \
                    and kind == QtCore.QEvent.Type.MouseMove \
                    and not event.buttons() \
                    and not self._wants_at(event.position()):
                self._set_through(True)
                return True
            if watched is self._dock._view \
                    and kind == QtCore.QEvent.Type.Wheel:
                # Forward explicitly: the scene may accept an unused wheel.
                if self._wants(event):
                    self._scroll(event)
                else:
                    self._pass_wheel(event)
                event.accept()
                return True
            if watched is self._dock._view and kind in _PRESSES:
                # Ask QML, not scene acceptance: tap handlers take part in
                # a press without accepting it.
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
                # Else an unaccepted release (a tap) reaches the 3D view
                # and changes the selection.
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

    def _scroll(self, event: Any) -> None:
        root = self._dock._view.rootObject()
        if root is None:
            return
        QtCore.QMetaObject.invokeMethod(
            root, "scrollWheel", QtCore.Qt.ConnectionType.DirectConnection,
            QtCore.Q_ARG("QVariant", float(event.angleDelta().y())),
            QtCore.Q_ARG("QVariant", float(event.pixelDelta().y())),
            QtCore.Q_ARG("QVariant", bool(
                event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)))

    def _pass_wheel(self, event: Any) -> None:
        """Send the panel's wheel event to the 3D view, in its coordinates."""
        view, host = self._dock._view, self._host
        if not widgets.alive(host):
            return
        local = QtCore.QPointF(view.mapTo(host, event.position().toPoint()))
        forwarded = QtGui.QWheelEvent(
            local, event.globalPosition(), event.pixelDelta(),
            event.angleDelta(), event.buttons(), event.modifiers(),
            event.phase(), event.inverted(), event.source())
        QtWidgets.QApplication.sendEvent(host, forwarded)

    def _deliver(self, event: Any) -> None:
        """Give a mouse event to the panel only, never past it."""
        quick_widget = _quick_modules()[2].QQuickWidget
        quick_widget.event(self._dock._view, event)
        event.accept()

    def _set_through(self, on: bool) -> None:
        """Make the panel transparent to the mouse, or not.

        Lets the 3D view get hover (preselection) and wheel natively.
        """
        view = self._dock._view
        if on == self._through or not widgets.alive(view):
            return
        self._through = on
        view.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, on)
        if on:
            # Clear row hover state.
            QtWidgets.QApplication.sendEvent(
                view, QtCore.QEvent(QtCore.QEvent.Type.Leave))

    def _in_view(self, event: Any) -> QtCore.QPointF:
        """A 3D view event's position in the panel's coordinates."""
        view = self._dock._view
        return QtCore.QPointF(view.mapFrom(self._host,
                                           event.position().toPoint()))

    def _wants(self, event: Any) -> bool:
        """Does the panel draw anything where this press is?"""
        return self._wants_at(event.position())

    def _wants_at(self, point: Any) -> bool:
        """Does the panel draw anything at this point, in its coordinates?"""
        view = self._dock._view
        root = view.rootObject() if widgets.alive(view) else None
        if root is None:
            return True
        try:
            return bool(QtCore.QMetaObject.invokeMethod(
                root, "wantsPoint",
                QtCore.Qt.ConnectionType.DirectConnection,
                QtCore.Q_RETURN_ARG("QVariant"),
                QtCore.Q_ARG("QVariant", point.x()),
                QtCore.Q_ARG("QVariant", point.y())))
        except Exception:
            return True

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


def _side_of(overlay: Any, box: QtCore.QRect, whole: QtCore.QRect) -> str:
    """Which side of the 3D view an overlay panel stands along."""
    name = overlay.objectName().lower()
    for side in ("left", "right", "top", "bottom"):
        if side in name:
            return side
    # By the edge it is nearest, for a name that does not tell.
    gaps = {"left": box.left() - whole.left(),
            "right": whole.right() - box.right(),
            "top": box.top() - whole.top(),
            "bottom": whole.bottom() - box.bottom()}
    return min(gaps, key=lambda k: gaps[k])
