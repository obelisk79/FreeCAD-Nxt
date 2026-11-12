"""Let go of a 3D view handle whose drag never ended.

A Coin dragger takes every event in the view while it is dragged, until
a left release reaches it. If that release is lost (the handle removed
mid-drag, or the release delivered elsewhere), the view stops panning
and orbiting, though it still zooms, until the next left click (issue
#194). A mouse moving over a 3D view with no button held means no drag
can be live: a dragger still holding the view is sent the release it
missed, so it and FreeCAD's navigation finish the drag as a real
release would.
"""

from __future__ import annotations

import contextlib
from typing import Any

import FreeCADGui as Gui

from ..core import view3d
from ..core.events import ApplicationEventFilter
from ..core.qt import QtCore, QtGui, QtWidgets


def stale_dragger(view: Any) -> Any:
    """The dragger holding `view`'s events, or None."""
    from pivy import coin
    action = view.getViewer().getSoEventManager().getHandleEventAction()
    grabber = action.getGrabber()
    if grabber is None or not grabber.isOfType(
            coin.SoDragger.getClassTypeId()):
        return None
    return grabber


def release(viewport: Any, position: QtCore.QPointF) -> None:
    """Give `viewport` the left release its drag missed.

    Through Qt, as a real release comes: FreeCAD's navigation saw the
    press too, and waits for the release as the dragger does.
    """
    event = QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonRelease, position,
        QtCore.QPointF(viewport.mapToGlobal(position.toPoint())),
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, event)


class StaleDragGuard(ApplicationEventFilter):
    """After a click, the first idle mouse move checks for a stuck drag."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._armed = False

    def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802
        kind = event.type()
        if kind == QtCore.QEvent.Type.MouseButtonPress:
            self._armed = True
            return False
        if not self._armed or kind != QtCore.QEvent.Type.MouseMove \
                or event.buttons() or watched is not view3d.active_viewport():
            return False
        self._armed = False
        with contextlib.suppress(Exception):
            view = Gui.ActiveDocument.ActiveView
            if stale_dragger(view) is not None:
                release(watched, event.position())
                if stale_dragger(view) is not None:
                    # It did not want the release: drop the grab itself.
                    view.getViewer().getSoEventManager() \
                        .getHandleEventAction().releaseGrabber()
        return False
