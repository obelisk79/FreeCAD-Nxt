"""Give a 3D view the mouse releases it never got (issue #194).

FreeCAD's navigation styles keep their own record of which buttons are
down, set by the press and cleared by the release that reach the view.
When a release goes elsewhere (to a window or overlay that appeared or
vanished mid-click, a popup's grab, a filter that ate it, a handle
removed mid-drag), the style still believes the button is down. With
the left button "held", a right or middle drag is read as a chord, so
the view only zooms until the next left click clears the flag.

Qt always knows which buttons are really held. Every mouse event over
the view is checked against the presses it has seen: a button the view
saw pressed but Qt says is up is sent the release it missed, before the
event that revealed it, so the navigation sees the real state. Whatever
swallowed the release, on any platform, the next touch of the mouse
puts it right.
"""

from __future__ import annotations

import contextlib
from typing import Any

from ..core import fc, view3d
from ..core.events import ApplicationEventFilter
from ..core.qt import QtCore, QtGui, QtWidgets

_Type = QtCore.QEvent.Type
_Button = QtCore.Qt.MouseButton
# A double click arrives as a press, then a DblClick: only the press counts.
_MOUSE = (_Type.MouseButtonPress, _Type.MouseButtonRelease, _Type.MouseMove)
_TRACKED = (_Button.LeftButton, _Button.RightButton, _Button.MiddleButton)


def stale_dragger(view: Any) -> Any:
    """The dragger holding `view`'s events, or None."""
    from pivy import coin
    action = view.getViewer().getSoEventManager().getHandleEventAction()
    grabber = action.getGrabber()
    if grabber is None or not grabber.isOfType(
            coin.SoDragger.getClassTypeId()):
        return None
    return grabber


def release(viewport: Any, position: QtCore.QPointF,
            button: Any = _Button.LeftButton,
            held: Any = _Button.NoButton) -> None:
    """Give `viewport` the release of `button` it missed.

    Through Qt, as a real release comes, so the navigation style and any
    dragger or sketcher tool waiting on it finish as they would have.
    """
    event = QtGui.QMouseEvent(
        _Type.MouseButtonRelease, position,
        QtCore.QPointF(viewport.mapToGlobal(position.toPoint())),
        button, held, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, event)


class StaleDragGuard(ApplicationEventFilter):
    """Keeps the 3D view's idea of the held buttons in step with Qt's."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._viewport: Any = None
        #: Buttons the viewport saw pressed, and where, not yet released.
        self._down: dict[Any, QtCore.QPointF] = {}
        self._sending = False
        #: A press since the last idle move: check once for a held dragger.
        self._armed = False

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        kind = event.type()
        if kind not in _MOUSE or self._sending:
            return False
        if kind == _Type.MouseButtonPress and watched is not self._viewport:
            self._follow(watched)
        if watched is not self._viewport or self._viewport is None:
            return False
        with contextlib.suppress(Exception):
            self._settle(event)
        return False

    def _follow(self, watched: Any) -> None:
        """A press in another 3D view: watch that one from now on."""
        if view3d.view3d_holding(watched) is None:
            return
        viewport = view3d.active_viewport()
        if viewport is not None and viewport is not self._viewport:
            self._viewport = viewport
            self._down.clear()

    def _settle(self, event: Any) -> None:
        kind = event.type()
        held = event.buttons()
        button = event.button()
        lost = [b for b in self._down
                if not held & b and not (kind == _Type.MouseButtonRelease
                                         and b == button)]
        # A second press of a button still "down": its release was lost.
        if kind == _Type.MouseButtonPress and button in self._down \
                and button not in lost:
            lost.append(button)
        for stale in lost:
            self._send_release(stale, self._down.pop(stale), held)
        if kind == _Type.MouseMove and not held and self._armed:
            self._armed = False
            self._free_dragger(event.position())
        if button in _TRACKED:
            if kind == _Type.MouseButtonPress:
                self._armed = True
                self._down[button] = event.position()
            elif kind == _Type.MouseButtonRelease:
                self._down.pop(button, None)

    def _send_release(self, button: Any, where: QtCore.QPointF,
                      held: Any) -> None:
        # Where it was pressed: what was waiting reads it as a click
        # there, not a drag to wherever the mouse is now.
        self._sending = True
        try:
            release(self._viewport, where, button, held & ~button)
        finally:
            self._sending = False

    def _free_dragger(self, position: QtCore.QPointF) -> None:
        """A dragger still grabbed with no button held: let it go."""
        view = fc.active_view()
        if view is None or stale_dragger(view) is None:
            return
        self._send_release(_Button.LeftButton, position, _Button.NoButton)
        if stale_dragger(view) is not None:
            # It did not want the release: drop the grab itself.
            view.getViewer().getSoEventManager() \
                .getHandleEventAction().releaseGrabber()
